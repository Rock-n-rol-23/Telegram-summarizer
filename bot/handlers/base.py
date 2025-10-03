"""Базовый класс для обработчиков сообщений"""

import logging
from typing import Optional, TYPE_CHECKING
import aiohttp

if TYPE_CHECKING:
    from database import DatabaseManager
    from bot.state_manager import StateManager

logger = logging.getLogger(__name__)


class BaseHandler:
    """Базовый класс для всех обработчиков"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        db: 'DatabaseManager',
        state_manager: 'StateManager'
    ):
        self.session = session
        self.base_url = base_url
        self.db = db
        self.state_manager = state_manager
        self.logger = logger

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[dict] = None
    ) -> Optional[dict]:
        """Отправить сообщение пользователю"""
        url = f"{self.base_url}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text
        }

        if parse_mode:
            payload['parse_mode'] = parse_mode
        if reply_markup:
            payload['reply_markup'] = reply_markup

        try:
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    self.logger.error(f"Ошибка отправки сообщения: {error_text}")
                    return None
        except Exception as e:
            self.logger.error(f"Исключение при отправке сообщения: {e}")
            return None

    async def send_chat_action(self, chat_id: int, action: str = "typing"):
        """Отправить статус 'печатает...'"""
        url = f"{self.base_url}/sendChatAction"
        payload = {'chat_id': chat_id, 'action': action}

        try:
            async with self.session.post(url, json=payload) as response:
                return response.status == 200
        except Exception as e:
            self.logger.error(f"Ошибка отправки chat action: {e}")
            return False

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[dict] = None
    ) -> Optional[dict]:
        """Редактировать сообщение"""
        url = f"{self.base_url}/editMessageText"
        payload = {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text
        }

        if parse_mode:
            payload['parse_mode'] = parse_mode
        if reply_markup:
            payload['reply_markup'] = reply_markup

        try:
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    self.logger.error(f"Ошибка редактирования сообщения: {error_text}")
                    return None
        except Exception as e:
            self.logger.error(f"Исключение при редактировании сообщения: {e}")
            return None

    def get_user_id(self, update: dict) -> Optional[int]:
        """Получить user_id из update"""
        if 'message' in update:
            return update['message'].get('from', {}).get('id')
        elif 'callback_query' in update:
            return update['callback_query'].get('from', {}).get('id')
        return None

    def get_chat_id(self, update: dict) -> Optional[int]:
        """Получить chat_id из update"""
        if 'message' in update:
            return update['message'].get('chat', {}).get('id')
        elif 'callback_query' in update:
            return update['callback_query'].get('message', {}).get('chat', {}).get('id')
        return None
