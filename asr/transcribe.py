"""
Модуль транскрибации аудио с использованием faster-whisper
"""

import os
import sys
import logging
import tempfile
import shutil
from typing import Dict, List, Optional
from pathlib import Path
import re

logger = logging.getLogger(__name__)

# Проверяем наличие зависимостей
try:
    from faster_whisper import WhisperModel
    import ffmpeg
    from pydub import AudioSegment
    TRANSCRIPTION_AVAILABLE = True
except ImportError as e:
    TRANSCRIPTION_AVAILABLE = False
    logger.warning(f"Транскрибация недоступна: {e}")

# Глобальные переменные для ленивой загрузки моделей
_whisper_model = None
_model_size = None


def get_whisper_model(model_size: str = "small"):
    """Получает модель Whisper с ленивой загрузкой"""
    global _whisper_model, _model_size
    
    if not TRANSCRIPTION_AVAILABLE:
        return None
    
    # Если модель уже загружена и размер не изменился
    if _whisper_model is not None and _model_size == model_size:
        return _whisper_model
    
    try:
        logger.info(f"Загружаю модель faster-whisper: {model_size}")
        
        # Освобождаем предыдущую модель
        if _whisper_model is not None:
            del _whisper_model
        
        _whisper_model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8"  # Экономим память
        )
        _model_size = model_size
        
        logger.info(f"Модель {model_size} загружена успешно")
        return _whisper_model
        
    except Exception as e:
        logger.error(f"Ошибка загрузки модели {model_size}: {e}")
        
        # Fallback на меньшую модель
        if model_size == "small":
            logger.info("Пробую модель tiny...")
            return get_whisper_model("tiny")
        
        return None


def convert_to_wav(input_path: str, output_path: str) -> bool:
    """Конвертирует аудио в WAV 16kHz mono"""
    try:
        logger.info(f"Конвертация {input_path} → {output_path}")
        
        # Используем pydub для конвертации
        audio = AudioSegment.from_file(input_path)
        
        # Конвертируем в mono, 16kHz
        audio = audio.set_channels(1)  # mono
        audio = audio.set_frame_rate(16000)  # 16kHz
        
        # Экспортируем как WAV
        audio.export(output_path, format="wav")
        
        logger.info(f"Конвертация завершена: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка конвертации аудио: {e}")
        
        # Fallback на ffmpeg-python
        try:
            logger.info("Пробую конвертацию через ffmpeg...")
            (
                ffmpeg
                .input(input_path)
                .output(output_path, ar=16000, ac=1, format='wav')
                .overwrite_output()
                .run(quiet=True)
            )
            logger.info("Конвертация через ffmpeg успешна")
            return True
            
        except Exception as ffmpeg_e:
            logger.error(f"Ошибка ffmpeg конвертации: {ffmpeg_e}")
            return False


def normalize_text(text: str) -> str:
    """Нормализует транскрипт: числа, даты, дни недели"""
    if not text:
        return ""
    
    # Дни недели
    day_replacements = {
        r'\bпн\b': 'понедельник',
        r'\bвт\b': 'вторник', 
        r'\bср\b': 'среда',
        r'\bчт\b': 'четверг',
        r'\bпт\b': 'пятница',
        r'\bсб\b': 'суббота',
        r'\bвс\b': 'воскресенье',
    }
    
    for pattern, replacement in day_replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # Нормализация времени: "в 14" → "в 14:00"
    text = re.sub(r'\bв (\d{1,2})\b', r'в \1:00', text)
    
    # Числа: "1 ый" → "первый"
    number_replacements = {
        r'\b1-?[ый]й?\b': 'первый',
        r'\b2-?[ой]й?\b': 'второй', 
        r'\b3-?[ий]й?\b': 'третий',
        r'\b4-?[ый]й?\b': 'четвертый',
        r'\b5-?[ый]й?\b': 'пятый',
    }
    
    for pattern, replacement in number_replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # Убираем лишние пробелы
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def detect_language(text: str) -> Optional[str]:
    """Простое определение языка по тексту"""
    if not text:
        return None
    
    # Считаем русские и английские символы
    russian_chars = len(re.findall(r'[а-яё]', text.lower()))
    english_chars = len(re.findall(r'[a-z]', text.lower()))
    
    total_chars = russian_chars + english_chars
    if total_chars == 0:
        return None
    
    # Если больше 60% русских символов, считаем русским
    if russian_chars / total_chars > 0.6:
        return "ru"
    elif english_chars / total_chars > 0.6:
        return "en"
    
    return None  # Авто-определение


