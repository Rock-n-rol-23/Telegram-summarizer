"""
Модуль для детекции языка текста (RU/EN)
"""
import re
from typing import Literal
from lingua import Language, LanguageDetectorBuilder

# Инициализация детектора языка для RU и EN
detector = LanguageDetectorBuilder.from_languages(Language.RUSSIAN, Language.ENGLISH).build()

def detect_lang(text: str) -> Literal['ru', 'en']:
    """
    Определяет язык текста (русский или английский)
    
    Args:
        text: Входной текст для анализа
        
    Returns:
        'ru' для русского языка, 'en' для английского
    """
    if not text or len(text.strip()) < 10:
        # Для очень коротких текстов используем эвристику
        return _fallback_detection(text)
    
    try:
        # Основная детекция через lingua
        detected = detector.detect_language_of(text)
        if detected == Language.RUSSIAN:
            return 'ru'
        elif detected == Language.ENGLISH:
            return 'en'
        else:
            # Fallback к эвристике если lingua не уверена
            return _fallback_detection(text)
    except Exception:
        # В случае ошибки используем эвристику
        return _fallback_detection(text)

def _fallback_detection(text: str) -> Literal['ru', 'en']:
    """
    Простая эвристическая детекция для коротких текстов
    """
    if not text:
        return 'en'  # По умолчанию английский
    
    # Подсчет кириллических и латинских символов
    cyrillic_count = len(re.findall(r'[а-яё]', text.lower()))
    latin_count = len(re.findall(r'[a-z]', text.lower()))
    
    # Если есть кириллица - скорее всего русский
    if cyrillic_count > 0:
        return 'ru'
    
    # Если больше латинских символов - английский
    if latin_count > cyrillic_count:
        return 'en'
    
    # По умолчанию английский
    return 'en'

def is_ru(text: str) -> bool:
    """Проверяет, является ли текст русским"""
    return detect_lang(text) == 'ru'

def is_en(text: str) -> bool:
    """Проверяет, является ли текст английским"""
    return detect_lang(text) == 'en'