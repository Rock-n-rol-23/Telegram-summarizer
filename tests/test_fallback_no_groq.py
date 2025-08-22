"""
Тест fallback режима без Groq API с сохранением блока "🔢 Цифры и факты"
"""

import pytest
import asyncio
from summarization.pipeline import SummarizationPipeline
from quality.quality_checks import extract_critical_numbers

# Тестовый текст с разнообразными фактами
FALLBACK_TEST_TEXT = """
Компания "Технологии Будущего" подвела итоги работы за 2024 год. 
Выручка выросла на 42% и составила 5.8 миллиарда рублей против 4.1 миллиарда в 2023 году.

Ключевые финансовые показатели:
- EBITDA увеличилась до 1.2 миллиарда рублей (+35%)
- Чистая прибыль: $180 миллионов (рост 28%)
- Свободный денежный поток: €150 миллионов
- Долговая нагрузка снижена с 2.8x до 1.9x EBITDA

Операционные результаты:
- Произведено 2.5 миллиона единиц продукции (+18%)
- Численность персонала выросла с 8 500 до 10 200 человек
- Открыто 47 новых точек продаж в 15 регионах
- Доля рынка увеличилась с 12.3% до 15.7%

Планы на 2025 год:
- Инвестиции в размере 900 миллионов рублей
- Запуск производства к 15 марта 2025 года
- Цель по выручке: 7.2 миллиарда рублей
- Планируемая рентабельность: не менее 18.5%

Компания также объявила о выплате дивидендов в размере 45 рублей на акцию, 
что на 25% больше чем в прошлом году (36 рублей).
"""

@pytest.mark.asyncio
async def test_fallback_pipeline_without_groq():
    """Тест работы пайплайна без Groq API клиента"""
    
    # Создаем пайплайн без клиента (None)
    pipeline = SummarizationPipeline(None)
    
    result = await pipeline.summarize_text_pipeline(
        FALLBACK_TEST_TEXT,
        lang="ru",
        target_chars=800,
        format_type="bullets"
    )
    
    assert result['success'] == True, "Fallback должен работать успешно"
    assert result['method'] == 'fallback', "Должен использоваться fallback метод"
    assert 'summary' in result, "Должно быть поле summary"
    
    summary = result['summary']
    print(f"Fallback summary length: {len(summary)} characters")
    print("Fallback summary:")
    print(summary)
    
    # Проверяем наличие обязательного блока с цифрами
    assert '🔢 Цифры и факты:' in summary, "Должен быть блок 'Цифры и факты'"
    
    # Проверяем что блок действительно содержит числа/факты
    facts_section = summary.split('🔢 Цифры и факты:')[1] if '🔢 Цифры и факты:' in summary else ""
    assert len(facts_section.strip()) > 50, "Блок с фактами не должен быть пустым"

def test_fallback_preserves_key_numbers():
    """Тест сохранения ключевых чисел в fallback режиме"""
    
    # Выполняем синхронно для простоты
    pipeline = SummarizationPipeline(None)
    
    # Создаем простой тест без async
    facts_extractor = pipeline
    source_facts = pipeline._create_facts_block({
        'money': [
            {'raw': '5.8 миллиарда рублей'},
            {'raw': '$180 миллионов'},
            {'raw': '€150 миллионов'}
        ],
        'dates': [
            {'raw': '15 марта 2025 года'}
        ],
        'sentences_with_numbers': [
            {'numbers': [{'raw': '42%'}]},
            {'numbers': [{'raw': '35%'}]},
            {'numbers': [{'raw': '18.5%'}]},
            {'numbers': [{'raw': '2.5 миллиона'}]}
        ]
    })
    
    print("Generated facts block:")
    print(facts_extractor)
    
    # Проверяем что ключевые числа попали в блок фактов
    key_numbers = ['5.8 миллиарда', '$180 миллионов', '€150 миллионов', '42%', '15 марта']
    
    preserved_count = 0
    for number in key_numbers:
        if number.lower() in facts_extractor.lower():
            preserved_count += 1
            print(f"✓ Сохранено число: {number}")
        else:
            print(f"✗ Потеряно число: {number}")
    
    preservation_rate = preserved_count / len(key_numbers)
    assert preservation_rate >= 0.7, f"В fallback должно сохраняться минимум 70% чисел, сохранено: {preservation_rate:.1%}"

