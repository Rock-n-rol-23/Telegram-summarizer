#!/usr/bin/env python3
"""
Тест отладки аудио обработки
Проверяет, что новая система работает корректно
"""
import sys
import os
import asyncio
import logging

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_audio_descriptor_extraction():
    """Тест извлечения аудио дескрипторов"""
    from utils.tg_audio import extract_audio_descriptor, get_audio_info_text
    
    print("=== Тест обработки пересланного голосового сообщения ===")
    
    # Симуляция пересланного голосового сообщения
    forwarded_voice_message = {
        "message_id": 12345,
        "from": {"id": 123456789, "username": "testuser"},
        "chat": {"id": -100123456789, "type": "supergroup"},
        "date": 1692461200,
        "forward_from": {"id": 987654321, "first_name": "Forwarded User"},
        "voice": {
            "duration": 15,
            "mime_type": "audio/ogg",
            "file_id": "AwACAgIAAxkBAAIBY2PhKT...",
            "file_unique_id": "AgADBQADVwABY2PhKQ",
            "file_size": 28800
        }
    }
    
    # Тест извлечения дескриптора
    descriptor = extract_audio_descriptor(forwarded_voice_message)
    
    if descriptor:
        print(f"✅ Дескриптор успешно извлечен: {descriptor}")
        
        info_text = get_audio_info_text(descriptor)
        print(f"📋 Информация об аудио: {info_text}")
        
        print(f"🔍 Детали:")
        print(f"   - Тип: {descriptor['kind']}")
        print(f"   - File ID: {descriptor['file_id'][:20]}...")
        print(f"   - Длительность: {descriptor['duration']} сек")
        print(f"   - MIME: {descriptor['mime_type']}")
        
        return True
    else:
        print("❌ Не удалось извлечь дескриптор")
        return False

def test_database_method():
    """Тест метода сохранения в базу данных"""
    try:
        from database import DatabaseManager
        
        print("\n=== Тест подключения к базе данных ===")
        
        # Инициализируем базу данных
        db = DatabaseManager()
        
        # Проверяем, что метод save_user_request существует
        if hasattr(db, 'save_user_request'):
            print("✅ Метод save_user_request найден")
            
            # Попробуем вызвать метод (без реального сохранения)
            try:
                # Получаем сигнатуру метода
                import inspect
                sig = inspect.signature(db.save_user_request)
                print(f"📋 Сигнатура метода: {sig}")
                return True
            except Exception as e:
                print(f"⚠️ Ошибка при проверке метода: {e}")
                return False
        else:
            print("❌ Метод save_user_request не найден")
            print(f"📋 Доступные методы: {[method for method in dir(db) if not method.startswith('_')]}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка инициализации базы данных: {e}")
        return False

def test_summarization_method():
    """Тест метода суммаризации"""
    try:
        from simple_bot import SimpleTelegramBot
        
        print("\n=== Тест методов суммаризации ===")
        
        # Проверяем доступные методы суммаризации
        methods = [method for method in dir(SimpleTelegramBot) if 'summarize' in method.lower()]
        print(f"📋 Доступные методы суммаризации: {methods}")
        
        # Проверяем конкретные методы
        if hasattr(SimpleTelegramBot, 'summarize_text'):
            print("✅ Метод summarize_text найден")
            
            # Получаем сигнатуру
            import inspect
            sig = inspect.signature(SimpleTelegramBot.summarize_text)
            print(f"📋 Сигнатура summarize_text: {sig}")
            return True
        else:
            print("❌ Метод summarize_text не найден")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при проверке методов суммаризации: {e}")
        return False

def main():
    """Запуск всех тестов"""
    print("🧪 Отладка аудио обработки в Telegram боте\n")
    
    tests = [
        ("Извлечение аудио дескрипторов", test_audio_descriptor_extraction),
        ("Методы базы данных", test_database_method),
        ("Методы суммаризации", test_summarization_method)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Тест: {test_name}")
        print('='*50)
        
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте: {e}")
            results.append((test_name, False))
    
    # Итоговый отчет
    print(f"\n{'='*50}")
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print('='*50)
    
    for test_name, success in results:
        status = "✅ ПРОШЕЛ" if success else "❌ НЕ ПРОШЕЛ"
        print(f"{test_name}: {status}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print(f"\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        print("💡 Новая система обработки аудио готова к использованию")
        return 0
    else:
        print(f"\n⚠️ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
        print("🔧 Требуется дополнительная отладка")
        return 1

if __name__ == "__main__":
    sys.exit(main())