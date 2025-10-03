"""Декораторы для обработки ошибок и retry логики"""

import time
import logging
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)


def retry_on_failure(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Декоратор для retry с экспоненциальным backoff

    Args:
        max_retries: Максимальное количество попыток
        delay: Начальная задержка в секундах
        backoff: Множитель для экспоненциального backoff
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    # Проверяем, стоит ли повторять
                    if attempt < max_retries - 1:
                        # Логируем только для важных ошибок
                        error_msg = str(e).lower()
                        if any(keyword in error_msg for keyword in ['rate limit', 'timeout', 'connection', 'temporary']):
                            logger.warning(f"Попытка {attempt + 1}/{max_retries} не удалась: {e}. Повтор через {current_delay:.1f}s")
                            time.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            # Не повторяем для критичных ошибок (invalid key, etc)
                            raise
                    else:
                        logger.error(f"Все {max_retries} попыток исчерпаны")

            # Если все попытки исчерпаны, пробрасываем последнюю ошибку
            raise last_exception

        return wrapper
    return decorator
