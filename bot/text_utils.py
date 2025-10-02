"""
Утилиты для обработки и нормализации текста.

Унифицированные функции для извлечения и нормализации текста из Telegram сообщений.
Заменяет дублирующийся код нормализации в разных частях simple_bot.py.
"""

import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def normalize_text(text: str, is_command: bool = False) -> Optional[str]:
    """
    Нормализация текста с удалением лишних пробелов и символов.

    Убирает избыточные пробелы, переносы строк, управляющие символы.
    Команды (начинающиеся с /) не нормализуются.

    Args:
        text: Исходный текст для нормализации
        is_command: Флаг, является ли текст командой (начинается с /)

    Returns:
        Нормализованный текст или None если текст слишком короткий

    Example:
        >>> normalize_text("  Привет   мир  \\n\\n\\n  ")
        "Привет мир"
        >>> normalize_text("/start  ", is_command=True)
        "/start"
    """
    if not text:
        return None

    # Команды не нормализуем, только trim
    if is_command or text.startswith('/'):
        return text.strip()

    try:
        # Удаляем управляющие символы (кроме \n)
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

        # Удаляем избыточные пробелы в начале и конце строк
        text = '\n'.join(line.strip() for line in text.split('\n'))

        # Заменяем множественные пробелы на одиночные
        text = re.sub(r' +', ' ', text)

        # Заменяем множественные переносы строк на двойные
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Убираем пробелы в начале и конце всего текста
        text = text.strip()

        # Проверка минимальной длины (только значимые символы)
        clean_text = ''.join(c for c in text if not c.isspace())
        if len(clean_text) < 5:
            logger.debug(f"Текст слишком короткий после нормализации: {len(clean_text)} символов")
            return None

        logger.debug(f"Текст нормализован: {len(text)} символов")
        return text

    except Exception as e:
        logger.error(f"Ошибка при нормализации текста: {e}")
        # В случае ошибки возвращаем исходный текст с trim
        return text.strip() if text else None


def extract_text_from_message(message: Dict[str, Any]) -> Optional[str]:
    """
    Извлечение и нормализация текста из Telegram сообщения.

    Поддерживает как обычный текст, так и caption (для медиа).
    Автоматически определяет, является ли текст командой.

    Args:
        message: Объект сообщения от Telegram API

    Returns:
        Нормализованный текст или None если текст отсутствует/невалиден

    Example:
        >>> message = {"text": "  /start  "}
        >>> extract_text_from_message(message)
        "/start"
        >>> message = {"caption": "Привет\\n\\n\\nмир"}
        >>> extract_text_from_message(message)
        "Привет\\n\\nмир"
    """
    # Извлекаем текст из сообщения
    text = message.get("text") or message.get("caption")

    if not text:
        logger.debug("Сообщение не содержит текста")
        return None

    logger.debug(f"Извлечен текст из сообщения: {len(text)} символов")

    # Определяем, является ли это командой
    is_command = text.lstrip().startswith('/')

    # Нормализуем и возвращаем
    return normalize_text(text, is_command)


def validate_text_length(
    text: str,
    min_length: int = 20,
    max_length: int = 50000
) -> tuple[bool, Optional[str]]:
    """
    Валидация длины текста для обработки.

    Args:
        text: Текст для проверки
        min_length: Минимальная допустимая длина (значимые символы)
        max_length: Максимальная допустимая длина (все символы)

    Returns:
        Кортеж (валиден, сообщение_об_ошибке)
        - (True, None) если текст валиден
        - (False, "error message") если невалиден

    Example:
        >>> validate_text_length("Привет")
        (False, "Текст слишком короткий: 6 символов. Минимум: 20 символов.")
        >>> validate_text_length("А" * 100)
        (True, None)
    """
    if not text:
        return False, "Текст пуст"

    # Считаем только значимые символы для минимума
    significant_chars = ''.join(c for c in text if not c.isspace())
    total_chars = len(text)

    if len(significant_chars) < min_length:
        return False, (
            f"Текст слишком короткий: {len(significant_chars)} символов. "
            f"Минимум: {min_length} символов."
        )

    if total_chars > max_length:
        return False, (
            f"Текст слишком длинный: {total_chars:,} символов. "
            f"Максимум: {max_length:,} символов."
        )

    return True, None


def truncate_text(text: str, max_length: int = 4096, suffix: str = "...") -> str:
    """
    Обрезка текста до максимальной длины с добавлением суффикса.

    Используется для соблюдения лимитов Telegram API (4096 символов).

    Args:
        text: Исходный текст
        max_length: Максимальная длина (включая suffix)
        suffix: Суффикс для добавления если текст обрезан

    Returns:
        Обрезанный текст

    Example:
        >>> truncate_text("А" * 5000, max_length=100)
        "ААААА...ААААА..." (длина 100)
    """
    if len(text) <= max_length:
        return text

    # Учитываем длину суффикса
    effective_length = max_length - len(suffix)
    if effective_length <= 0:
        return suffix[:max_length]

    return text[:effective_length] + suffix


def count_words(text: str) -> int:
    """
    Подсчет количества слов в тексте.

    Args:
        text: Текст для подсчета

    Returns:
        Количество слов

    Example:
        >>> count_words("Привет мир! Как дела?")
        4
    """
    if not text:
        return 0

    # Разбиваем по пробелам и фильтруем пустые строки
    words = [word for word in text.split() if word.strip()]
    return len(words)


def extract_first_n_sentences(text: str, n: int = 3) -> str:
    """
    Извлечение первых N предложений из текста.

    Используется для быстрой суммаризации без AI.

    Args:
        text: Исходный текст
        n: Количество предложений для извлечения

    Returns:
        Первые N предложений

    Example:
        >>> extract_first_n_sentences("Привет. Как дела? Всё хорошо. Спасибо.", n=2)
        "Привет. Как дела?"
    """
    if not text:
        return ""

    # Разбиваем на предложения по знакам препинания
    sentences = re.split(r'[.!?]+', text)

    # Фильтруем пустые и короткие предложения
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    # Берем первые N
    selected = sentences[:n]

    # Собираем обратно
    result = '. '.join(selected)

    # Добавляем точку в конце если нужно
    if result and not result.endswith('.'):
        result += '.'

    return result
