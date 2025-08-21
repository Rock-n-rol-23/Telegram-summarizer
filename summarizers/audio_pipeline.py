"""
Конвейер обработки аудио: транскрибация + умная суммаризация
"""

import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

try:
    from asr.transcribe import transcribe_audio
    from summarizers.text_summarizer import smart_summarize
    AUDIO_PIPELINE_AVAILABLE = True
except ImportError as e:
    AUDIO_PIPELINE_AVAILABLE = False
    logger.warning(f"Аудио пайплайн недоступен: {e}")


def summarize_audio_file(
    file_path: str, 
    format: str = "structured", 
    verbosity: str = "normal",
    language: Optional[str] = None,
    progress_callback=None
) -> Dict:
    """
    Полный конвейер обработки аудиофайла
    
    Args:
        file_path: путь к аудиофайлу
        format: "structured" | "bullets" | "paragraph"
        verbosity: "short" | "normal" | "detailed"
        language: язык для транскрибации ("ru", "en" или None)
        progress_callback: функция для отчета о прогрессе
    
    Returns:
        {
            "success": bool,
            "summary": str,               # готовое саммари
            "transcript": str,            # полный транскрипт
            "language": str,              # определенный язык
            "duration": float,            # длительность аудио
            "processing_time": float,     # время обработки
            "stages": Dict,               # время каждого этапа
            "error": str                  # ошибка, если success=False
        }
    """
    
    if not AUDIO_PIPELINE_AVAILABLE:
        return {
            "success": False,
            "error": "Аудио пайплайн недоступен - установите зависимости"
        }
    
    start_time = time.time()
    stages = {}
    
    try:
        logger.info(f"Начинаю обработку аудио: {file_path}")
        
        # Этап 1: Транскрибация
        if progress_callback:
            progress_callback("🎧 Транскрибирую аудио...")
        
        transcribe_start = time.time()
        transcript_result = transcribe_audio(file_path, language=language)
        stages["transcription"] = time.time() - transcribe_start
        
        if not transcript_result["success"]:
            return {
                "success": False,
                "error": f"Ошибка транскрибации: {transcript_result['error']}",
                "processing_time": time.time() - start_time,
                "stages": stages
            }
        
        transcript_text = transcript_result["text"]
        detected_language = transcript_result.get("language", "unknown")
        duration = transcript_result.get("duration", 0.0)
        
        logger.info(f"Транскрибация завершена: {len(transcript_text)} символов, {detected_language}")
        
        # Проверяем минимальную длину
        if len(transcript_text) < 50:
            return {
                "success": False,
                "error": "Транскрипт слишком короткий для суммаризации",
                "transcript": transcript_text,
                "language": detected_language,
                "duration": duration,
                "processing_time": time.time() - start_time,
                "stages": stages
            }
        
        # Автоматическая настройка verbosity для коротких аудио
        if duration > 0 and duration < 120:  # Меньше 2 минут
            if verbosity == "normal":
                verbosity = "detailed"
                logger.info("Короткое аудио - переключаю на detailed режим")
        
        # Этап 2: Умная суммаризация
        if progress_callback:
            progress_callback("🤖 Создаю умное саммари...")
        
        summarize_start = time.time()
        summary = smart_summarize(
            transcript_result, 
            format=format, 
            verbosity=verbosity
        )
        stages["summarization"] = time.time() - summarize_start
        
        total_time = time.time() - start_time
        
        logger.info(f"Обработка завершена за {total_time:.1f}с: {len(summary)} символов саммари")
        
        return {
            "success": True,
            "summary": summary,
            "transcript": transcript_text,
            "language": detected_language,
            "duration": duration,
            "processing_time": total_time,
            "stages": stages,
            "format": format,
            "verbosity": verbosity
        }
        
    except Exception as e:
        logger.error(f"Ошибка в аудио пайплайне: {e}")
        return {
            "success": False,
            "error": f"Ошибка обработки: {str(e)}",
            "processing_time": time.time() - start_time,
            "stages": stages
        }


