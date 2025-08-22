"""
Модуль проверки качества суммаризации и сохранности ключевых фактов
"""

import re
import logging
from typing import Set, Tuple, List, Dict
try:
    from lingua import Language, LanguageDetectorBuilder
except ImportError:
    # Fallback to simple lingua
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'simple_deps'))
    from simple_lingua import Language, LanguageDetectorBuilder

logger = logging.getLogger(__name__)

def extract_critical_numbers(text: str) -> Set[str]:
    """
    Извлекает критически важные числа из текста
    
    Returns:
        Множество строк с критичными числами/фактами
    """
    critical_patterns = [
        # Проценты
        r'\b\d+(?:[,.]?\d+)?%',
        # Валюты
        r'\d+(?:\s?\d{3})*(?:[,.]?\d+)?\s*(?:₽|руб\.?|рублей?)',
        r'\$\s*\d+(?:\s?\d{3})*(?:[,.]?\d+)?',
        r'€\s*\d+(?:\s?\d{3})*(?:[,.]?\d+)?',
        # Большие числа
        r'\d+(?:[,.]?\d+)?\s*(?:млн\.?|миллион[ов]?|млрд\.?|миллиард[ов]?|тыс\.?|тысяч[и]?)',
        # Диапазоны
        r'\d+(?:[,.]?\d+)?\s*[-–—]\s*\d+(?:[,.]?\d+)?',
        # Даты
        r'\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b',
        r'\b\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b',
        # Времена
        r'\b\d{1,2}:\d{2}\b',
        # Базисные пункты
        r'[+-]?\d+(?:[,.]?\d+)?\s*б\.п\.',
        # Годы
        r'\b20\d{2}\b',
        # Номера/коды
        r'\b\d{3,}\b'
    ]
    
    critical_numbers = set()
    
    for pattern in critical_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Нормализуем для сравнения
            normalized = re.sub(r'\s+', ' ', match.strip())
            critical_numbers.add(normalized)
    
    return critical_numbers


def validate_numbers_preserved(source_text: str, summary_text: str) -> Tuple[bool, List[str]]:
    """
    Проверяет сохранность критических чисел в итоговом тексте
    
    Returns:
        Tuple[bool, List[str]]: (все_числа_сохранены, список_потерянных_чисел)
    """
    source_numbers = extract_critical_numbers(source_text)
    summary_numbers = extract_critical_numbers(summary_text)
    
    missing_numbers = []
    
    for source_num in source_numbers:
        found = False
        
        # Прямое совпадение
        if source_num in summary_numbers:
            found = True
        else:
            # Нечеткое совпадение (игнорируем пробелы и регистр)
            source_normalized = re.sub(r'[^\d,.\-–—%₽$€а-яa-z]', '', source_num.lower())
            
            for summary_num in summary_numbers:
                summary_normalized = re.sub(r'[^\d,.\-–—%₽$€а-яa-z]', '', summary_num.lower())
                if source_normalized == summary_normalized:
                    found = True
                    break
        
        if not found:
            missing_numbers.append(source_num)
    
    all_preserved = len(missing_numbers) == 0
    return all_preserved, missing_numbers


def assert_language(expected_lang: str, output_text: str) -> bool:
    """
    Проверяет, что выходной текст соответствует ожидаемому языку
    
    Args:
        expected_lang: 'ru' или 'en'
        output_text: Текст для проверки
        
    Returns:
        bool: True если язык совпадает
    """
    try:
        detector = LanguageDetectorBuilder.from_languages(
            Language.RUSSIAN, Language.ENGLISH
        ).build()
        
        detected = detector.detect_language_of(output_text)
        
        if detected == Language.RUSSIAN and expected_lang == 'ru':
            return True
        elif detected == Language.ENGLISH and expected_lang == 'en':
            return True
        else:
            logger.warning(f"Language mismatch: expected {expected_lang}, detected {detected}")
            return False
            
    except Exception as e:
        logger.warning(f"Language detection failed: {e}")
        # Fallback to simple heuristics
        if expected_lang == 'ru':
            # Проверяем наличие кириллицы
            return bool(re.search(r'[а-яё]', output_text.lower()))
        else:
            # Проверяем отсутствие кириллицы и наличие латиницы
            has_cyrillic = bool(re.search(r'[а-яё]', output_text.lower()))
            has_latin = bool(re.search(r'[a-z]', output_text.lower()))
            return not has_cyrillic and has_latin


def trim_to_length(text: str, target_chars: int, tolerance: float = 0.1) -> str:
    """
    Обрезает текст до целевой длины с учетом допуска
    
    Args:
        text: Исходный текст
        target_chars: Целевое количество символов
        tolerance: Допустимое превышение (10% по умолчанию)
        
    Returns:
        Обрезанный текст
    """
    max_length = int(target_chars * (1 + tolerance))
    
    if len(text) <= max_length:
        return text
    
    # Обрезаем по предложениям, если возможно
    sentences = re.split(r'[.!?]+', text)
    trimmed = ""
    
    for sentence in sentences:
        if len(trimmed + sentence) <= target_chars:
            trimmed += sentence + ". "
        else:
            break
    
    # Если не удалось обрезать по предложениям, обрезаем жестко
    if not trimmed.strip():
        trimmed = text[:target_chars] + "..."
    
    return trimmed.strip()


