"""
Тесты сохранения чисел, процентов, валют и дат в суммаризации
"""

import pytest
import asyncio
from summarization.pipeline import SummarizationPipeline
from quality.quality_checks import validate_numbers_preserved, extract_critical_numbers

# Тестовые тексты с ключевыми фактами
TEST_TEXT_RU = """
Компания показала рост выручки на 38% до 3 млрд рублей в 2024 году. 
Планируется увеличение производства к 15 сентября на 2,5 миллиона единиц.
Инвестиции составят $150 млн, а также дополнительно €50 млн от европейских партнеров.
Процентная ставка выросла на +15 б.п. до 7,25%.
Численность сотрудников увеличится с 1 200 до 1 850 человек.
Срок реализации проекта: с января по декабрь 2025 года.
"""

TEST_TEXT_EN = """
The company reported 25% revenue growth to $2.5 billion in Q3 2024.
New facility will produce 1.5 million units by December 15th.
Investment includes €75 million for equipment and £25 million for training.
Interest rate increased by +0.5% to 5.75%.
Headcount will grow from 800 to 1,200 employees by March 2025.
"""

class MockGroqClient:
    """Мок клиент для тестирования без реального API"""
    
    def __init__(self, return_json=True):
        self.return_json = return_json
    
    @property
    def chat(self):
        return MockChat(self.return_json)

class MockChat:
    def __init__(self, return_json):
        self.return_json = return_json
    
    @property 
    def completions(self):
        return MockCompletions(self.return_json)

class MockCompletions:
    def __init__(self, return_json):
        self.return_json = return_json
    
    def create(self, **kwargs):
        """Мок ответ от LLM"""
        
        if kwargs.get('response_format', {}).get('type') == 'json_object' or self.return_json:
            # Phase A - JSON response
            json_response = {
                "bullets": [
                    "Рост выручки на 38% до 3 млрд рублей в 2024 году",
                    "Планы увеличения производства к 15 сентября на 2,5 миллиона единиц",
                    "Инвестиции $150 млн + €50 млн от европейских партнеров",
                    "Процентная ставка +15 б.п. до 7,25%"
                ],
                "key_facts": [
                    {"value_raw": "38%", "value_norm": 0.38, "unit": "%"},
                    {"value_raw": "3 млрд рублей", "value_norm": 3000000000, "unit": "RUB"},
                    {"value_raw": "$150 млн", "value_norm": 150000000, "unit": "USD"},
                    {"value_raw": "€50 млн", "value_norm": 50000000, "unit": "EUR"},
                    {"value_raw": "15 б.п.", "value_norm": 0.0015, "unit": "bp"},
                    {"value_raw": "7,25%", "value_norm": 0.0725, "unit": "%"},
                    {"value_raw": "15 сентября", "norm": "2024-09-15"}
                ],
                "entities": {
                    "ORG": ["Компания"],
                    "PERSON": [],
                    "GPE": []
                },
                "uncertainties": []
            }
            
            return MockResponse(json.dumps(json_response, ensure_ascii=False))
        else:
            # Phase B - text response
            final_summary = """
Компания демонстрирует значительный рост, увеличив выручку на 38% до 3 млрд рублей в 2024 году. 

Ключевые планы:
• Увеличение производства к 15 сентября на 2,5 миллиона единиц
• Привлечение инвестиций $150 млн и €50 млн от европейских партнеров  
• Рост численности с 1 200 до 1 850 сотрудников

🔢 Цифры и факты:
— 38% рост выручки
— 3 млрд рублей выручка 2024
— $150 млн инвестиции
— €50 млн от европейских партнеров
— +15 б.п. рост процентной ставки до 7,25%
— 15 сентября срок увеличения производства
— 2,5 миллиона единиц план производства
            """
            return MockResponse(final_summary.strip())

class MockResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]

class MockChoice:
    def __init__(self, content):
        self.message = MockMessage(content)

class MockMessage:
    def __init__(self, content):
        self.content = content

