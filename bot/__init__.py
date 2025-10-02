"""
Bot utilities package.

Модульная структура для Telegram бота-суммаризатора.
Содержит утилиты для управления состоянием пользователей и обработки текста.
"""

from .state_manager import StateManager, UserState, UserStep
from .text_utils import (
    normalize_text,
    extract_text_from_message,
    validate_text_length,
    truncate_text,
    count_words,
    extract_first_n_sentences
)

__all__ = [
    # State management
    'StateManager',
    'UserState',
    'UserStep',
    # Text utilities
    'normalize_text',
    'extract_text_from_message',
    'validate_text_length',
    'truncate_text',
    'count_words',
    'extract_first_n_sentences',
]

__version__ = '0.1.0'
