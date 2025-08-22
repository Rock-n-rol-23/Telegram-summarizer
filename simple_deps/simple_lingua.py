"""
Простой детектор языка для замены lingua
"""

import re
from enum import Enum
from typing import Optional

class Language(Enum):
    RUSSIAN = "ru"
    ENGLISH = "en"
    UNKNOWN = "unknown"

class LanguageDetectorBuilder:
    def __init__(self, languages=None):
        self.languages = languages or [Language.RUSSIAN, Language.ENGLISH]
    
    @classmethod
    def from_languages(cls, *languages):
        return cls(list(languages))
    
    def build(self):
        return SimpleLanguageDetector(self.languages)

class SimpleLanguageDetector:
    def __init__(self, languages):
        self.languages = languages
    
    def detect_language_of(self, text: str) -> Language:
        """Простая детекция языка на основе кириллицы/латиницы"""
        
        if not text or not text.strip():
            return Language.UNKNOWN
        
        # Считаем кириллические и латинские символы
        cyrillic_count = len(re.findall(r'[а-яё]', text.lower()))
        latin_count = len(re.findall(r'[a-z]', text.lower()))
        
        total_letters = cyrillic_count + latin_count
        
        if total_letters == 0:
            return Language.UNKNOWN
        
        cyrillic_ratio = cyrillic_count / total_letters
        
        # Если больше 30% кириллицы - считаем русским
        if cyrillic_ratio > 0.3:
            return Language.RUSSIAN
        elif latin_count > 0:
            return Language.ENGLISH
        else:
            return Language.UNKNOWN