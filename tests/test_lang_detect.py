"""
Tests for language detection functionality
"""

import pytest
from utils.language_detect import detect_language_simple, get_language_info, get_chunking_params

def test_russian_detection():
    """Test Russian text detection"""
    russian_text = "Привет, как дела? Это русский текст для тестирования."
    assert detect_language_simple(russian_text) == 'ru'

def test_english_detection():
    """Test English text detection"""
    english_text = "Hello, how are you? This is English text for testing."
    assert detect_language_simple(english_text) == 'en'

def test_mixed_text_mostly_russian():
    """Test mixed text with mostly Russian"""
    mixed_text = "Привет! This is mixed text, но больше русского."
    assert detect_language_simple(mixed_text) == 'ru'

def test_mixed_text_mostly_english():
    """Test mixed text with mostly English"""
    mixed_text = "Hello! Это mixed text, but mostly English words here."
    assert detect_language_simple(mixed_text) == 'en'

def test_short_text():
    """Test very short text defaults to English"""
    assert detect_language_simple("Hi") == 'en'
    assert detect_language_simple("") == 'en'

def test_language_info():
    """Test language info retrieval"""
    ru_info = get_language_info('ru')
    assert ru_info['name'] == 'Russian'
    assert 'Цифры и факты' in ru_info['numbers_header']
    
    en_info = get_language_info('en')
    assert en_info['name'] == 'English'
    assert 'Numbers and Facts' in en_info['numbers_header']

def test_chunking_params():
    """Test chunking parameter calculation"""
    russian_text = "Это русский текст для тестирования алгоритма чанкинга."
    params = get_chunking_params(russian_text, 1000)
    
    assert params['language'] in ['ru', 'en']
    assert params['max_chars'] > 0
    assert params['overlap_chars'] > 0