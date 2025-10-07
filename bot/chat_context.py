"""
Управление контекстом диалога с ботом
Позволяет пользователям задавать вопросы по последней суммаризации
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ChatContext:
    """Контекст диалога пользователя"""
    user_id: int
    original_text: str  # Исходный текст/транскрипт
    summary: str  # Суммаризация
    content_type: str  # 'audio', 'document', 'photo', 'text', 'youtube'
    timestamp: datetime = field(default_factory=datetime.now)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)

    def add_message(self, role: str, content: str):
        """Добавить сообщение в историю диалога"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def get_context_age_minutes(self) -> float:
        """Получить возраст контекста в минутах"""
        return (datetime.now() - self.timestamp).total_seconds() / 60

    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """Проверить, истек ли контекст"""
        return self.get_context_age_minutes() > timeout_minutes


class ChatContextManager:
    """Менеджер контекстов диалогов"""

    def __init__(self, context_timeout_minutes: int = 30, max_history_messages: int = 10):
        self.contexts: Dict[int, ChatContext] = {}
        self.context_timeout_minutes = context_timeout_minutes
        self.max_history_messages = max_history_messages

    def create_context(
        self,
        user_id: int,
        original_text: str,
        summary: str,
        content_type: str
    ) -> ChatContext:
        """Создать новый контекст для пользователя"""
        context = ChatContext(
            user_id=user_id,
            original_text=original_text,
            summary=summary,
            content_type=content_type
        )
        self.contexts[user_id] = context
        logger.info(f"📝 Создан новый контекст для пользователя {user_id}, тип: {content_type}")
        return context

    def get_context(self, user_id: int) -> Optional[ChatContext]:
        """Получить контекст пользователя"""
        context = self.contexts.get(user_id)

        if context is None:
            return None

        # Проверяем, не истек ли контекст
        if context.is_expired(self.context_timeout_minutes):
            logger.info(f"⏰ Контекст пользователя {user_id} истек, удаляем")
            self.clear_context(user_id)
            return None

        return context

    def has_active_context(self, user_id: int) -> bool:
        """Проверить, есть ли активный контекст у пользователя"""
        return self.get_context(user_id) is not None

    def add_user_message(self, user_id: int, message: str) -> bool:
        """Добавить сообщение пользователя в контекст"""
        context = self.get_context(user_id)
        if context is None:
            return False

        context.add_message("user", message)

        # Ограничиваем размер истории
        if len(context.conversation_history) > self.max_history_messages:
            context.conversation_history = context.conversation_history[-self.max_history_messages:]

        return True

    def add_assistant_message(self, user_id: int, message: str) -> bool:
        """Добавить ответ ассистента в контекст"""
        context = self.get_context(user_id)
        if context is None:
            return False

        context.add_message("assistant", message)

        # Ограничиваем размер истории
        if len(context.conversation_history) > self.max_history_messages:
            context.conversation_history = context.conversation_history[-self.max_history_messages:]

        return True

    def get_conversation_for_llm(self, user_id: int) -> Optional[List[Dict[str, str]]]:
        """
        Получить историю диалога в формате для LLM

        Returns:
            List of messages in format [{"role": "system", "content": "..."}, ...]
        """
        context = self.get_context(user_id)
        if context is None:
            return None

        # Формируем системное сообщение с контекстом
        system_message = f"""Ты - помощник по анализу контента. У тебя есть доступ к исходному тексту и его суммаризации.

📄 **Тип контента:** {context.content_type}

📝 **Суммаризация:**
{context.summary}

📋 **Исходный текст (для справки):**
{context.original_text[:3000]}{'...' if len(context.original_text) > 3000 else ''}

Отвечай на вопросы пользователя на основе этого контента. Будь конкретным, ссылайся на факты из текста.
Если информации нет в тексте - так и скажи."""

        messages = [{"role": "system", "content": system_message}]

        # Добавляем историю диалога
        for msg in context.conversation_history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        return messages

    def clear_context(self, user_id: int):
        """Очистить контекст пользователя"""
        if user_id in self.contexts:
            del self.contexts[user_id]
            logger.info(f"🗑️ Контекст пользователя {user_id} очищен")

    def cleanup_expired_contexts(self):
        """Очистить все истекшие контексты"""
        expired_users = [
            user_id
            for user_id, context in self.contexts.items()
            if context.is_expired(self.context_timeout_minutes)
        ]

        for user_id in expired_users:
            self.clear_context(user_id)

        if expired_users:
            logger.info(f"🗑️ Очищено {len(expired_users)} истекших контекстов")

    def get_stats(self) -> Dict:
        """Получить статистику по контекстам"""
        active_contexts = len(self.contexts)
        contexts_by_type = {}

        for context in self.contexts.values():
            content_type = context.content_type
            contexts_by_type[content_type] = contexts_by_type.get(content_type, 0) + 1

        return {
            "active_contexts": active_contexts,
            "contexts_by_type": contexts_by_type,
            "timeout_minutes": self.context_timeout_minutes
        }


# Глобальный экземпляр менеджера контекстов
chat_context_manager = ChatContextManager(
    context_timeout_minutes=30,  # Контекст живет 30 минут
    max_history_messages=10  # Максимум 10 сообщений в истории
)
