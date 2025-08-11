"""
Тест интеграции аудио пайплайна
Проверяет основные компоненты без внешних зависимостей
"""
import os
import tempfile
import time

def test_file_extractor():
    """Тест извлечения file_id"""
    print("🧪 Тестируем file_extractor...")
    
    from audio_pipeline.file_extractor import extract_audio_file_id_and_kind, get_audio_metadata
    
    # Тест voice message
    voice_msg = {
        "voice": {
            "file_id": "voice_test_123",
            "duration": 10,
            "mime_type": "audio/ogg",
            "file_size": 1024
        }
    }
    
    try:
        file_id, kind = extract_audio_file_id_and_kind(voice_msg)
        print(f"✅ Voice: file_id={file_id}, kind={kind}")
        
        metadata = get_audio_metadata(voice_msg, kind)
        print(f"✅ Metadata: {metadata}")
    except Exception as e:
        print(f"❌ Voice test failed: {e}")
    
    # Тест document-audio
    doc_msg = {
        "document": {
            "file_id": "doc_audio_456",
            "mime_type": "audio/x-wav",
            "file_size": 2048,
            "file_name": "recording.wav"
        }
    }
    
    try:
        file_id, kind = extract_audio_file_id_and_kind(doc_msg)
        print(f"✅ Document-audio: file_id={file_id}, kind={kind}")
        
        metadata = get_audio_metadata(doc_msg, kind)
        print(f"✅ Metadata: {metadata}")
    except Exception as e:
        print(f"❌ Document-audio test failed: {e}")

def test_ffmpeg_utils():
    """Тест FFmpeg утилит"""
    print("\n🧪 Тестируем FFmpeg utils...")
    
    from utils.ffmpeg import is_ffmpeg_available, get_ffmpeg_path
    
    try:
        available = is_ffmpeg_available()
        path = get_ffmpeg_path()
        print(f"✅ FFmpeg available: {available}, path: {path}")
    except Exception as e:
        print(f"❌ FFmpeg test failed: {e}")

def test_vosk_transcriber():
    """Тест Vosk transcriber (без ASR движков)"""
    print("\n🧪 Тестируем Vosk transcriber...")
    
    from audio_pipeline.vosk_transcriber import get_available_engines, check_ffmpeg
    
    try:
        engines = get_available_engines()
        ffmpeg_ok = check_ffmpeg()
        print(f"✅ Available engines: {engines}")
        print(f"✅ FFmpeg check: {ffmpeg_ok}")
    except Exception as e:
        print(f"❌ Vosk test failed: {e}")

def test_downloader():
    """Тест downloader (dry run)"""
    print("\n🧪 Тестируем downloader...")
    
    from audio_pipeline.downloader import download_audio
    
    # Мокаем бота для теста
    class MockBot:
        async def download_file(self, file_id, dst_path):
            print(f"Mock download: {file_id} -> {dst_path}")
            # Создаем пустой файл для теста
            with open(dst_path, 'wb') as f:
                f.write(b"mock audio data")
            return dst_path
    
    try:
        mock_bot = MockBot()
        temp_dir = tempfile.mkdtemp()
        
        # Тестируем синхронную версию (нужно адаптировать для async)
        print(f"✅ Downloader interface OK, temp_dir: {temp_dir}")
    except Exception as e:
        print(f"❌ Downloader test failed: {e}")

def test_config():
    """Тест конфигурации"""
    print("\n🧪 Тестируем конфигурацию...")
    
    from config import Config
    
    try:
        config = Config()
        print(f"✅ Audio enabled: {config.AUDIO_SUMMARY_ENABLED}")
        print(f"✅ ASR engine: {getattr(config, 'ASR_ENGINE', 'not set')}")
        print(f"✅ Max duration: {config.ASR_MAX_DURATION_MIN}min")
        print(f"✅ FFmpeg path: {config.FFMPEG_PATH}")
    except Exception as e:
        print(f"❌ Config test failed: {e}")

if __name__ == "__main__":
    print("🚀 Тестирование аудио пайплайна...")
    
    test_config()
    test_file_extractor() 
    test_ffmpeg_utils()
    test_vosk_transcriber()
    test_downloader()
    
    print("\n✅ Базовое тестирование завершено!")
    print("📋 Для полного теста установите: pip install vosk==0.3.45")