def validate_json_structure(json_data: Dict) -> Tuple[bool, List[str]]:
    """
    Проверяет структуру JSON ответа от LLM
    
    Returns:
        Tuple[bool, List[str]]: (структура_валидна, список_ошибок)
    """
    errors = []
    
    required_fields = ['bullets', 'key_facts', 'entities']
    
    for field in required_fields:
        if field not in json_data:
            errors.append(f"Missing required field: {field}")
    
    # Проверяем bullets
    if 'bullets' in json_data:
        if not isinstance(json_data['bullets'], list):
            errors.append("Field 'bullets' should be a list")
        elif len(json_data['bullets']) < 3:
            errors.append("Field 'bullets' should contain at least 3 items")
    
    # Проверяем key_facts
    if 'key_facts' in json_data:
        if not isinstance(json_data['key_facts'], list):
            errors.append("Field 'key_facts' should be a list")
        else:
            for i, fact in enumerate(json_data['key_facts']):
                if not isinstance(fact, dict):
                    errors.append(f"key_facts[{i}] should be a dict")
                elif 'value_raw' not in fact:
                    errors.append(f"key_facts[{i}] missing 'value_raw' field")
    
    # Проверяем entities
    if 'entities' in json_data:
        if not isinstance(json_data['entities'], dict):
            errors.append("Field 'entities' should be a dict")
        else:
            for entity_type in ['ORG', 'PERSON', 'GPE']:
                if entity_type in json_data['entities']:
                    if not isinstance(json_data['entities'][entity_type], list):
                        errors.append(f"entities.{entity_type} should be a list")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def check_summary_quality(source_text: str, summary_text: str, expected_lang: str, target_chars: int) -> Dict:
    """
    Комплексная проверка качества суммаризации
    
    Returns:
        {
            'numbers_preserved': bool,
            'missing_numbers': List[str],
            'language_correct': bool,
            'length_appropriate': bool,
            'actual_length': int,
            'quality_score': float  # 0-1
        }
    """
    # Проверка сохранности чисел
    numbers_preserved, missing_numbers = validate_numbers_preserved(source_text, summary_text)
    
    # Проверка языка
    language_correct = assert_language(expected_lang, summary_text)
    
    # Проверка длины
    actual_length = len(summary_text)
    length_appropriate = actual_length <= target_chars * 1.2  # 20% допуск
    
    # Вычисляем общий балл качества
    quality_score = 0.0
    if numbers_preserved:
        quality_score += 0.4  # 40% за сохранность чисел
    if language_correct:
        quality_score += 0.3   # 30% за правильный язык
    if length_appropriate:
        quality_score += 0.2   # 20% за соответствие длине
    
    # Бонус за отсутствие потерянных чисел
    if len(missing_numbers) == 0:
        quality_score += 0.1
    
    return {
        'numbers_preserved': numbers_preserved,
        'missing_numbers': missing_numbers,
        'language_correct': language_correct,
        'length_appropriate': length_appropriate,
        'actual_length': actual_length,
        'target_length': target_chars,
        'quality_score': min(quality_score, 1.0)
    }


def calculate_quality_score(original_text: str, summary: str) -> float:
    """
    Вычисляет общий балл качества суммаризации (0.0 - 1.0)
    """
    
    if not original_text or not summary:
        return 0.0
    
    scores = []
    
    try:
        # 1. Сохранность чисел (вес 0.4)
        numbers_preserved, missing = validate_numbers_preserved(original_text, summary)
        if numbers_preserved:
            number_score = 1.0
        else:
            source_numbers = extract_critical_numbers(original_text)
            if source_numbers:
                preservation_rate = 1 - (len(missing) / len(source_numbers))
                number_score = max(0, preservation_rate)
            else:
                number_score = 1.0  # Нет чисел для проверки
        scores.append(('numbers', number_score, 0.4))
        
        # 2. Адекватность сжатия (вес 0.2)
        compression_ratio = len(summary) / len(original_text)
        if 0.1 <= compression_ratio <= 0.6:
            compression_score = 1.0
        elif compression_ratio < 0.05:
            compression_score = 0.3  # Слишком сжато
        elif compression_ratio > 0.8:
            compression_score = 0.5  # Слишком длинно
        else:
            compression_score = 0.8
        scores.append(('compression', compression_score, 0.2))
        
        # 3. Языковая корректность (вес 0.2)
        lang_correct = validate_language(original_text, summary)
        lang_score = 1.0 if lang_correct else 0.3
        scores.append(('language', lang_score, 0.2))
        
        # 4. Структурированность (вес 0.1)
        structure_score = 0.8 if ('•' in summary or '—' in summary or '\n' in summary) else 0.6
        scores.append(('structure', structure_score, 0.1))
        
        # 5. Содержательность (вес 0.1)
        content_words = len([w for w in summary.split() if len(w) > 3])
        if content_words >= 10:
            content_score = 1.0
        elif content_words >= 5:
            content_score = 0.7
        else:
            content_score = 0.4
        scores.append(('content', content_score, 0.1))
        
        # Вычисляем взвешенную сумму
        weighted_score = sum(score * weight for name, score, weight in scores)
        
        logger.debug(f"Quality scores: {[(name, f'{score:.2f}', f'{weight:.1f}') for name, score, weight in scores]}")
        logger.debug(f"Final quality score: {weighted_score:.3f}")
        
        return round(weighted_score, 3)
        
    except Exception as e:
        logger.error(f"Ошибка расчета качества: {e}")
        return 0.5  # Средний балл при ошибке