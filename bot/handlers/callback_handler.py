"""Обработчик callback queries (нажатия на inline кнопки)"""

import logging
from .base import BaseHandler

logger = logging.getLogger(__name__)


class CallbackHandler(BaseHandler):
    """Обработчик callback queries от inline кнопок"""

    def __init__(self, session, base_url, db, state_manager):
        super().__init__(session, base_url, db, state_manager)

    async def handle_callback_query(self, callback_query: dict):
        """Обработка callback query"""
        query_id = callback_query["id"]
        callback_data = callback_query.get("data", "")
        user_id = callback_query["from"]["id"]

        # Получаем chat_id из сообщения
        message = callback_query.get("message")
        if not message:
            await self.answer_callback_query(query_id, "❌ Ошибка: сообщение не найдено")
            return

        chat_id = message["chat"]["id"]
        message_id = message["message_id"]

        logger.info(f"Callback query от пользователя {user_id}: {callback_data}")

        try:
            # Обработка различных типов callback
            if callback_data.startswith("compression_"):
                await self.handle_compression_callback(
                    query_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("audio_format_"):
                await self.handle_audio_format_callback(
                    query_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("audio_verbosity_"):
                await self.handle_audio_verbosity_callback(
                    query_id, chat_id, message_id, user_id, callback_data
                )
            else:
                # Неизвестный callback
                await self.answer_callback_query(query_id, "⚠️ Неизвестная команда")
                logger.warning(f"Неизвестный callback_data: {callback_data}")

        except Exception as e:
            logger.error(f"Ошибка обработки callback query: {e}")
            await self.answer_callback_query(query_id, "❌ Произошла ошибка")

    async def handle_compression_callback(
        self, query_id: str, chat_id: int, message_id: int, user_id: int, callback_data: str
    ):
        """Обработка изменения уровня сжатия"""
        try:
            # Извлекаем уровень из callback_data (например: "compression_30")
            parts = callback_data.split("_")
            compression_level = int(parts[1])

            # Сохраняем в БД
            try:
                self.db.update_compression_level(user_id, compression_level, "")
                logger.info(f"Обновлен уровень сжатия для пользователя {user_id}: {compression_level}%")
            except Exception as e:
                logger.error(f"Ошибка сохранения уровня сжатия: {e}")
                await self.answer_callback_query(query_id, "❌ Ошибка сохранения настроек")
                return

            # Названия уровней
            level_names = {
                10: "🔥 Кратко",
                30: "📊 Сбалансированно",
                60: "📖 Подробно"
            }
            level_name = level_names.get(compression_level, f"{compression_level}%")

            # Отправляем подтверждение
            await self.answer_callback_query(
                query_id,
                f"✅ Установлен уровень: {level_name}",
                show_alert=False
            )

            # Обновляем сообщение с новыми кнопками
            confirmation_text = (
                f"✅ Стиль саммаризации изменён: {level_name}\n\n"
                f"Теперь твои тексты будут обрабатываться в стиле \"{level_name}\".\n\n"
                f"📝 Просто отправь текст, статью или документ!"
            )

            await self.edit_message_text(chat_id, message_id, confirmation_text)

        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка парсинга callback_data: {e}")
            await self.answer_callback_query(query_id, "❌ Неверный формат данных")

    async def handle_audio_format_callback(
        self, query_id: str, chat_id: int, message_id: int, user_id: int, callback_data: str
    ):
        """Обработка изменения формата аудио"""
        try:
            # Извлекаем формат из callback_data (например: "audio_format_detailed")
            format_type = callback_data.replace("audio_format_", "")

            # Проверяем доступность enhanced audio settings
            try:
                from bot.ui_settings import get_settings_manager

                settings_manager = get_settings_manager()
                if settings_manager:
                    settings_manager.update_user_format(user_id, format_type)
                    logger.info(
                        f"Обновлен формат аудио для пользователя {user_id}: {format_type}"
                    )

                    format_names = {
                        "detailed": "Подробный",
                        "concise": "Краткий",
                        "bullets": "Маркированный список"
                    }
                    format_name = format_names.get(format_type, format_type)

                    await self.answer_callback_query(
                        query_id, f"✅ Формат изменён: {format_name}"
                    )
                else:
                    await self.answer_callback_query(query_id, "❌ Настройки недоступны")
            except ImportError:
                await self.answer_callback_query(
                    query_id, "❌ Функция недоступна - обновите бота"
                )

        except Exception as e:
            logger.error(f"Ошибка обработки audio format callback: {e}")
            await self.answer_callback_query(query_id, "❌ Ошибка обработки")

    async def handle_audio_verbosity_callback(
        self, query_id: str, chat_id: int, message_id: int, user_id: int, callback_data: str
    ):
        """Обработка изменения детальности аудио"""
        try:
            # Извлекаем уровень verbosity
            verbosity_type = callback_data.replace("audio_verbosity_", "")

            try:
                from bot.ui_settings import get_settings_manager

                settings_manager = get_settings_manager()
                if settings_manager:
                    settings_manager.update_user_verbosity(user_id, verbosity_type)
                    logger.info(
                        f"Обновлена детальность аудио для пользователя {user_id}: {verbosity_type}"
                    )

                    verbosity_names = {
                        "high": "Высокая",
                        "medium": "Средняя",
                        "low": "Низкая"
                    }
                    verbosity_name = verbosity_names.get(verbosity_type, verbosity_type)

                    await self.answer_callback_query(
                        query_id, f"✅ Детальность изменена: {verbosity_name}"
                    )
                else:
                    await self.answer_callback_query(query_id, "❌ Настройки недоступны")
            except ImportError:
                await self.answer_callback_query(
                    query_id, "❌ Функция недоступна - обновите бота"
                )

        except Exception as e:
            logger.error(f"Ошибка обработки audio verbosity callback: {e}")
            await self.answer_callback_query(query_id, "❌ Ошибка обработки")

    async def answer_callback_query(
        self, query_id: str, text: str = "", show_alert: bool = False
    ):
        """Отправка ответа на callback query"""
        url = f"{self.base_url}/answerCallbackQuery"
        data = {"callback_query_id": query_id, "text": text, "show_alert": show_alert}

        async with self.session.post(url, json=data) as response:
            result = await response.json()
            if not result.get("ok"):
                logger.error(f"Ошибка answerCallbackQuery: {result}")
            return result
