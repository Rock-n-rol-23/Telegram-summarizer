"""
Модуль управления состояниями пользователей бота.

Централизованное хранение и управление состояниями пользователей,
заменяет разрозненные словари user_states, user_settings, user_messages_buffer.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, List, Any
from datetime import datetime


class UserStep(Enum):
    """Перечисление шагов пользовательского взаимодействия."""
    IDLE = "idle"
    WAITING_TEXT = "waiting_text"
    COMPRESSION_LEVEL = "compression_level"
    FORMAT_SELECTION = "format_selection"


@dataclass
class UserState:
    """
    Состояние одного пользователя.

    Attributes:
        step: Текущий шаг в процессе взаимодействия
        compression: Выбранный уровень сжатия (10, 30, 50)
        format: Формат вывода (bullets, paragraph, keywords)
        smart_mode: Включен ли режим умной суммаризации
        messages_buffer: Буфер сообщений для объединения
        last_activity: Время последней активности
    """
    step: UserStep = UserStep.IDLE
    compression: Optional[str] = "30"
    format: Optional[str] = "bullets"
    smart_mode: bool = True
    messages_buffer: List[Dict[str, Any]] = field(default_factory=list)
    last_activity: datetime = field(default_factory=datetime.now)

    def reset(self):
        """Сброс состояния пользователя к начальному."""
        self.step = UserStep.IDLE
        self.compression = "30"
        self.format = "bullets"
        self.smart_mode = True
        self.messages_buffer = []
        self.last_activity = datetime.now()

    def update_activity(self):
        """Обновление времени последней активности."""
        self.last_activity = datetime.now()


class StateManager:
    """
    Менеджер состояний пользователей.

    Централизованное управление состояниями всех пользователей бота.
    Заменяет три разных словаря на один унифицированный интерфейс.
    """

    def __init__(self):
        """Инициализация менеджера состояний."""
        self._states: Dict[int, UserState] = {}

    def get_state(self, user_id: int) -> UserState:
        """
        Получить состояние пользователя.

        Если состояние не существует - создает новое с настройками по умолчанию.

        Args:
            user_id: ID пользователя в Telegram

        Returns:
            Объект UserState с текущим состоянием пользователя
        """
        if user_id not in self._states:
            self._states[user_id] = UserState()

        # Обновляем время активности
        self._states[user_id].update_activity()
        return self._states[user_id]

    def clear_state(self, user_id: int) -> bool:
        """
        Очистить состояние пользователя.

        Args:
            user_id: ID пользователя в Telegram

        Returns:
            True если состояние было удалено, False если его не было
        """
        if user_id in self._states:
            del self._states[user_id]
            return True
        return False

    def reset_state(self, user_id: int):
        """
        Сбросить состояние пользователя к начальному.

        В отличие от clear_state, не удаляет объект UserState,
        а возвращает его к дефолтным значениям.

        Args:
            user_id: ID пользователя в Telegram
        """
        if user_id in self._states:
            self._states[user_id].reset()
        else:
            self._states[user_id] = UserState()

    def has_state(self, user_id: int) -> bool:
        """
        Проверить, есть ли состояние для пользователя.

        Args:
            user_id: ID пользователя в Telegram

        Returns:
            True если состояние существует
        """
        return user_id in self._states

    def get_all_user_ids(self) -> List[int]:
        """
        Получить список всех пользователей с активными состояниями.

        Returns:
            Список ID пользователей
        """
        return list(self._states.keys())

    def cleanup_inactive(self, max_age_hours: int = 24) -> int:
        """
        Очистить неактивные состояния.

        Удаляет состояния пользователей, которые не проявляли
        активность более max_age_hours часов.

        Args:
            max_age_hours: Максимальный возраст неактивных состояний в часах

        Returns:
            Количество удаленных состояний
        """
        from datetime import timedelta

        now = datetime.now()
        to_remove = []

        for user_id, state in self._states.items():
            if (now - state.last_activity) > timedelta(hours=max_age_hours):
                to_remove.append(user_id)

        for user_id in to_remove:
            del self._states[user_id]

        return len(to_remove)

    def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику по состояниям.

        Returns:
            Словарь со статистикой
        """
        total_users = len(self._states)

        step_counts = {}
        for state in self._states.values():
            step_name = state.step.value
            step_counts[step_name] = step_counts.get(step_name, 0) + 1

        smart_mode_count = sum(1 for s in self._states.values() if s.smart_mode)

        return {
            'total_users': total_users,
            'step_distribution': step_counts,
            'smart_mode_enabled': smart_mode_count
        }