def get_pipeline_info() -> str:
    """Возвращает информацию о доступности аудио пайплайна"""
    if not AUDIO_PIPELINE_AVAILABLE:
        return "Аудио пайплайн недоступен"
    
    # Проверяем компоненты
    try:
        from asr.transcribe import check_transcription_availability
        from summarizers.text_summarizer import check_summarization_availability
        
        transcription = check_transcription_availability()
        summarization = check_summarization_availability()
        
        transcription_ok = transcription.get("faster_whisper", False)
        summarization_ok = sum(summarization.values()) >= 2
        
        if transcription_ok and summarization_ok:
            return "Аудио пайплайн полностью функционален"
        elif transcription_ok:
            return "Аудио пайплайн частично функционален (транскрибация доступна)"
        elif summarization_ok:
            return "Аудио пайплайн частично функционален (суммаризация доступна)"
        else:
            return "Аудио пайплайн недоступен - отсутствуют ключевые зависимости"
            
    except Exception as e:
        return f"Ошибка проверки пайплайна: {e}"


def estimate_processing_time(duration: float) -> str:
    """Оценивает время обработки аудио"""
    if duration <= 0:
        return "~30 секунд"
    
    # Примерные оценки (зависят от размера модели и мощности CPU)
    transcription_ratio = 0.3  # 30% от длительности аудио
    summarization_time = 5     # ~5 секунд на суммаризацию
    
    estimated_seconds = duration * transcription_ratio + summarization_time
    
    if estimated_seconds < 60:
        return f"~{int(estimated_seconds)} секунд"
    else:
        minutes = int(estimated_seconds // 60)
        seconds = int(estimated_seconds % 60)
        return f"~{minutes}м {seconds}с"


# Вспомогательные функции для интеграции

def quick_audio_summary(file_path: str, duration: float = 0) -> str:
    """Быстрое саммари с автоматическими настройками"""
    
    # Автоматический выбор настроек
    if duration > 0 and duration < 120:  # Короткое аудио
        format = "structured"
        verbosity = "detailed"
    elif duration > 600:  # Длинное аудио (>10 мин)
        format = "bullets" 
        verbosity = "short"
    else:  # Среднее аудио
        format = "structured"
        verbosity = "normal"
    
    result = summarize_audio_file(file_path, format=format, verbosity=verbosity)
    
    if result["success"]:
        return result["summary"]
    else:
        return f"Ошибка обработки: {result['error']}"


def format_audio_result(result: Dict, include_stats: bool = True) -> str:
    """Форматирует результат обработки для отправки пользователю"""
    if not result["success"]:
        return f"❌ {result['error']}"
    
    output = []
    
    # Основное саммари
    output.append(result["summary"])
    
    # Статистика
    if include_stats:
        output.append("")
        output.append("📊 **Статистика обработки:**")
        
        duration = result.get("duration", 0)
        if duration > 0:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            output.append(f"• Длительность: {minutes}м {seconds}с")
        
        transcript_len = len(result.get("transcript", ""))
        summary_len = len(result.get("summary", ""))
        
        output.append(f"• Транскрипт: {transcript_len:,} символов")
        output.append(f"• Саммари: {summary_len:,} символов")
        
        if transcript_len > 0 and summary_len > 0:
            compression = (1 - summary_len / transcript_len) * 100
            output.append(f"• Сжатие: {compression:.1f}%")
        
        processing_time = result.get("processing_time", 0)
        output.append(f"• Время обработки: {processing_time:.1f}с")
        
        stages = result.get("stages", {})
        if stages:
            transcription_time = stages.get("transcription", 0)
            summarization_time = stages.get("summarization", 0)
            output.append(f"• Транскрибация: {transcription_time:.1f}с, суммаризация: {summarization_time:.1f}с")
        
        language = result.get("language", "unknown")
        if language != "unknown":
            lang_name = {"ru": "русский", "en": "английский"}.get(language, language)
            output.append(f"• Язык: {lang_name}")
        
        format_info = f"{result.get('format', 'structured')} / {result.get('verbosity', 'normal')}"
        output.append(f"• Режим: {format_info}")
    
    return "\n".join(output)