def transcribe_audio(file_path: str, language: Optional[str] = None) -> Dict:
    """
    Транскрибирует аудиофайл с использованием faster-whisper
    
    Args:
        file_path: путь к аудиофайлу
        language: язык транскрипции ("ru", "en" или None для авто)
    
    Returns:
        {
            "success": bool,
            "text": str,                    # полный текст
            "segments": List[{"start":float,"end":float,"text":str}],
            "language": str,               # определенный язык
            "error": str                   # ошибка, если success=False
        }
    """
    
    if not TRANSCRIPTION_AVAILABLE:
        return {
            "success": False,
            "error": "faster-whisper не установлен - транскрибация недоступна"
        }
    
    if not os.path.exists(file_path):
        return {
            "success": False,
            "error": f"Файл не найден: {file_path}"
        }
    
    temp_wav_path = None
    
    try:
        # Создаем временный WAV файл
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
            temp_wav_path = temp_wav.name
        
        # Конвертируем в WAV
        if not convert_to_wav(file_path, temp_wav_path):
            return {
                "success": False,
                "error": "Не удалось конвертировать аудио в WAV"
            }
        
        # Получаем модель Whisper
        model = get_whisper_model("small")
        if model is None:
            return {
                "success": False,
                "error": "Не удалось загрузить модель Whisper"
            }
        
        logger.info(f"Начинаю транскрибацию: {file_path}")
        
        # Параметры транскрибации
        transcribe_params = {
            "audio": temp_wav_path,
            "language": language,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 300},
            "temperature": [0.0, 0.2, 0.4],  # Fallback температуры
            "beam_size": 5,
        }
        
        # Выполняем транскрибацию
        segments, info = model.transcribe(**transcribe_params)
        
        # Собираем результаты
        text_parts = []
        segment_list = []
        
        for segment in segments:
            if segment.text.strip():
                text_parts.append(segment.text.strip())
                segment_list.append({
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": segment.text.strip()
                })
        
        # Полный текст
        full_text = " ".join(text_parts)
        
        # Нормализация текста
        normalized_text = normalize_text(full_text)
        
        # Определяем язык
        detected_language = info.language if hasattr(info, 'language') else detect_language(normalized_text)
        
        logger.info(f"Транскрибация завершена: {len(normalized_text)} символов, язык: {detected_language}")
        
        return {
            "success": True,
            "text": normalized_text,
            "segments": segment_list,
            "language": detected_language or "unknown",
            "duration": info.duration if hasattr(info, 'duration') else 0.0
        }
        
    except Exception as e:
        logger.error(f"Ошибка транскрибации: {e}")
        
        # Если OOM, пробуем меньшую модель
        if "memory" in str(e).lower() or "cuda" in str(e).lower():
            logger.info("Пробую модель tiny из-за ошибки памяти...")
            try:
                model = get_whisper_model("tiny")
                if model is not None:
                    segments, info = model.transcribe(temp_wav_path, language=language)
                    
                    text_parts = []
                    segment_list = []
                    
                    for segment in segments:
                        if segment.text.strip():
                            text_parts.append(segment.text.strip())
                            segment_list.append({
                                "start": float(segment.start),
                                "end": float(segment.end),
                                "text": segment.text.strip()
                            })
                    
                    full_text = " ".join(text_parts)
                    normalized_text = normalize_text(full_text)
                    
                    logger.info(f"Транскрибация tiny модели завершена: {len(normalized_text)} символов")
                    
                    return {
                        "success": True,
                        "text": normalized_text,
                        "segments": segment_list,
                        "language": info.language if hasattr(info, 'language') else "unknown",
                        "duration": info.duration if hasattr(info, 'duration') else 0.0
                    }
                    
            except Exception as tiny_e:
                logger.error(f"Ошибка транскрибации с tiny моделью: {tiny_e}")
        
        return {
            "success": False,
            "error": f"Ошибка транскрибации: {str(e)}"
        }
    
    finally:
        # Очищаем временный файл
        if temp_wav_path and os.path.exists(temp_wav_path):
            try:
                os.unlink(temp_wav_path)
            except:
                pass


def check_transcription_availability() -> Dict[str, bool]:
    """Проверяет доступность компонентов транскрибации"""
    availability = {
        "faster_whisper": False,
        "ffmpeg": False,
        "pydub": False
    }
    
    try:
        from faster_whisper import WhisperModel
        availability["faster_whisper"] = True
    except ImportError:
        pass
    
    try:
        import ffmpeg
        availability["ffmpeg"] = True
    except ImportError:
        pass
    
    try:
        from pydub import AudioSegment
        availability["pydub"] = True
    except ImportError:
        pass
    
    return availability


def get_transcription_info() -> str:
    """Возвращает информацию о доступности транскрибации"""
    availability = check_transcription_availability()
    
    if all(availability.values()):
        return "Транскрибация полностью поддерживается (faster-whisper + pydub + ffmpeg)"
    elif availability["faster_whisper"]:
        return "Транскрибация частично поддерживается (faster-whisper доступен)"
    else:
        return "Транскрибация недоступна - установите faster-whisper"