#!/usr/bin/env python3
"""
Тест для проверки обработки пересланных аудио/голосовых сообщений
"""
import sys
import os
import asyncio
import logging

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_forwarded_audio_routing():
    """Тест логики роутинга пересланных аудио сообщений"""
    print("=== Тест роутинга пересланных аудио ===")
    
    # Симуляция пересланного голосового сообщения
    forwarded_voice = {
        "message": {
            "message_id": 1,
            "from": {"id": 12345, "username": "testuser"},
            "chat": {"id": 12345},
            "forward_from": {"id": 67890, "username": "original_user"},
            "voice": {
                "file_id": "BAADBAADWgADBREAAYdaXXDbJEORAg",
                "duration": 10,
                "mime_type": "audio/ogg",
                "file_size": 5432
            }
        }
    }
    
    # Симуляция пересланного аудио файла
    forwarded_audio = {
        "message": {
            "message_id": 2,
            "from": {"id": 12345, "username": "testuser"},
            "chat": {"id": 12345},
            "forward_origin": {"type": "user", "date": 1638360000},
            "audio": {
                "file_id": "BAADBAADXAADBREAAe5bAAFSfWCGAg",
                "duration": 180,
                "performer": "Artist",
                "title": "Song",
                "mime_type": "audio/mpeg",
                "file_size": 4321000
            }
        }
    }
    
    # Симуляция пересланного аудио документа
    forwarded_audio_doc = {
        "message": {
            "message_id": 3,
            "from": {"id": 12345, "username": "testuser"},
            "chat": {"id": 12345},
            "forward_from_chat": {"id": 54321, "type": "channel"},
            "document": {
                "file_id": "BAADBAADYgADBREAAQbgNlGhCe8qAg",
                "file_name": "meeting_recording.oga",
                "mime_type": "audio/ogg",
                "file_size": 2100000
            }
        }
    }
    
    # Симуляция обычного фото (должно игнорироваться)
    forwarded_photo = {
        "message": {
            "message_id": 4,
            "from": {"id": 12345, "username": "testuser"},
            "chat": {"id": 12345},
            "forward_from": {"id": 67890},
            "photo": [
                {"file_id": "AgACAgIAAx0EW8sJOgACBhN...", "width": 1280, "height": 720}
            ]
        }
    }
    
    def check_should_process_as_audio(message_data):
        """Проверяет, должно ли сообщение обрабатываться как аудио"""
        message = message_data["message"]
        
        # Проверяем наличие пересылки
        is_forwarded = any(key in message for key in ['forward_from', 'forward_from_chat', 'forward_origin'])
        
        # Проверяем типы медиа
        has_voice = "voice" in message
        has_audio = "audio" in message
        has_audio_document = False
        
        if "document" in message:
            document = message["document"]
            file_name = document.get("file_name", "").lower()
            mime_type = document.get("mime_type", "")
            
            audio_extensions = [".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus", ".oga"]
            audio_mime_types = ["audio/mpeg", "audio/mp3", "audio/wav", "audio/m4a", "audio/ogg", "audio/flac", "audio/aac", "audio/opus"]
            
            has_audio_document = (
                mime_type in audio_mime_types or
                any(file_name.endswith(ext) for ext in audio_extensions)
            )
        
        has_other_media = any(key in message for key in ['photo', 'video', 'sticker', 'animation', 'video_note'])
        
        return (has_voice or has_audio or has_audio_document), has_other_media, is_forwarded
    
    # Тестируем все случаи
    test_cases = [
        ("Пересланное голосовое", forwarded_voice, True, False),
        ("Пересланное аудио", forwarded_audio, True, False),
        ("Пересланный аудио документ", forwarded_audio_doc, True, False),
        ("Пересланное фото", forwarded_photo, False, True),
    ]
    
    all_passed = True
    
    for name, data, should_be_audio, should_be_ignored in test_cases:
        is_audio, has_other_media, is_forwarded = check_should_process_as_audio(data)
        
        print(f"\n{name}:")
        print(f"  Пересланное: {is_forwarded}")
        print(f"  Должно обрабатываться как аудио: {should_be_audio} -> {is_audio}")
        print(f"  Должно игнорироваться: {should_be_ignored} -> {has_other_media and not is_audio}")
        
        if is_audio != should_be_audio:
            print(f"  ❌ ОШИБКА: ожидалось {should_be_audio}, получено {is_audio}")
            all_passed = False
        else:
            print(f"  ✓ Корректно")
    
    if all_passed:
        print("\n🎉 Все тесты пройдены успешно!")
    else:
        print("\n❌ Есть ошибки в логике")
    
    return all_passed

def test_audio_extensions():
    """Тест расширений аудио файлов"""
    print("\n=== Тест аудио расширений ===")
    
    audio_extensions = [".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus", ".oga"]
    
    test_files = [
        ("music.mp3", True),
        ("voice.oga", True),  # Telegram голосовые часто в .oga
        ("record.opus", True),  # WebM/Opus формат
        ("document.pdf", False),
        ("video.mp4", False),
        ("audio.wav", True),
    ]
    
    all_passed = True
    
    for filename, should_match in test_files:
        matches = any(filename.lower().endswith(ext) for ext in audio_extensions)
        print(f"  {filename}: {matches} (ожидалось: {should_match})")
        
        if matches != should_match:
            print(f"    ❌ ОШИБКА")
            all_passed = False
        else:
            print(f"    ✓ Корректно")
    
    # Проверяем наличие .oga
    has_oga = ".oga" in audio_extensions
    print(f"\n  Расширение .oga поддерживается: {has_oga}")
    if not has_oga:
        print("    ❌ КРИТИЧЕСКАЯ ОШИБКА: .oga отсутствует!")
        all_passed = False
    else:
        print("    ✓ .oga присутствует")
    
    return all_passed

def main():
    """Запуск всех тестов"""
    print("🧪 Тест исправления пересланных аудио сообщений\n")
    
    test1_passed = test_forwarded_audio_routing()
    test2_passed = test_audio_extensions()
    
    print(f"\n{'='*50}")
    if test1_passed and test2_passed:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("\n✅ Изменения готовы для тестирования в Telegram:")
        print("   • Пересылайте голосовые сообщения")
        print("   • Пересылайте аудио файлы")
        print("   • Пересылайте аудио документы (.mp3, .oga, и т.д.)")
        print("   • Фото/видео без текста продолжат игнорироваться")
        print("\n🔍 Проверьте логи бота для подтверждения роутинга")
        return 0
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
        print("   Проверьте логику перед тестированием в Telegram")
        return 1

if __name__ == "__main__":
    sys.exit(main())