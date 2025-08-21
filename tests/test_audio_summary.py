#!/usr/bin/env python3
"""
Тесты для улучшенной системы аудио суммаризации
"""

import os
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from summarizers.text_summarizer import smart_summarize, extract_sentences, categorize_sentences
    from summarizers.audio_pipeline import get_pipeline_info
    from bot.ui_settings import UserSettings, SummaryFormat, SummaryVerbosity
    TESTING_AVAILABLE = True
except ImportError as e:
    print(f"❌ Тестирование недоступно: {e}")
    TESTING_AVAILABLE = False
    sys.exit(1)


def create_test_transcript() -> dict:
    """Создает тестовый транскрипт близкий к примеру из ТЗ"""
    
    test_text = """
    Договорились о встрече в понедельник и вторник на полдня. 
    Первое занятие будет бесплатно, чтобы вы могли понять подходит ли вам формат.
    Расписание можно будет скорректировать если понравится и вы решите продолжить.
    Нужно будет подготовить договор к понедельнику или вторнику.
    После пробного занятия подтвердите пожалуйста запись на постоянной основе.
    Стоимость составляет 3000 рублей в месяц за индивидуальные занятия.
    Если вас что-то не устроит, можно будет обсудить корректировку расписания.
    Мы работаем с 10:00 до 18:00 в будние дни.
    Необходимо заранее предупреждать об отмене за 24 часа.
    В случае болезни можно перенести занятие без штрафа.
    Оплата производится в начале каждого месяца.
    """
    
    return {
        "text": test_text.strip(),
        "segments": [
            {"start": 0.0, "end": 5.0, "text": "Договорились о встрече в понедельник и вторник на полдня."},
            {"start": 5.0, "end": 10.0, "text": "Первое занятие будет бесплатно, чтобы вы могли понять подходит ли вам формат."},
            {"start": 10.0, "end": 15.0, "text": "Расписание можно будет скорректировать если понравится и вы решите продолжить."}
        ],
        "language": "ru",
        "duration": 45.0
    }


def test_sentence_extraction():
    """Тест разбиения на предложения"""
    print("🧪 Тест извлечения предложений")
    
    transcript = create_test_transcript()
    sentences = extract_sentences(transcript["text"])
    
    assert len(sentences) >= 5, f"Ожидалось минимум 5 предложений, получено {len(sentences)}"
    assert any("договорились" in s.lower() for s in sentences), "Не найдено предложение с 'договорились'"
    assert any("бесплатно" in s.lower() for s in sentences), "Не найдено предложение с 'бесплатно'"
    
    print(f"✅ Извлечено {len(sentences)} предложений")


def test_sentence_categorization():
    """Тест категоризации предложений"""
    print("\n🧪 Тест категоризации предложений")
    
    transcript = create_test_transcript()
    sentences = extract_sentences(transcript["text"])
    categories = categorize_sentences(sentences)
    
    # Проверяем наличие договоренностей
    assert len(categories['agreements']) > 0, "Не найдены договоренности"
    agreement_found = any("договорились" in sent.lower() for _, sent in categories['agreements'])
    assert agreement_found, "Предложение с 'договорились' не в категории договоренностей"
    
    # Проверяем наличие сроков
    assert len(categories['deadlines']) > 0, "Не найдены сроки"
    deadline_found = any(any(day in sent.lower() for day in ['понедельник', 'вторник']) for _, sent in categories['deadlines'])
    assert deadline_found, "Дни недели не найдены в сроках"
    
    # Проверяем наличие действий
    assert len(categories['actions']) > 0, "Не найдены действия"
    action_found = any("подготовить" in sent.lower() or "подтвердить" in sent.lower() for _, sent in categories['actions'])
    assert action_found, "Не найдены ключевые действия"
    
    print(f"✅ Категории: договоренности={len(categories['agreements'])}, сроки={len(categories['deadlines'])}, действия={len(categories['actions'])}")


def test_structured_format():
    """Тест структурированного формата"""
    print("\n🧪 Тест структурированного формата")
    
    transcript = create_test_transcript()
    summary = smart_summarize(transcript, format="structured", verbosity="detailed")
    
    # Проверяем наличие секций
    assert "договоренности" in summary.lower(), "Отсутствует секция договоренностей"
    assert "сроки" in summary.lower() or "расписание" in summary.lower(), "Отсутствует секция сроков"
    assert "следующие шаги" in summary.lower(), "Отсутствует секция следующих шагов"
    
    # Проверяем ключевые факты
    assert "понедельник" in summary.lower() or "вторник" in summary.lower(), "Не упомянуты дни недели"
    assert "бесплатно" in summary.lower(), "Не упомянуто 'бесплатно'"
    assert "расписание" in summary.lower(), "Не упомянуто 'расписание'"
    
    # Проверяем длину в режиме detailed
    assert len(summary) >= 300, f"Слишком короткое саммари в режиме detailed: {len(summary)} символов"
    
    print(f"✅ Структурированное саммари: {len(summary)} символов")
    print(f"Содержит разделы и ключевые факты")


