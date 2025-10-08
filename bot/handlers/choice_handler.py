"""Обработчик выбора между обработкой фото и ссылки"""

import logging
from typing import Dict, Optional
from .base import BaseHandler
import re

logger = logging.getLogger(__name__)


class ChoiceHandler(BaseHandler):
    """Обработчик диалога выбора между фото и ссылкой"""

    def __init__(
        self,
        session,
        base_url,
        db,
        state_manager,
        photo_handler,
        text_handler,
        url_processor
    ):
        super().__init__(session, base_url, db, state_manager)
        self.photo_handler = photo_handler
        self.text_handler = text_handler
        self.url_processor = url_processor

        # Кэш сообщений пользователей для обработки после выбора
        self.pending_choices: Dict[int, dict] = {}

    async def handle_photo_with_url(self, update: dict, urls: list):
        """
        Обработка сообщения с фото и URL

        Args:
            update: Telegram update object
            urls: Список найденных URL в caption
        """
        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]

        logger.info(f"Пользователь {user_id} отправил фото с {len(urls)} URL")

        # Сохраняем сообщение для последующей обработки
        self.pending_choices[user_id] = {
            "update": update,
            "urls": urls,
            "message_id": message["message_id"]
        }

        # Создаем inline клавиатуру для выбора
        keyboard = self._create_choice_keyboard(len(urls))

        # Формируем сообщение с вопросом
        if len(urls) == 1:
            choice_text = f"""🤔 **Что обработать?**

Вы отправили фото с текстом, содержащим ссылку:
{urls[0]}

Выберите, что вы хотите обработать:"""
        else:
            urls_text = '\n'.join(f"{i+1}. {url}" for i, url in enumerate(urls))
            choice_text = f"""🤔 **Что обработать?**

Вы отправили фото с текстом, содержащим {len(urls)} ссылки:
{urls_text}

Выберите, что вы хотите обработать:"""

        # Отправляем сообщение с выбором
        await self.send_message(chat_id, choice_text, reply_markup=keyboard)

    async def handle_choice_callback(self, callback_query: dict):
        """
        Обработка callback от inline кнопок выбора

        Args:
            callback_query: Callback query от Telegram
        """
        user_id = callback_query["from"]["id"]
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]
        choice = callback_query["data"]

        logger.info(f"Пользователь {user_id} выбрал: {choice}")

        # Проверяем наличие сохраненного выбора
        if user_id not in self.pending_choices:
            await self.edit_message_text(
                chat_id,
                message_id,
                "❌ Выбор устарел. Отправьте сообщение заново."
            )
            return

        # Получаем сохраненные данные
        pending = self.pending_choices[user_id]
        update = pending["update"]
        urls = pending["urls"]

        # Удаляем из кэша
        del self.pending_choices[user_id]

        # Удаляем сообщение с выбором
        await self.delete_message(chat_id, message_id)

        # Обрабатываем выбор
        if choice == "choice_photo":
            # Обрабатываем фото
            await self.photo_handler.handle_photo_message(update)

        elif choice == "choice_url":
            # Обрабатываем URL
            await self._process_urls(update, urls)

        else:
            logger.warning(f"Неизвестный выбор: {choice}")

    async def _process_urls(self, update: dict, urls: list):
        """
        Обработка URL из сообщения

        Args:
            update: Telegram update object
            urls: Список URL для обработки
        """
        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]

        # Отправляем сообщение о начале обработки
        processing_msg = await self.send_message(
            chat_id,
            f"🔗 Обрабатываю {len(urls)} ссылку(и)...\n\n⏳ Загружаю и парсю контент..."
        )
        processing_msg_id = processing_msg.get("result", {}).get("message_id") if processing_msg else None

        # Обрабатываем каждый URL
        all_text = []
        titles = []

        for i, url in enumerate(urls):
            # Обновляем прогресс
            if processing_msg_id and len(urls) > 1:
                await self.edit_message_text(
                    chat_id,
                    processing_msg_id,
                    f"🔗 Обрабатываю ссылку {i+1}/{len(urls)}...\n\n⏳ Загружаю контент из {url}"
                )

            # Парсим URL
            text, title = await self.url_processor.process_url(url)

            if text:
                all_text.append(text)
                if title:
                    titles.append(title)
                logger.info(f"Успешно обработан URL {url}: {len(text)} символов")
            else:
                logger.warning(f"Не удалось извлечь текст из URL {url}")

        # Удаляем сообщение о обработке
        if processing_msg_id:
            await self.delete_message(chat_id, processing_msg_id)

        # Проверяем результат
        if not all_text:
            await self.send_message(
                chat_id,
                "❌ Не удалось извлечь текст из указанных ссылок!\n\n"
                "Убедитесь, что ссылки ведут на доступные веб-страницы."
            )
            return

        # Объединяем весь текст
        combined_text = "\n\n---\n\n".join(all_text)

        # Создаем временное update с текстом для обработки через TextHandler
        modified_update = {
            "message": {
                **update["message"],
                "text": combined_text
            }
        }

        # Передаем в TextHandler для суммаризации
        await self.text_handler.handle_text_message(modified_update, message_text=combined_text)

    def _create_choice_keyboard(self, url_count: int) -> dict:
        """
        Создает inline клавиатуру для выбора

        Args:
            url_count: Количество URL

        Returns:
            Inline keyboard markup
        """
        url_text = f"🔗 Обработать ссылку" if url_count == 1 else f"🔗 Обработать {url_count} ссылки"

        buttons = [
            [
                {
                    "text": "🖼️ Обработать фото",
                    "callback_data": "choice_photo"
                }
            ],
            [
                {
                    "text": url_text,
                    "callback_data": "choice_url"
                }
            ]
        ]

        return {"inline_keyboard": buttons}

    async def delete_message(self, chat_id: int, message_id: int):
        """Удаление сообщения"""
        try:
            url = f"{self.base_url}/deleteMessage"
            data = {"chat_id": chat_id, "message_id": message_id}

            async with self.session.post(url, json=data) as response:
                result = await response.json()
                return result.get("ok", False)
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
            return False

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[dict] = None
    ):
        """Редактирование текста сообщения"""
        try:
            url = f"{self.base_url}/editMessageText"
            data = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text
            }
            if reply_markup:
                data["reply_markup"] = reply_markup

            async with self.session.post(url, json=data) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
            return None
