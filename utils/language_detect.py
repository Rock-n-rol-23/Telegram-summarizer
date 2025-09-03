"""
Simple heuristic language detection for Russian/English
Avoids external API calls by using character-based detection
"""

import re
from typing import Optional

def detect_language_simple(text: str) -> str:
    """
    Simple heuristic language detection for RU/EN
    
    Args:
        text: Input text to analyze
        
    Returns:
        'ru' for Russian, 'en' for English
    """
    if not text or len(text.strip()) < 3:
        return 'en'  # Default to English for very short texts
    
    # Remove punctuation, digits, and whitespace for analysis
    clean_text = re.sub(r'[^\w\s]', '', text.lower())
    clean_text = re.sub(r'\d+', '', clean_text)
    clean_text = re.sub(r'\s+', '', clean_text)
    
    if len(clean_text) < 3:
        return 'en'
    
    # Count Cyrillic characters
    cyrillic_chars = len(re.findall(r'[а-яё]', clean_text))
    
    # Count Latin characters  
    latin_chars = len(re.findall(r'[a-z]', clean_text))
    
    total_letters = cyrillic_chars + latin_chars
    
    if total_letters == 0:
        return 'en'
    
    # If more than 15% are Cyrillic, consider it Russian
    cyrillic_ratio = cyrillic_chars / total_letters
    
    if cyrillic_ratio > 0.15:
        return 'ru'
    else:
        return 'en'

def get_language_info(lang_code: str) -> dict:
    """Get language-specific information"""
    languages = {
        'ru': {
            'name': 'Russian',
            'native_name': 'Русский',
            'bullet': '•',
            'numbers_header': '🔢 Цифры и факты',
            'summary_intro': 'Краткое изложение:',
            'key_points': 'Ключевые моменты:'
        },
        'en': {
            'name': 'English', 
            'native_name': 'English',
            'bullet': '•',
            'numbers_header': '🔢 Numbers and Facts',
            'summary_intro': 'Summary:',
            'key_points': 'Key Points:'
        }
    }
    
    return languages.get(lang_code, languages['en'])

def get_chunking_params(text: str, target_tokens: int = 3000) -> dict:
    """
    Get chunking parameters based on text characteristics
    
    Args:
        text: Input text
        target_tokens: Target tokens per chunk
        
    Returns:
        Dict with chunking parameters
    """
    # Rough token estimation: 1 token ≈ 4 characters for English, 3 for Russian
    lang = detect_language_simple(text)
    chars_per_token = 3 if lang == 'ru' else 4
    
    target_chars = target_tokens * chars_per_token
    overlap_chars = 300 * chars_per_token  # 300 tokens overlap
    
    return {
        'max_chars': target_chars,
        'overlap_chars': overlap_chars,
        'language': lang
    }