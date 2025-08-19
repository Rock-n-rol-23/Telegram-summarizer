"""
Модуль для извлечения контента с веб-страниц
Многоступенчатый пайплайн: trafilatura → readability-lxml → bs4-эвристики
"""

from .web_extractor import extract_url, ExtractedPage

__all__ = ['extract_url', 'ExtractedPage']