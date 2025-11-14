#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы Gemini API
"""

import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

print("=" * 60)
print("🧪 ТЕСТ КОНФИГУРАЦИИ GEMINI API")
print("=" * 60)

# Проверяем наличие API ключа
gemini_key = os.getenv('GEMINI_API_KEY', '')
use_gemini = os.getenv('USE_GEMINI_PRIMARY', 'true').lower() == 'true'
gemini_model = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash-exp')

print(f"\n📋 Конфигурация:")
print(f"   USE_GEMINI_PRIMARY: {use_gemini}")
print(f"   GEMINI_MODEL: {gemini_model}")

if gemini_key and gemini_key != 'your_gemini_api_key_here':
    print(f"   GEMINI_API_KEY: {'*' * 20}{gemini_key[-8:]} ✅")

    # Проверяем, установлена ли библиотека
    try:
        import google.generativeai as genai
        print(f"\n✅ Библиотека google-generativeai установлена")

        # Пробуем инициализировать клиент
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(gemini_model)
            print(f"✅ Gemini клиент инициализирован успешно")

            # Пробуем простой запрос
            print(f"\n🤖 Тест запроса к Gemini...")
            response = model.generate_content(
                "Ответь одним словом: работает ли Gemini API?",
                generation_config={"max_output_tokens": 50}
            )

            print(f"✅ Ответ от Gemini: {response.text}")
            print(f"\n🎉 ВСЁ РАБОТАЕТ! Gemini API полностью настроен.")

        except Exception as e:
            print(f"❌ Ошибка при работе с Gemini: {e}")
            print(f"   Проверьте правильность API ключа")

    except ImportError:
        print(f"\n❌ Библиотека google-generativeai НЕ установлена")
        print(f"   Установите: python3 -m pip install google-generativeai")

else:
    print(f"   GEMINI_API_KEY: НЕ УСТАНОВЛЕН ❌")
    print(f"\n⚠️  Получите API ключ: https://aistudio.google.com/app/apikey")
    print(f"   И добавьте его в .env файл")

# Проверяем резервные провайдеры
print(f"\n📋 Резервные провайдеры:")
openrouter_key = os.getenv('OPENROUTER_API_KEY', '')
groq_key = os.getenv('GROQ_API_KEY', '')

if openrouter_key and openrouter_key != 'your_openrouter_api_key_here':
    print(f"   OpenRouter: {'*' * 20}{openrouter_key[-8:]} ✅")
else:
    print(f"   OpenRouter: НЕ НАСТРОЕН ❌")

if groq_key and groq_key != 'your_groq_api_key_here':
    print(f"   Groq: {'*' * 20}{groq_key[-8:]} ✅")
else:
    print(f"   Groq: НЕ НАСТРОЕН (опционально)")

print("\n" + "=" * 60)
print("📝 Итог:")
if gemini_key and gemini_key != 'your_gemini_api_key_here':
    print("   ✅ Gemini настроен - бот будет использовать его")
elif openrouter_key and openrouter_key != 'your_openrouter_api_key_here':
    print("   ⚠️  Gemini не настроен, будет использоваться OpenRouter")
else:
    print("   ❌ Ни один провайдер не настроен!")
print("=" * 60)
