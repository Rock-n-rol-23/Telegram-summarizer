"""
Простой Vosk transcriber для продакшна
Автоматическая загрузка русской модели и транскрипция
"""
import os
import json
import logging
import zipfile
import urllib.request
import shutil
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Глобальные переменные для кэширования
_VOSK_MODEL_DIR = os.environ.get("VOSK_MODEL_DIR", "./models/vosk-ru")
_VOSK_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
_vosk_model = None

def check_ffmpeg() -> bool:
    """Проверка доступности FFmpeg"""
    ffmpeg_path = os.getenv("FFMPEG_PATH", "ffmpeg")
    return shutil.which(ffmpeg_path) is not None

def to_wav_16k_mono(src: str, dst: str, ffmpeg_path: str = "ffmpeg") -> bool:
    """Конвертация в WAV 16kHz mono"""
    import subprocess
    try:
        cmd = [ffmpeg_path, "-y", "-i", src, "-ac", "1", "-ar", "16000", dst]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            logger.info(f"Converted: {src} -> {dst}")
            return True
        else:
            logger.error(f"FFmpeg error: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout")
        return False
    except Exception as e:
        logger.error(f"FFmpeg conversion failed: {e}")
        return False

def _ensure_vosk_model():
    """Автоматическая загрузка и распаковка модели Vosk"""
    try:
        os.makedirs(_VOSK_MODEL_DIR, exist_ok=True)
        
        # Проверяем, распакована ли модель
        if os.path.exists(os.path.join(_VOSK_MODEL_DIR, "am")):
            logger.info("Vosk model already exists")
            return True
            
        logger.info("Downloading Vosk Russian model...")
        tmp_zip = "/tmp/vosk_ru.zip"
        
        # Скачиваем модель
        urllib.request.urlretrieve(_VOSK_URL, tmp_zip)
        logger.info("Model downloaded, extracting...")
        
        # Распаковываем во временную папку
        with zipfile.ZipFile(tmp_zip) as z:
            z.extractall("/tmp")
        
        # Находим распакованную папку и перемещаем
        for name in os.listdir("/tmp"):
            if name.startswith("vosk-model-small-ru"):
                src_path = os.path.join("/tmp", name)
                if os.path.exists(src_path):
                    # Убираем целевую папку если есть
                    if os.path.exists(_VOSK_MODEL_DIR):
                        shutil.rmtree(_VOSK_MODEL_DIR)
                    shutil.move(src_path, _VOSK_MODEL_DIR)
                    logger.info(f"Model installed to {_VOSK_MODEL_DIR}")
                    break
        
        # Очищаем временный файл
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)
            
        return os.path.exists(os.path.join(_VOSK_MODEL_DIR, "am"))
        
    except Exception as e:
        logger.error(f"Failed to setup Vosk model: {e}")
        return False

def transcribe_audio(file_path: str, language_hint: Optional[str] = None) -> Dict:
    """
    Транскрибирует аудио файл с помощью Vosk
    
    Args:
        file_path: Путь к WAV файлу (16kHz mono)
        language_hint: Подсказка языка (игнорируется, всегда русский)
        
    Returns:
        Dict с результатом транскрипции
    """
    global _vosk_model
    
    try:
        # Проверяем наличие Vosk
        try:
            import vosk
            from vosk import Model, KaldiRecognizer
        except ImportError:
            return {
                "text": "",
                "language": "ru", 
                "duration_sec": 0.0,
                "engine": "vosk",
                "chunks": 0,
                "error": "Vosk не установлен. Выполните: pip install vosk==0.3.45"
            }
        
        # Подготавливаем модель
        if not _ensure_vosk_model():
            return {
                "text": "",
                "language": "ru",
                "duration_sec": 0.0, 
                "engine": "vosk",
                "chunks": 0,
                "error": "Не удалось загрузить модель Vosk"
            }
            
        # Загружаем модель один раз
        if _vosk_model is None:
            logger.info(f"Loading Vosk model from {_VOSK_MODEL_DIR}")
            _vosk_model = Model(_VOSK_MODEL_DIR)
            logger.info("Vosk model loaded successfully")
        
        # Открываем аудио файл
        import wave
        with wave.open(file_path, "rb") as wf:
            # Проверяем параметры
            if wf.getframerate() != 16000:
                logger.warning(f"Expected 16kHz, got {wf.getframerate()}Hz")
            if wf.getnchannels() != 1:
                logger.warning(f"Expected mono, got {wf.getnchannels()} channels")
                
            # Создаем распознаватель
            rec = KaldiRecognizer(_vosk_model, wf.getframerate())
            rec.SetWords(True)
            
            # Процессируем аудио по кускам
            text_parts = []
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                    
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").strip()
                    if text:
                        text_parts.append(text)
            
            # Получаем финальный результат
            final_result = json.loads(rec.FinalResult())
            final_text = final_result.get("text", "").strip()
            if final_text:
                text_parts.append(final_text)
        
        # Объединяем весь текст
        full_text = " ".join(text_parts).strip()
        
        logger.info(f"Vosk transcription completed: {len(full_text)} chars, {len(text_parts)} chunks")
        
        return {
            "text": full_text,
            "language": "ru",
            "duration_sec": 0.0,  # Длительность рассчитается отдельно
            "engine": "vosk",
            "chunks": len(text_parts)
        }
        
    except Exception as e:
        logger.error(f"Vosk transcription error: {e}")
        return {
            "text": "",
            "language": "ru",
            "duration_sec": 0.0,
            "engine": "vosk", 
            "chunks": 0,
            "error": str(e)
        }

def get_available_engines() -> list:
    """Возвращает список доступных ASR движков"""
    engines = []
    
    # Проверяем Vosk
    try:
        import vosk
        engines.append("vosk")
    except ImportError:
        pass
        
    return engines

# Проверка FFmpeg при импорте
if __name__ == "__main__":
    # Проверяем FFmpeg
    assert check_ffmpeg(), "FFmpeg not found! Install with: nixpkgs = ['ffmpeg']"
    print("✅ FFmpeg available")
    
    # Проверяем Vosk
    try:
        import vosk
        print("✅ Vosk available")
    except ImportError:
        print("❌ Vosk not available - install with: pip install vosk==0.3.45")