def test_different_verbosity():
    """Тест разных уровней подробности"""
    print("\n🧪 Тест уровней подробности")
    
    transcript = create_test_transcript()
    
    # Тестируем все уровни
    short_summary = smart_summarize(transcript, format="structured", verbosity="short")
    normal_summary = smart_summarize(transcript, format="structured", verbosity="normal")
    detailed_summary = smart_summarize(transcript, format="structured", verbosity="detailed")
    
    # Проверяем что detailed длиннее normal, а normal длиннее short
    assert len(detailed_summary) > len(normal_summary), "Detailed должен быть длиннее normal"
    assert len(normal_summary) > len(short_summary), "Normal должен быть длиннее short"
    
    # Все должны содержать основные факты
    for summary, mode in [(short_summary, "short"), (normal_summary, "normal"), (detailed_summary, "detailed")]:
        assert "понедельник" in summary.lower() or "вторник" in summary.lower(), f"Дни недели отсутствуют в {mode}"
        assert "бесплатно" in summary.lower(), f"'Бесплатно' отсутствует в {mode}"
    
    print(f"✅ Длины саммари - short: {len(short_summary)}, normal: {len(normal_summary)}, detailed: {len(detailed_summary)}")


def test_different_formats():
    """Тест разных форматов вывода"""
    print("\n🧪 Тест форматов вывода")
    
    transcript = create_test_transcript()
    
    # Тестируем все форматы
    structured = smart_summarize(transcript, format="structured", verbosity="normal")
    bullets = smart_summarize(transcript, format="bullets", verbosity="normal")
    paragraph = smart_summarize(transcript, format="paragraph", verbosity="normal")
    
    # Проверяем характерные черты форматов
    assert "**" in structured, "Структурированный формат должен содержать заголовки"
    assert "•" in bullets, "Bullet формат должен содержать маркеры"
    
    # Все форматы должны содержать ключевую информацию
    for summary, fmt in [(structured, "structured"), (bullets, "bullets"), (paragraph, "paragraph")]:
        assert len(summary) > 100, f"Саммари {fmt} слишком короткое: {len(summary)}"
        key_terms_found = sum(1 for term in ["договор", "бесплатно", "расписание"] if term in summary.lower())
        assert key_terms_found >= 2, f"В формате {fmt} найдено только {key_terms_found} ключевых терминов"
    
    print(f"✅ Все форматы содержат ключевую информацию")


def test_user_settings():
    """Тест пользовательских настроек"""
    print("\n🧪 Тест пользовательских настроек")
    
    # Создаем настройки пользователя
    settings = UserSettings(12345)
    
    # Проверяем настройки по умолчанию
    assert settings.get_format_str() == "structured", "Формат по умолчанию должен быть structured"
    assert settings.get_verbosity_str() == "normal", "Подробность по умолчанию должна быть normal"
    
    # Тестируем изменение настроек
    assert settings.set_format("bullets"), "Не удалось установить формат bullets"
    assert settings.get_format_str() == "bullets", "Формат не изменился на bullets"
    
    assert settings.set_verbosity("detailed"), "Не удалось установить подробность detailed"
    assert settings.get_verbosity_str() == "detailed", "Подробность не изменилась на detailed"
    
    # Тестируем неверные значения
    assert not settings.set_format("invalid"), "Должна быть ошибка для неверного формата"
    assert not settings.set_verbosity("invalid"), "Должна быть ошибка для неверной подробности"
    
    print(f"✅ Настройки работают корректно")


def test_key_facts_preservation():
    """Тест сохранения ключевых фактов"""
    print("\n🧪 Тест сохранения ключевых фактов")
    
    transcript = create_test_transcript()
    summary = smart_summarize(transcript, format="structured", verbosity="normal")
    
    # Ключевые факты которые должны сохраниться
    key_facts = [
        "договор",      # договоренности
        "полдня",       # длительность  
        "бесплатно",    # условия
        "расписание",   # организационные вопросы
        "3000",         # стоимость
        "24 часа"       # правила отмены
    ]
    
    preserved_facts = []
    for fact in key_facts:
        if fact.lower() in summary.lower():
            preserved_facts.append(fact)
    
    # Должно быть сохранено минимум 4 из 6 ключевых фактов
    assert len(preserved_facts) >= 4, f"Сохранено только {len(preserved_facts)} из {len(key_facts)} ключевых фактов: {preserved_facts}"
    
    print(f"✅ Сохранены ключевые факты: {', '.join(preserved_facts)}")


def test_pipeline_info():
    """Тест информации о пайплайне"""
    print("\n🧪 Тест информации о пайплайне")
    
    info = get_pipeline_info()
    assert isinstance(info, str), "Информация о пайплайне должна быть строкой"
    assert len(info) > 10, "Информация о пайплайне слишком короткая"
    
    print(f"✅ Информация о пайплайне: {info}")


def run_all_tests():
    """Запускает все тесты"""
    print("🧪 Тестирование улучшенной системы аудио суммаризации\n")
    
    if not TESTING_AVAILABLE:
        print("❌ Тестирование недоступно - отсутствуют зависимости")
        return False
    
    tests = [
        test_sentence_extraction,
        test_sentence_categorization,
        test_structured_format,
        test_different_verbosity,
        test_different_formats,
        test_user_settings,
        test_key_facts_preservation,
        test_pipeline_info
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1
    
    print(f"\n📊 Результаты тестов аудио суммаризации: {passed} прошли, {failed} провалились")
    
    if failed == 0:
        print("\n✅ Все тесты прошли! Система готова к работе")
        print("🎯 Проверены: извлечение предложений, категоризация, форматы, подробность, настройки")
        return True
    else:
        print(f"\n❌ {failed} тестов провалились, требуется доработка")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)