@pytest.mark.asyncio
async def test_numbers_preserved_pipeline():
    """Тест сохранения чисел через полный пайплайн"""
    
    # Создаем пайплайн с мок клиентом
    mock_client = MockGroqClient()
    pipeline = SummarizationPipeline(mock_client)
    
    result = await pipeline.summarize_text_pipeline(
        TEST_TEXT_RU, 
        lang="ru", 
        target_chars=500,
        format_type="bullets"
    )
    
    assert result['success'] == True
    assert 'summary' in result
    
    # Проверяем сохранность критических чисел
    source_numbers = extract_critical_numbers(TEST_TEXT_RU)
    summary_numbers = extract_critical_numbers(result['summary'])
    
    # Ключевые числа должны присутствовать
    critical_values = ['38%', '3 млрд', '$150', '€50', '7,25%', '15 б.п.', '15 сентября']
    
    for value in critical_values:
        # Проверяем наличие в исходном тексте
        assert any(value.lower() in num.lower() for num in source_numbers), f"Значение {value} не найдено в исходном тексте"
    
    # Проверяем качественную оценку
    is_preserved, missing = validate_numbers_preserved(TEST_TEXT_RU, result['summary'])
    
    # В идеале все числа должны сохраниться
    print(f"Сохранено чисел: {is_preserved}")
    print(f"Потеряно: {missing}")
    
    # Должно быть минимум 80% сохранности
    preservation_rate = 1 - (len(missing) / len(source_numbers)) if source_numbers else 1
    assert preservation_rate >= 0.8, f"Сохранность чисел слишком низкая: {preservation_rate:.2%}"

def test_critical_numbers_extraction():
    """Тест извлечения критически важных чисел"""
    
    numbers = extract_critical_numbers(TEST_TEXT_RU)
    
    expected_patterns = [
        '38%',      # процент
        '3 млрд',   # крупная сумма  
        '$150',     # валюта USD
        '€50',      # валюта EUR
        '7,25%',    # процентная ставка
        '15 б.п.',  # базисные пункты
        '15 сентября' # дата
    ]
    
    found_count = 0
    for pattern in expected_patterns:
        if any(pattern.lower() in num.lower() for num in numbers):
            found_count += 1
            print(f"✓ Найден паттерн: {pattern}")
        else:
            print(f"✗ Не найден паттерн: {pattern}")
    
    # Должно быть найдено минимум 80% ожидаемых паттернов
    assert found_count >= len(expected_patterns) * 0.8

def test_english_numbers_extraction():
    """Тест извлечения чисел из английского текста"""
    
    numbers = extract_critical_numbers(TEST_TEXT_EN)
    
    expected_patterns = [
        '25%',      # percent growth
        '$2.5',     # USD billions
        '€75',      # EUR millions
        '£25',      # GBP millions  
        '5.75%',    # interest rate
        'December 15' # date
    ]
    
    found_count = 0
    for pattern in expected_patterns:
        if any(pattern.lower() in num.lower() for num in numbers):
            found_count += 1
        else:
            print(f"Missing pattern: {pattern}")
    
    assert found_count >= len(expected_patterns) * 0.7

@pytest.mark.asyncio 
async def test_fallback_without_groq():
    """Тест fallback режима без Groq API"""
    
    pipeline = SummarizationPipeline(None)  # Без клиента
    
    result = await pipeline.summarize_text_pipeline(
        TEST_TEXT_RU,
        lang="ru", 
        target_chars=400,
        format_type="bullets"
    )
    
    assert result['success'] == True
    assert result['method'] == 'fallback'
    assert '🔢 Цифры и факты' in result['summary']
    
    # Проверяем что основные числа сохранились
    is_preserved, missing = validate_numbers_preserved(TEST_TEXT_RU, result['summary'])
    
    # В fallback режиме должно сохраняться минимум 60%
    preservation_rate = 1 - (len(missing) / len(extract_critical_numbers(TEST_TEXT_RU)))
    assert preservation_rate >= 0.6

def test_number_validation_edge_cases():
    """Тест граничных случаев валидации чисел"""
    
    # Тест с близкими, но разными числами
    source = "Рост составил 25,5% при инвестициях $100 млн"
    summary_good = "Компания показала рост 25,5% с инвестициями $100 млн"
    summary_bad = "Рост около 25% с инвестициями примерно $90 млн"
    
    is_preserved_good, missing_good = validate_numbers_preserved(source, summary_good)
    is_preserved_bad, missing_bad = validate_numbers_preserved(source, summary_bad)
    
    assert is_preserved_good == True, "Точные числа должны считаться сохраненными"
    assert is_preserved_bad == False, "Измененные числа должны считаться потерянными"
    assert len(missing_bad) > 0, "Должны быть выявлены потерянные числа"

if __name__ == "__main__":
    # Запуск тестов
    import sys
    sys.exit(pytest.main([__file__, "-v"]))