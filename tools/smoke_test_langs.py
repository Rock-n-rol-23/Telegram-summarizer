#!/usr/bin/env python3
"""
Тестирование поддержки английского и русского языков
"""
import sys
import os
import asyncio

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.lang import detect_lang, is_ru, is_en
from summarizers.english_sumy import summarize_en
from summarizer import TextSummarizer

# Тестовые тексты
RU_TEXT = """
Искусственный интеллект (ИИ) стремительно развивается и уже сегодня оказывает значительное влияние на различные сферы человеческой деятельности. Машинное обучение позволяет компьютерам анализировать огромные массивы данных и выявлять закономерности, которые было бы невозможно обнаружить человеку. В медицине ИИ помогает диагностировать заболевания на ранних стадиях, анализируя медицинские изображения с точностью, превышающей возможности врачей. В финансовой сфере алгоритмы машинного обучения используются для выявления мошеннических операций и автоматизации торговых решений. Автономные транспортные средства, основанные на технологиях ИИ, обещают революционизировать транспортную индустрию, сделав дороги более безопасными и эффективными.
"""

EN_TEXT = """
Artificial intelligence (AI) is rapidly evolving and already having a significant impact on various aspects of human activity. Machine learning enables computers to analyze vast amounts of data and identify patterns that would be impossible for humans to detect. In healthcare, AI helps diagnose diseases at early stages by analyzing medical images with accuracy exceeding that of doctors. In the financial sector, machine learning algorithms are used to detect fraudulent transactions and automate trading decisions. Autonomous vehicles based on AI technologies promise to revolutionize the transportation industry, making roads safer and more efficient. The integration of AI into everyday life raises important questions about privacy, employment, and the ethical implications of artificial decision-making systems.
"""

SHORT_RU_TEXT = "Это короткий русский текст для тестирования."
SHORT_EN_TEXT = "This is a short English text for testing purposes."

TEXT_WITH_LINKS = """
Recent studies (https://example.com/study1) show that climate change is accelerating faster than previously predicted. The research conducted by MIT (https://mit.edu/research) indicates significant temperature increases. For more information, visit https://climate.gov for official data.
"""

async def test_language_detection():
    """Тест детекции языка"""
    print("=== Тест детекции языка ===")
    
    # Русский текст
    ru_detected = detect_lang(RU_TEXT)
    print(f"RU текст: {ru_detected} (ожидается: ru)")
    assert ru_detected == 'ru', f"Ожидался ru, получен {ru_detected}"
    
    # Английский текст
    en_detected = detect_lang(EN_TEXT)
    print(f"EN текст: {en_detected} (ожидается: en)")
    assert en_detected == 'en', f"Ожидался en, получен {en_detected}"
    
    # Короткие тексты
    short_ru = detect_lang(SHORT_RU_TEXT)
    short_en = detect_lang(SHORT_EN_TEXT)
    print(f"Короткий RU: {short_ru}, Короткий EN: {short_en}")
    
    print("✓ Детекция языка работает корректно\n")

def test_english_summarizer():
    """Тест английского суммаризатора"""
    print("=== Тест английского суммаризатора ===")
    
    # Длинный текст
    summary = summarize_en(EN_TEXT, max_sentences=5)
    print(f"EN саммари длиной {len(summary)} символов:")
    print(summary)
    print()
    
    # Проверки
    assert len(summary) > 50, "Саммари слишком короткое"
    assert summary.count('•') >= 3, "Недостаточно буллетов"
    assert 'AI' in summary or 'artificial' in summary.lower(), "Ключевые термины отсутствуют"
    
    # Короткий текст
    short_summary = summarize_en(SHORT_EN_TEXT, max_sentences=3)
    print(f"Короткий EN саммари: {short_summary}")
    
    # Текст со ссылками
    links_summary = summarize_en(TEXT_WITH_LINKS, max_sentences=3)
    print(f"Саммари с ссылками: {links_summary}")
    assert 'https://' in links_summary, "Ссылки должны сохраняться"
    
    print("✓ Английский суммаризатор работает корректно\n")

async def test_full_summarizer():
    """Тест полного суммаризатора с роутингом"""
    print("=== Тест полного суммаризатора ===")
    
    # Инициализируем суммаризатор (без Groq API для теста)
    summarizer = TextSummarizer(groq_api_key=None, use_local_fallback=False)
    
    # Русский текст (должен вернуть None без Groq API)
    ru_summary = await summarizer.summarize_text(RU_TEXT, target_ratio=0.3)
    print(f"RU саммари: {ru_summary}")
    
    # Английский текст (должен использовать экстрактивный суммаризатор)
    en_summary = await summarizer.summarize_text(EN_TEXT, target_ratio=0.3)
    print(f"EN саммари длиной {len(en_summary) if en_summary else 0} символов:")
    print(en_summary)
    
    if en_summary:
        assert len(en_summary) > 50, "EN саммари слишком короткое"
        assert '•' in en_summary, "EN саммари должно содержать буллеты"
    
    print("✓ Полный суммаризатор работает корректно\n")

def test_helper_functions():
    """Тест вспомогательных функций"""
    print("=== Тест вспомогательных функций ===")
    
    assert is_ru(RU_TEXT), "is_ru должна вернуть True для русского текста"
    assert not is_ru(EN_TEXT), "is_ru должна вернуть False для английского текста"
    
    assert is_en(EN_TEXT), "is_en должна вернуть True для английского текста" 
    assert not is_en(RU_TEXT), "is_en должна вернуть False для русского текста"
    
    print("✓ Вспомогательные функции работают корректно\n")

async def main():
    """Запуск всех тестов"""
    print("🧪 Smoke Test: Поддержка многоязычности (RU/EN)\n")
    
    try:
        await test_language_detection()
        test_english_summarizer()
        await test_full_summarizer()
        test_helper_functions()
        
        print("🎉 Все тесты прошли успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка в тестах: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())