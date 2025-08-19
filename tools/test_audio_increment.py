#!/usr/bin/env python3
"""
Тест первого инкремента улучшения аудио обработки
Проверяет новую функциональность извлечения аудио дескрипторов
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.tg_audio import extract_audio_descriptor, get_audio_info_text, is_audio_document, sanitize_filename

def test_audio_descriptor_extraction():
    """Тест извлечения дескрипторов аудио"""
    print("=== Тест извлечения аудио дескрипторов ===")
    
    # Тест 1: Voice сообщение
    voice_message = {
        "voice": {
            "file_id": "BAADBAADRgADBREAAYag2DP7...",
            "duration": 15,
            "mime_type": "audio/ogg"
        }
    }
    
    descriptor = extract_audio_descriptor(voice_message)
    print(f"Voice: {descriptor}")
    assert descriptor and descriptor["kind"] == "voice"
    assert descriptor["file_id"] == "BAADBAADRgADBREAAYag2DP7..."
    assert descriptor["duration"] == 15
    print("✅ Voice test passed")
    
    # Тест 2: Audio файл
    audio_message = {
        "audio": {
            "file_id": "BAADBAADRgADBREAAYag2DP7xxx",
            "file_name": "song.mp3", 
            "duration": 180,
            "mime_type": "audio/mpeg"
        }
    }
    
    descriptor = extract_audio_descriptor(audio_message)
    print(f"Audio: {descriptor}")
    assert descriptor and descriptor["kind"] == "audio"
    assert descriptor["file_name"] == "song.mp3"
    print("✅ Audio test passed")
    
    # Тест 3: Video note
    video_note_message = {
        "video_note": {
            "file_id": "DQACAgIAAxkBAAIC...",
            "duration": 30
        }
    }
    
    descriptor = extract_audio_descriptor(video_note_message)
    print(f"Video note: {descriptor}")
    assert descriptor and descriptor["kind"] == "video_note"
    print("✅ Video note test passed")
    
    # Тест 4: Document с аудио MIME
    audio_doc_message = {
        "document": {
            "file_id": "BAADBAADRgADBREAAYag2DP7yyy",
            "file_name": "recording.wav",
            "mime_type": "audio/wav"
        }
    }
    
    descriptor = extract_audio_descriptor(audio_doc_message)
    print(f"Audio document: {descriptor}")
    assert descriptor and descriptor["kind"] == "document"
    assert descriptor["file_name"] == "recording.wav"
    print("✅ Audio document test passed")
    
    # Тест 5: Document с аудио расширением но без MIME
    audio_doc_ext_message = {
        "document": {
            "file_id": "BAADBAADRgADBREAAYag2DP7zzz",
            "file_name": "voice_memo.m4a",
            "mime_type": "application/octet-stream"
        }
    }
    
    descriptor = extract_audio_descriptor(audio_doc_ext_message)
    print(f"Audio document (by extension): {descriptor}")
    assert descriptor and descriptor["kind"] == "document"
    print("✅ Audio document (extension) test passed")
    
    # Тест 6: Не аудио сообщение
    text_message = {
        "text": "Hello world"
    }
    
    descriptor = extract_audio_descriptor(text_message)
    print(f"Text message: {descriptor}")
    assert descriptor is None
    print("✅ Non-audio message test passed")
    
    # Тест 7: Пересланное voice сообщение
    forwarded_voice = {
        "forward_from": {"id": 123456},
        "voice": {
            "file_id": "BAADBAADRgADBREAAYag2DP7forwarded",
            "duration": 25
        }
    }
    
    descriptor = extract_audio_descriptor(forwarded_voice)
    print(f"Forwarded voice: {descriptor}")
    assert descriptor and descriptor["kind"] == "voice"
    print("✅ Forwarded voice test passed")

def test_audio_info_text():
    """Тест форматирования информации об аудио"""
    print("\n=== Тест форматирования аудио информации ===")
    
    descriptor = {
        "kind": "voice",
        "file_id": "test123",
        "file_name": "voice.ogg",
        "duration": 65  # 1:05
    }
    
    info = get_audio_info_text(descriptor)
    print(f"Audio info: {info}")
    assert "Голосовое сообщение" in info
    assert "1:05" in info
    print("✅ Audio info formatting test passed")

def test_document_audio_detection():
    """Тест определения аудио документов"""
    print("\n=== Тест определения аудио документов ===")
    
    # Аудио по MIME
    audio_doc = {
        "mime_type": "audio/mpeg",
        "file_name": "song.mp3"
    }
    assert is_audio_document(audio_doc)
    print("✅ Audio MIME detection passed")
    
    # Аудио по расширению
    audio_ext_doc = {
        "mime_type": "application/octet-stream",
        "file_name": "recording.wav"
    }
    assert is_audio_document(audio_ext_doc)
    print("✅ Audio extension detection passed")
    
    # Не аудио
    text_doc = {
        "mime_type": "application/pdf",
        "file_name": "document.pdf"
    }
    assert not is_audio_document(text_doc)
    print("✅ Non-audio document detection passed")

def test_filename_sanitization():
    """Тест очистки имен файлов"""
    print("\n=== Тест очистки имен файлов ===")
    
    test_cases = [
        ("normal_file.mp3", "normal_file.mp3"),
        ("file with spaces.wav", "file_with_spaces.wav"),
        ("file<>:|?.ogg", "file.ogg"),
        ("очень_длинное_имя_файла_которое_нужно_обрезать_" * 5 + ".mp3", None),  # Проверим, что обрезается
        ("", "audio_file"),
        ("   ___   ", "audio_file")
    ]
    
    for original, expected in test_cases:
        result = sanitize_filename(original)
        print(f"'{original}' -> '{result}'")
        if expected:
            assert result == expected
        else:
            assert len(result) <= 100  # Проверяем, что обрезается
    
    print("✅ Filename sanitization tests passed")

def main():
    """Запуск всех тестов"""
    print("🧪 Тест первого инкремента улучшения аудио обработки\n")
    
    try:
        test_audio_descriptor_extraction()
        test_audio_info_text() 
        test_document_audio_detection()
        test_filename_sanitization()
        
        print(f"\n{'='*50}")
        print("✅ ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        print(f"{'='*50}")
        print("\n🎉 Первый инкремент готов к тестированию:")
        print("• Унифицированное извлечение аудио дескрипторов")
        print("• Поддержка пересланных сообщений") 
        print("• Обработка всех типов аудио (voice, audio, video_note, document)")
        print("• Улучшенные прогресс-сообщения")
        print("• Детальная обработка ошибок")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ТЕСТ НЕ ПРОШЕЛ: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())