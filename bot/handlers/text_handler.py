"""Обработчик текстовых сообщений"""

import logging
import time
import sqlite3
from typing import Dict, Set, Optional
from datetime import datetime
from .base import BaseHandler

logger = logging.getLogger(__name__)


class TextHandler(BaseHandler):
    """Обработчик текстовых сообщений и кастомной суммаризации"""

    def __init__(
        self,
        session,
        base_url,
        db,
        state_manager,
        groq_client,
        openrouter_client,
        smart_summarizer,
        user_requests: Dict,
        processing_users: Set,
        user_states: Dict,
        user_settings: Dict,
        user_messages_buffer: Dict,
        db_executor
    ):
        super().__init__(session, base_url, db, state_manager)
        self.groq_client = groq_client
        self.openrouter_client = openrouter_client
        self.smart_summarizer = smart_summarizer
        self.user_requests = user_requests
        self.processing_users = processing_users
        self.user_states = user_states
        self.user_settings = user_settings
        self.user_messages_buffer = user_messages_buffer
        self.db_executor = db_executor

    async def handle_text_message(self, update: dict, message_text: Optional[str] = None):
        """Обработка текстовых сообщений"""
        from bot.text_utils import extract_text_from_message

        chat_id = update["message"]["chat"]["id"]
        user = update["message"]["from"]
        user_id = user["id"]
        username = user.get("username", "")

        # Используем переданный текст или извлекаем из сообщения
        if message_text:
            text = message_text
        else:
            text = extract_text_from_message(update["message"])
            if not text:
                logger.error("Не удалось извлечь текст из сообщения")
                return

        logger.info(f"Получен текст от пользователя {user_id} ({username}), длина: {len(text)} символов")

        # Проверка лимита запросов
        if not self.check_user_rate_limit(user_id):
            await self.send_message(
                chat_id,
                "⏰ Превышен лимит запросов!\n\n"
                "Пожалуйста, подождите минуту перед отправкой нового текста. Лимит: 10 запросов в минуту."
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

        # Проверка минимальной длины текста
        if len(text) < 50:
            await self.send_message(
                chat_id,
                f"📝 Текст слишком короткий!\n\n"
                f"Для качественной суммаризации нужно минимум 50 символов.\n"
                f"Ваш текст: {len(text)} символов."
            )
            return

        # Добавляем пользователя в список обрабатываемых
        self.processing_users.add(user_id)

        try:
            # Отправляем сообщение о начале обработки
            processing_response = await self.send_message(
                chat_id,
                "🤖 Обрабатываю ваш текст...\n\nЭто может занять несколько секунд."
            )
            processing_message_id = (
                processing_response.get("result", {}).get("message_id")
                if processing_response
                else None
            )

            start_time = time.time()

            # Получаем уровень сжатия пользователя из базы данных
            user_compression_level = await self.get_user_compression_level(user_id)
            target_ratio = user_compression_level / 100.0

            # Выполняем суммаризацию с пользовательскими настройками
            summary = await self.summarize_text(text, target_ratio=target_ratio)

            processing_time = time.time() - start_time

            if summary and not summary.startswith("❌"):
                # Сохраняем запрос в базу данных (неблокирующая запись)
                try:
                    await self._run_in_executor(
                        self.db.save_user_request,
                        user_id,
                        username,
                        len(text),
                        len(summary),
                        processing_time,
                        "groq",
                    )
                except (OSError, sqlite3.Error) as save_error:
                    logger.error(f"Ошибка сохранения запроса в БД: {save_error}")

                # Вычисляем статистику
                compression_ratio = len(summary) / len(text)

                # Формируем ответ
                response_text = f"""📋 Саммари готово! (Уровень сжатия: {user_compression_level}%)

{summary}

📊 Статистика:
• Исходный текст: {len(text):,} символов
• Саммари: {len(summary):,} символов
• Сжатие: {compression_ratio:.1%}
• Время обработки: {processing_time:.1f}с"""

                # Удаляем сообщение о обработке
                if processing_message_id:
                    await self.delete_message(chat_id, processing_message_id)

                # Создаем inline клавиатуру с кнопками уровней сжатия
                keyboard = self._get_compression_keyboard(user_compression_level)

                await self.send_message(chat_id, response_text, reply_markup=keyboard)

                logger.info(
                    f"Успешно обработан текст пользователя {user_id}, сжатие: {compression_ratio:.1%}"
                )

            else:
                # Удаляем сообщение о обработке
                if processing_message_id:
                    await self.delete_message(chat_id, processing_message_id)

                await self.send_message(
                    chat_id,
                    "❌ Ошибка при обработке текста!\n\n"
                    "Попробуйте позже или обратитесь к администратору.",
                )

                logger.error(f"Не удалось обработать текст пользователя {user_id}")

        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Ошибка при обработке текста пользователя {user_id}: {str(e)}")

            await self.send_message(
                chat_id, f"❌ Произошла ошибка!\n\nПожалуйста, попробуйте позже."
            )

        finally:
            # Удаляем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)

    async def handle_custom_summarize_text(self, update: dict, text: str):
        """Обработка текста в режиме настраиваемой суммаризации"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]

        try:
            # Добавляем текст в буфер сообщений пользователя
            self.user_messages_buffer[user_id].append(
                {
                    "text": text,
                    "timestamp": datetime.now(),
                    "is_forwarded": "forward_from" in update["message"]
                    or "forward_from_chat" in update["message"],
                }
            )

            # Проверяем, нужно ли ждать еще сообщений
            total_chars = sum(len(msg["text"]) for msg in self.user_messages_buffer[user_id])

            if len(self.user_messages_buffer[user_id]) == 1 and total_chars >= 100:
                # Если это первое сообщение и оно достаточно длинное - обрабатываем сразу
                await self.process_custom_summarization(chat_id, user_id)
            elif len(self.user_messages_buffer[user_id]) > 1:
                # Если уже есть несколько сообщений - спрашиваем, продолжать ли сбор
                await self.send_message(
                    chat_id,
                    f"📝 Собрано сообщений: {len(self.user_messages_buffer[user_id])}\n"
                    f"📊 Общий объем: {total_chars:,} символов\n\n"
                    f"Отправьте текст: 'ok' для обработки или еще текст для добавления",
                )
            else:
                # Слишком мало символов
                await self.send_message(
                    chat_id,
                    f"📝 Получено: {total_chars} символов\n"
                    f"Минимум: 100 символов\n\n"
                    f"Отправьте больше текста или пересланных сообщений.",
                )

        except Exception as e:
            logger.error(f"Ошибка обработки текста настраиваемой суммаризации: {e}")
            await self.send_message(
                chat_id, "❌ Произошла ошибка при обработке текста. Попробуйте снова."
            )

    async def process_custom_summarization(self, chat_id: int, user_id: int):
        """Выполнение настраиваемой суммаризации с выбранными параметрами"""
        try:
            if user_id not in self.user_settings or user_id not in self.user_messages_buffer:
                await self.send_message(
                    chat_id,
                    "❌ Настройки суммаризации не найдены. Используйте /summarize для начала.",
                )
                return

            # Объединяем все сообщения
            combined_text = ""
            for msg in self.user_messages_buffer[user_id]:
                if combined_text:
                    combined_text += "\n\n"
                combined_text += msg["text"]

            total_chars = len(combined_text)

            if total_chars < 100:
                await self.send_message(
                    chat_id,
                    f"❌ Недостаточно текста для суммаризации ({total_chars} символов). Минимум: 100 символов.",
                )
                return

            if total_chars > 10000:
                await self.send_message(
                    chat_id,
                    f"❌ Слишком много текста ({total_chars:,} символов). Максимум: 10,000 символов.",
                )
                return

            # Отправляем сообщение о начале обработки
            processing_msg = await self.send_message(
                chat_id, "⏳ Обрабатываю текст с выбранными настройками..."
            )

            # Получаем настройки пользователя
            settings = self.user_settings[user_id]
            compression_ratio = int(settings["compression"]) / 100.0
            format_type = settings["format"]

            # Выполняем настраиваемую суммаризацию
            summary = await self.custom_summarize_text(
                combined_text, compression_ratio, format_type
            )

            # Удаляем сообщение о обработке
            if processing_msg:
                processing_msg_id = processing_msg.get("result", {}).get("message_id")
                if processing_msg_id:
                    await self.delete_message(chat_id, processing_msg_id)

            # Формируем ответ
            format_emoji = {"bullets": "•", "paragraph": "📄", "keywords": "🏷️"}[format_type]
            compression_text = f"{settings['compression']}%"

            response_text = f"""{format_emoji} **Настраиваемая суммаризация**
📊 Сжатие: {compression_text} | 📝 Исходный текст: {total_chars:,} символов

{summary}

✅ Суммаризация завершена! Используйте /summarize для новой настраиваемой суммаризации."""

            await self.send_message(chat_id, response_text)

            # Сохраняем статистику
            try:
                await self._run_in_executor(
                    self.db.save_user_request, user_id, "", total_chars, len(summary), 0.0, "groq"
                )
            except (OSError, sqlite3.Error) as save_error:
                logger.error(f"Ошибка сохранения запроса в БД: {save_error}")

            # Очищаем состояние пользователя
            if user_id in self.user_states:
                del self.user_states[user_id]
            if user_id in self.user_settings:
                del self.user_settings[user_id]
            if user_id in self.user_messages_buffer:
                del self.user_messages_buffer[user_id]

        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Ошибка выполнения настраиваемой суммаризации: {e}")
            await self.send_message(
                chat_id, "❌ Произошла ошибка при суммаризации. Попробуйте позже."
            )

    # ============ Вспомогательные методы ============

    async def summarize_text(self, text: str, target_ratio: float = 0.3) -> str:
        """Суммаризация текста с помощью LLM API"""
        if not self.groq_client and not self.openrouter_client:
            return "❌ LLM API недоступен. Пожалуйста, проверьте настройки."

        try:
            import re

            # Нормализация текста
            text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
            text = re.sub(r"\s+", " ", text)
            text = text.strip()

            if not text:
                return "❌ Текст пуст после нормализации"

            target_length = int(len(text) * target_ratio)

            prompt = f"""Ты - эксперт по суммаризации текстов. Создай краткое саммари следующего текста на том же языке, что и исходный текст.

Требования:
- Саммари должно быть примерно {target_length} символов (целевое сжатие: {target_ratio:.0%})
- Сохрани все ключевые моменты и важную информацию
- Используй структурированный формат с bullet points (•)
- Пиши естественным языком, сохраняя стиль исходного текста
- Если текст на русском - отвечай на русском языке
- Начни ответ сразу с саммари, без вступлений

Текст для суммаризации:
{text}"""

            # Пробуем Groq, затем OpenRouter
            summary = None
            if self.groq_client:
                try:
                    from bot.core.decorators import retry_on_failure

                    @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
                    def call_groq():
                        return self.groq_client.chat.completions.create(
                            messages=[{"role": "user", "content": prompt}],
                            model="llama-3.3-70b-versatile",
                            temperature=0.3,
                            max_tokens=2000,
                        )

                    response = call_groq()
                    if response.choices and response.choices[0].message:
                        summary = response.choices[0].message.content.strip()
                except Exception as e:
                    logger.warning(f"Groq API недоступен: {e}")

            # Fallback на OpenRouter
            if not summary and self.openrouter_client:
                try:
                    response = await self.openrouter_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model="deepseek/deepseek-chat-v3.1:free",
                        temperature=0.3,
                        max_tokens=2000,
                    )
                    if response.choices and response.choices[0].message:
                        summary = response.choices[0].message.content.strip()
                        logger.info("Использован OpenRouter (fallback)")
                except Exception as e:
                    logger.error(f"OpenRouter API ошибка: {e}")

            return summary if summary else "❌ Не удалось получить ответ от модели"

        except Exception as e:
            logger.error(f"Ошибка при суммаризации: {e}")
            return f"❌ Ошибка при обработке текста: {str(e)[:100]}"

    async def custom_summarize_text(
        self, text: str, compression_ratio: float, format_type: str
    ) -> str:
        """Настраиваемая суммаризация текста"""
        try:
            target_length = int(len(text) * compression_ratio)

            format_instructions = {
                "bullets": """- Создай маркированный список ключевых пунктов
- Используй bullet points (•) для каждого пункта
- Каждый пункт должен быть краткой, но информативной мыслью
- Структурируй по важности: сначала самое важное""",
                "paragraph": """- Создай связный абзац в виде краткого изложения
- Текст должен читаться естественно и плавно
- Сохрани логическую структуру исходного текста
- Используй переходные слова и связки между предложениями""",
                "keywords": """- Создай список ключевых слов и терминов
- Выдели самые важные понятия из текста
- Используй формат: слово/термин - краткое пояснение
- Расположи по важности: сначала центральные концепции""",
            }

            prompt = f"""Ты - эксперт по суммаризации текстов. Создай саммари следующего текста на том же языке, что и исходный текст.

Требования:
- Саммари должно быть примерно {target_length} символов (целевое сжатие: {compression_ratio:.0%})
- Сохрани все ключевые моменты и важную информацию
- Если текст на русском - отвечай на русском языке

Формат результата:
{format_instructions[format_type]}

Начни ответ сразу с саммари, без вступлений и комментариев.

Текст для суммаризации:
{text}"""

            if self.groq_client:
                from bot.core.decorators import retry_on_failure

                @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
                def call_groq_api():
                    return self.groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.3,
                        max_tokens=2000,
                        top_p=0.9,
                        stream=False,
                    )

                response = call_groq_api()

                if response.choices and response.choices[0].message:
                    summary = response.choices[0].message.content
                    if summary:
                        return summary.strip()

            return "❌ Не удалось получить ответ от модели"

        except Exception as e:
            logger.error(f"Ошибка при настраиваемой суммаризации: {e}")
            return f"❌ Ошибка при обработке текста: {str(e)[:100]}"

    def check_user_rate_limit(self, user_id: int) -> bool:
        """Проверка лимита запросов пользователя"""
        now = time.time()
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []

        # Удаляем запросы старше 1 минуты
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id] if now - req_time < 60
        ]

        # Проверяем лимит (10 запросов в минуту)
        if len(self.user_requests[user_id]) >= 10:
            return False

        self.user_requests[user_id].append(now)
        return True

    async def get_user_compression_level(self, user_id: int) -> int:
        """Получение уровня сжатия пользователя из базы данных"""
        try:
            settings = await self._run_in_executor(self.db.get_user_settings, user_id)
            return settings.get("compression_level", 30)
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Ошибка получения настроек пользователя {user_id}: {e}")
            return 30

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

    def _get_compression_keyboard(self, current_level: int = 30) -> dict:
        """
        Создает inline клавиатуру для выбора уровня сжатия

        Args:
            current_level: Текущий уровень сжатия (10, 30, 50)

        Returns:
            dict: Inline keyboard markup
        """
        buttons = [
            [
                {
                    "text": "✅ Коротко (10%)" if current_level == 10 else "Коротко (10%)",
                    "callback_data": "compression_10",
                },
                {
                    "text": "✅ Средне (30%)" if current_level == 30 else "Средне (30%)",
                    "callback_data": "compression_30",
                },
                {
                    "text": "✅ Подробно (50%)" if current_level == 50 else "Подробно (50%)",
                    "callback_data": "compression_50",
                },
            ]
        ]

        return {"inline_keyboard": buttons}
