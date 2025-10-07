"""Обработчик фотографий и изображений"""

import logging
import time
import sqlite3
from typing import Dict, Set, Optional
from .base import BaseHandler
from bot.core.decorators import retry_on_failure
from llm.provider_router import analyze_image
from config import config

logger = logging.getLogger(__name__)


class PhotoHandler(BaseHandler):
    """Обработчик фотографий и изображений через Gemini Vision"""

    def __init__(
        self,
        session,
        base_url,
        db,
        state_manager,
        user_requests: Dict,
        processing_users: Set,
        db_executor
    ):
        super().__init__(session, base_url, db, state_manager)
        self.user_requests = user_requests
        self.processing_users = processing_users
        self.db_executor = db_executor

    async def handle_photo_message(self, update: dict):
        """Обработка фотографий через Gemini Vision"""
        try:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            username = message["from"].get("username", "")
            photo = message["photo"][-1]  # Берем самое большое разрешение

            # Проверка лимита запросов
            if not self.check_user_rate_limit(user_id):
                await self.send_message(
                    chat_id,
                    "⏰ Превышен лимит запросов!\n\n"
                    "Пожалуйста, подождите минуту перед отправкой нового изображения. "
                    "Лимит: 10 запросов в минуту."
                )
                return

            # Проверка на повторную обработку
            if user_id in self.processing_users:
                await self.send_message(
                    chat_id,
                    "⚠️ Обработка в процессе!\n\n"
                    "Пожалуйста, дождитесь завершения предыдущего запроса."
                )
                return

            # Добавляем пользователя в список обрабатываемых
            self.processing_users.add(user_id)

            logger.info(f"Получено фото от пользователя {user_id}")

            # Отправляем сообщение о начале обработки
            processing_message = await self.send_message(
                chat_id,
                "🖼️ Анализирую изображение...\n\n⏳ Распознаю текст и визуальные элементы..."
            )
            processing_message_id = (
                processing_message.get("result", {}).get("message_id")
                if processing_message and processing_message.get("ok")
                else None
            )

            try:
                # Получаем информацию о файле от Telegram
                file_info_response = await self.get_file_info(photo["file_id"])
                if not file_info_response or not file_info_response.get("ok"):
                    await self.send_message(chat_id, "❌ Не удалось получить информацию о фото")
                    return

                file_info = file_info_response["result"]
                file_path = f"https://api.telegram.org/file/bot{self.base_url.split('/bot')[1].split('/')[0]}/{file_info['file_path']}"

                # Обновляем сообщение о прогрессе
                if processing_message_id:
                    await self.edit_message_text(
                        chat_id,
                        processing_message_id,
                        "🖼️ Анализирую изображение...\n\n📥 Скачиваю фото..."
                    )

                # Скачиваем изображение
                async with self.session.get(file_path) as response:
                    if response.status != 200:
                        await self.send_message(chat_id, "❌ Не удалось скачать изображение")
                        return
                    image_data = await response.read()

                # Обновляем прогресс
                if processing_message_id:
                    await self.edit_message_text(
                        chat_id,
                        processing_message_id,
                        "🖼️ Анализирую изображение...\n\n🤖 Распознаю с помощью Gemini Vision..."
                    )

                # Получаем caption если есть (дополнительный контекст)
                caption = message.get("caption", "")

                # Формируем промпт
                if caption:
                    analysis_prompt = f"{config.IMAGE_ANALYSIS_PROMPT}\n\nДополнительный контекст от пользователя: {caption}"
                else:
                    analysis_prompt = config.IMAGE_ANALYSIS_PROMPT

                # Анализируем изображение через Gemini Vision
                try:
                    analysis_result = analyze_image(
                        image_data=image_data,
                        prompt=analysis_prompt,
                        temperature=0.3,
                        max_tokens=2000
                    )

                    if analysis_result:
                        # Формируем итоговый ответ
                        response_text = f"""🖼️ **Анализ изображения**

{analysis_result}

📊 **Информация:**
• Размер: {photo.get('width', 0)}×{photo.get('height', 0)} px
• Метод: Gemini Vision AI"""

                        # Удаляем сообщение о обработке
                        if processing_message_id:
                            await self.delete_message(chat_id, processing_message_id)

                        await self.send_message(chat_id, response_text)

                        # Сохраняем в базу данных
                        try:
                            await self._run_in_executor(
                                self.db.save_user_request,
                                user_id,
                                f"photo_analysis",
                                len(analysis_result),
                                len(analysis_result),
                                0.0,
                                'gemini_vision'
                            )
                        except (OSError, sqlite3.Error) as save_error:
                            logger.error(f"Ошибка сохранения запроса в БД: {save_error}")

                        logger.info(f"Успешно проанализировано фото пользователя {user_id}")

                    else:
                        if processing_message_id:
                            await self.delete_message(chat_id, processing_message_id)
                        await self.send_message(
                            chat_id,
                            "❌ Не удалось проанализировать изображение!\n\n"
                            "Попробуйте позже или отправьте другое фото."
                        )

                except NotImplementedError:
                    # Fallback на OCR если Gemini недоступен
                    if processing_message_id:
                        await self.edit_message_text(
                            chat_id,
                            processing_message_id,
                            "🖼️ Анализирую изображение...\n\n👁️ Использую OCR (Gemini недоступен)..."
                        )

                    # Здесь можно добавить fallback на OCR
                    await self.send_message(
                        chat_id,
                        "⚠️ Gemini Vision временно недоступен.\n\n"
                        "Отправьте изображение как документ для обработки через OCR."
                    )

            except (sqlite3.Error, ValueError) as e:
                logger.error(f"Ошибка при обработке фото: {e}")
                if processing_message_id:
                    await self.delete_message(chat_id, processing_message_id)
                await self.send_message(
                    chat_id,
                    "❌ Произошла ошибка при обработке изображения!\n\n"
                    "Пожалуйста, попробуйте позже."
                )

        except Exception as e:
            logger.error(f"Общая ошибка при обработке фото: {e}")
            await self.send_message(
                chat_id,
                "❌ Произошла ошибка!\n\nПожалуйста, попробуйте позже."
            )

        finally:
            # Удаляем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)

    # ============ Вспомогательные методы ============

    async def get_file_info(self, file_id: str):
        """Получает информацию о файле от Telegram API"""
        try:
            url = f"{self.base_url}/getFile"
            params = {"file_id": file_id}

            async with self.session.get(url, params=params) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Ошибка получения информации о файле: {e}")
            return None

    def check_user_rate_limit(self, user_id: int) -> bool:
        """Проверка лимита запросов пользователя (10 запросов в минуту)"""
        now = time.time()
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []

        # Удаляем запросы старше 1 минуты
        self.user_requests[user_id] = [
            req_time
            for req_time in self.user_requests[user_id]
            if now - req_time < 60
        ]

        # Проверяем лимит (10 запросов в минуту)
        if len(self.user_requests[user_id]) >= 10:
            return False

        self.user_requests[user_id].append(now)
        return True

    async def _run_in_executor(self, func, *args):
        """Запуск синхронной функции в executor"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.db_executor, func, *args)

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
        parse_mode: Optional[str] = None
    ):
        """Редактирование текста сообщения"""
        try:
            url = f"{self.base_url}/editMessageText"
            data = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text
            }
            if parse_mode:
                data["parse_mode"] = parse_mode

            async with self.session.post(url, json=data) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
            return None