@pytest.mark.asyncio
async def test_fallback_vs_original_text_coverage():
    """Тест покрытия контента в fallback режиме"""
    
    pipeline = SummarizationPipeline(None)
    
    result = await pipeline.summarize_text_pipeline(
        FALLBACK_TEST_TEXT,
        lang="ru", 
        target_chars=600,
        format_type="structured"
    )
    
    assert result['success'] == True
    
    summary = result['summary']
    
    # Проверяем что основные темы покрыты
    key_topics = [
        'выручка', 'ebitda', 'прибыль', 'производство', 
        'персонал', 'инвестиции', '2025', 'дивиденд'
    ]
    
    covered_topics = 0
    for topic in key_topics:
        if topic.lower() in summary.lower():
            covered_topics += 1
            print(f"✓ Тема покрыта: {topic}")
        else:
            print(f"✗ Тема отсутствует: {topic}")
    
    topic_coverage = covered_topics / len(key_topics)
    assert topic_coverage >= 0.6, f"Fallback должен покрывать минимум 60% тем, покрыто: {topic_coverage:.1%}"

def test_fallback_format_handling():
    """Тест обработки разных форматов в fallback режиме"""
    
    formats_to_test = ['bullets', 'paragraph', 'structured']
    
    for format_type in formats_to_test:
        pipeline = SummarizationPipeline(None)
        
        # Синхронный fallback для тестирования
        summary = pipeline._create_fallback_summary(
            FALLBACK_TEST_TEXT, 
            'ru', 
            format_type, 
            500
        )
        
        assert len(summary) > 100, f"Fallback summary для {format_type} должно быть содержательным"
        assert '🔢 Цифры и факты:' in summary, f"Блок фактов должен быть в {format_type}"
        
        if format_type == 'bullets':
            assert '•' in summary or '—' in summary or '-' in summary, f"Bullets формат должен содержать маркеры"
        
        print(f"✓ Format {format_type} works in fallback mode")

@pytest.mark.asyncio
async def test_fallback_quality_report():
    """Тест отчета о качестве в fallback режиме"""
    
    pipeline = SummarizationPipeline(None)
    
    result = await pipeline.summarize_text_pipeline(
        FALLBACK_TEST_TEXT,
        lang="ru",
        target_chars=700,
        format_type="bullets"
    )
    
    assert 'quality_report' in result, "Должен быть отчет о качестве"
    
    quality = result['quality_report']
    
    # В fallback режиме качество может быть ниже, но не критично
    assert isinstance(quality['quality_score'], float), "Должен быть численный скор качества"
    assert 0 <= quality['quality_score'] <= 1, "Скор должен быть от 0 до 1"
    assert quality['language_correct'] == True, "Язык должен определяться правильно"
    
    print(f"Fallback quality score: {quality['quality_score']:.2f}")
    print(f"Numbers preserved: {quality['numbers_preserved']}")
    print(f"Missing numbers: {quality['missing_numbers']}")

def test_fallback_must_keep_sentences():
    """Тест приоритета предложений с ключевыми фактами"""
    
    from summarization.fact_extractor import extract_key_facts, select_must_keep_sentences
    
    # Извлекаем факты из текста
    facts = extract_key_facts(FALLBACK_TEST_TEXT, 'ru')
    must_keep_indices = select_must_keep_sentences(facts)
    
    assert len(must_keep_indices) > 0, "Должны быть предложения для обязательного сохранения"
    
    print(f"Must keep sentence indices: {sorted(must_keep_indices)}")
    
    # Проверяем что предложения с фактами действительно важные
    sentences = FALLBACK_TEST_TEXT.split('.')
    important_patterns = ['%', 'млрд', 'млн', '$', '€', '₽', '2024', '2025']
    
    for idx in must_keep_indices:
        if idx < len(sentences):
            sentence = sentences[idx]
            has_important_data = any(pattern in sentence for pattern in important_patterns)
            print(f"Sentence {idx}: {sentence[:50]}... - Important: {has_important_data}")
            
    # Хотя бы половина "обязательных" предложений должна содержать важные данные
    important_count = sum(
        1 for idx in must_keep_indices 
        if idx < len(sentences) and any(pattern in sentences[idx] for pattern in important_patterns)
    )
    
    important_rate = important_count / len(must_keep_indices)
    assert important_rate >= 0.5, f"Минимум 50% must-keep предложений должны содержать важные данные, найдено: {important_rate:.1%}"

def test_fallback_performance():
    """Тест производительности fallback режима"""
    
    import time
    
    start_time = time.time()
    
    pipeline = SummarizationPipeline(None)
    summary = pipeline._create_fallback_summary(FALLBACK_TEST_TEXT, 'ru', 'bullets', 600)
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    print(f"Fallback execution time: {execution_time:.3f} seconds")
    
    # Fallback должен работать быстро (менее 1 секунды для текста ~1KB)
    assert execution_time < 2.0, f"Fallback слишком медленный: {execution_time:.3f}s"
    assert len(summary) > 200, "Fallback должен генерировать содержательный результат"
    assert '🔢 Цифры и факты:' in summary, "Блок фактов обязателен даже при быстрой работе"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])