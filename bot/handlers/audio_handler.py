"""Обработчик аудио сообщений"""

import logging
import os
import sqlite3
from typing import Dict, Set, Optional
from .base import BaseHandler

logger = logging.getLogger(__name__)


class AudioHandler(BaseHandler):
    """Обработчик аудио сообщений (voice, audio, video_note, documents)"""

    def __init__(
        self,
        session,
        base_url,
        db,
        state_manager,
        token,
        audio_processor,
        smart_summarizer,
        groq_client,
        openrouter_client,
        user_requests: Dict,
        processing_users: Set,
        db_executor
    ):
        super().__init__(session, base_url, db, state_manager)
        self.token = token
        self.audio_processor = audio_processor
        self.smart_summarizer = smart_summarizer
        self.groq_client = groq_client
        self.openrouter_client = openrouter_client
        self.user_requests = user_requests
        self.processing_users = processing_users
        self.db_executor = db_executor

    async def handle_audio_message(self, update: dict):
        """Универсальная обработка всех типов аудио сообщений"""
        from utils.tg_audio import (
            extract_audio_descriptor,
            get_audio_info_text,
            format_duration
        )

        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]

        # Извлекаем дескриптор аудио
        audio_descriptor = extract_audio_descriptor(message)

        if not audio_descriptor or not audio_descriptor.get("success"):
            await self.send_message(
                chat_id,
                "🔍 Аудио не найдено\n\n"
                "Я не нашёл аудио или голос в этом сообщении.\n"
                "Поддерживаются:\n"
                "• Голосовые сообщения (voice)\n"
                "• Аудио файлы (audio)\n"
                "• Видео сообщения/кружочки (video note)\n"
                "• Документы с аудио файлами\n\n"
                "Попробуйте переслать голосовое сообщение или загрузить аудио файл."
            )
            return

        # Логируем информацию об аудио
        audio_info = get_audio_info_text(audio_descriptor)
        logger.info(f"Обрабатываю аудио для пользователя {user_id}: {audio_info}")

        # Проверка лимита запросов
        if not self.check_user_rate_limit(user_id):
            await self.send_message(
                chat_id,
                "⏰ Превышен лимит запросов!\n\n"
                "Пожалуйста, подождите минуту перед отправкой нового аудио. Лимит: 10 запросов в минуту."
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

        # Отправляем прогресс-сообщение
        progress_msg = await self.send_message(
            chat_id,
            f"⏳ Обрабатываю аудио…\n\n{audio_info}"
        )
        progress_message_id = (
            progress_msg.get("result", {}).get("message_id")
            if progress_msg and progress_msg.get("ok")
            else None
        )

        try:
            # Проверяем доступность аудио процессора
            if not self.audio_processor:
                error_msg = "❌ Аудио обработка недоступна\n\nНет доступа к Groq API для распознавания речи."
                if progress_message_id:
                    await self.edit_message_text(chat_id, progress_message_id, error_msg)
                else:
                    await self.send_message(chat_id, error_msg)
                return

            # Обновляем прогресс - скачивание
            if progress_message_id and isinstance(progress_message_id, int):
                try:
                    await self.edit_message_text(
                        chat_id,
                        progress_message_id,
                        f"⬇️ Скачиваю файл…\n\n{audio_info}"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось обновить прогресс (скачивание): {e}")

            # Получаем URL файла для скачивания
            file_url = await self._get_file_url(audio_descriptor["file_id"])
            filename_hint = audio_descriptor.get("filename") or "audio.ogg"

            # Добавляем маппинг расширения по mime и дефолт .ogg
            if not os.path.splitext(filename_hint)[1]:
                mime = (audio_descriptor.get("mime_type") or "").lower()
                ext_by_mime = {
                    "audio/ogg": ".ogg",
                    "audio/oga": ".oga",
                    "audio/opus": ".ogg",
                    "audio/mpeg": ".mp3",
                    "audio/mp3": ".mp3",
                    "audio/mp4": ".m4a",
                    "audio/x-m4a": ".m4a",
                    "audio/aac": ".aac",
                    "audio/flac": ".flac",
                    "audio/wav": ".wav",
                    "audio/x-wav": ".wav",
                    "video/webm": ".webm",
                    "video/mp4": ".m4a",
                    "application/octet-stream": ".ogg",
                }
                filename_hint += ext_by_mime.get(mime, ".ogg")

            # Логируем информацию об аудио перед обработкой
            logger.info(
                f"Audio: mime={audio_descriptor.get('mime_type')} filename_hint={filename_hint}"
            )

            # Обновляем прогресс - конвертация
            if progress_message_id and isinstance(progress_message_id, int):
                try:
                    await self.edit_message_text(
                        chat_id,
                        progress_message_id,
                        f"🎛️ Конвертирую аудио…\n\n{audio_info}"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось обновить прогресс (конвертация): {e}")

            # Обрабатываем аудио
            result = await self.audio_processor.process_audio_from_telegram(
                file_url, filename_hint
            )

            if not result.get("success"):
                error_msg = f"❌ Ошибка обработки аудио\n\n{result.get('error', 'Неизвестная ошибка')}"
                if progress_message_id:
                    await self.edit_message_text(chat_id, progress_message_id, error_msg)
                else:
                    await self.send_message(chat_id, error_msg)
                return

            # Обновляем прогресс - распознавание завершено
            if progress_message_id and isinstance(progress_message_id, int):
                try:
                    await self.edit_message_text(
                        chat_id,
                        progress_message_id,
                        f"📝 Готовлю саммари…\n\n{audio_info}"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось обновить прогресс (саммари): {e}")

            transcript = result["transcript"]
            duration = result.get("duration_sec")

            # Проверяем длину транскрипта
            if not transcript or len(transcript.strip()) < 10:
                error_msg = (
                    "❌ Речь не распознана\n\n"
                    "Возможные причины:\n"
                    "• Слишком тихая запись\n"
                    "• Фоновый шум\n"
                    "• Неподдерживаемый язык\n"
                    "• Файл без речи"
                )
                if progress_message_id:
                    await self.edit_message_text(chat_id, progress_message_id, error_msg)
                else:
                    await self.send_message(chat_id, error_msg)
                return

            # Попытка smart суммаризации
            summary = None
            if hasattr(self, "smart_summarizer") and self.smart_summarizer:
                try:
                    compression_level = await self.get_user_compression_level(user_id)
                    target_ratio = compression_level / 100.0

                    smart_result = await self.smart_summarizer.smart_summarize(
                        transcript,
                        source_type="audio",
                        source_name=filename_hint,
                        compression_ratio=target_ratio,
                    )

                    if smart_result.get("success"):
                        summary = smart_result.get("summary", "")
                except Exception as e:
                    logger.warning(f"SmartSummarizer не сработал: {e}")

            # Фолбэк суммаризация через Groq
            if not summary and self.groq_client:
                try:
                    compression_level = await self.get_user_compression_level(user_id)
                    target_ratio = compression_level / 100.0
                    summary = await self.summarize_text(transcript, target_ratio)
                except Exception as e:
                    logger.warning(f"Groq суммаризация не сработала: {e}")

            # Если нет саммаризации, показываем транскрипт
            if not summary:
                summary = (
                    "Краткое изложение недоступно. Вот полный текст:\n\n"
                    + transcript[:1000]
                    + ("..." if len(transcript) > 1000 else "")
                )

            # Формируем финальный ответ
            duration_text = f" ({format_duration(duration)})" if duration else ""
            final_message = f"🎧 {audio_info}{duration_text}\n\n📋 **Саммари:**\n{summary}"

            # Ограничиваем длину сообщения
            if len(final_message) > 4000:
                summary_limit = (
                    4000 - len(f"🎧 {audio_info}{duration_text}\n\n📋 **Саммари:**\n") - 50
                )
                summary = summary[:summary_limit] + "..."
                final_message = (
                    f"🎧 {audio_info}{duration_text}\n\n📋 **Саммари:**\n{summary}"
                )

            # Отправляем результат
            if progress_message_id and isinstance(progress_message_id, int):
                try:
                    await self.edit_message_text(chat_id, progress_message_id, final_message)
                except Exception as e:
                    logger.warning(f"Не удалось отредактировать сообщение: {e}")
                    await self.send_message(chat_id, final_message)
            else:
                await self.send_message(chat_id, final_message)

            # Сохраняем в базу
            try:
                username = message["from"].get("username", "")
                await self._run_in_executor(
                    self.db.save_user_request,
                    user_id,
                    username,
                    len(transcript),
                    len(summary) if summary else 0,
                    0.0,
                    "audio_processing",
                )
            except (sqlite3.Error, ValueError) as e:
                logger.error(f"Ошибка сохранения в БД: {e}")

        except Exception as e:
            logger.error(f"Ошибка обработки аудио для пользователя {user_id}: {e}")
            error_msg = f"❌ Произошла ошибка при обработке аудио\n\n{str(e)[:200]}..."

            if progress_message_id:
                await self.edit_message_text(chat_id, progress_message_id, error_msg)
            else:
                await self.send_message(chat_id, error_msg)

        finally:
            # Убираем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)

    # ============ Вспомогательные методы ============

    async def _get_file_url(self, file_id: str) -> str:
        """Получает URL файла от Telegram API"""
        file_info_response = await self.get_file_info(file_id)
        if not file_info_response or not file_info_response.get("ok"):
            raise Exception("Не удалось получить информацию о файле")

        file_info = file_info_response["result"]
        return f"https://api.telegram.org/file/bot{self.token}/{file_info['file_path']}"

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
        """Проверка лимита запросов пользователя"""
        import time

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

    async def summarize_text(self, text: str, target_ratio: float = 0.3) -> str:
        """Суммаризация текста с помощью LLM API"""
        if not self.groq_client and not self.openrouter_client:
            return "❌ LLM API недоступен"

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

            # Пробуем Groq
            if self.groq_client:
                try:
                    response = self.groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.3,
                        max_tokens=2000,
                    )
                    if response.choices and response.choices[0].message:
                        return response.choices[0].message.content.strip()
                except Exception as e:
                    logger.warning(f"Groq API error: {e}")

            # Fallback на OpenRouter
            if self.openrouter_client:
                try:
                    response = await self.openrouter_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model="deepseek/deepseek-chat-v3.1:free",
                        temperature=0.3,
                        max_tokens=2000,
                    )
                    if response.choices and response.choices[0].message:
                        return response.choices[0].message.content.strip()
                except Exception as e:
                    logger.error(f"OpenRouter API error: {e}")

            return "❌ Не удалось получить ответ от модели"

        except Exception as e:
            logger.error(f"Ошибка при суммаризации: {e}")
            return f"❌ Ошибка: {str(e)[:100]}"

    async def _run_in_executor(self, func, *args):
        """Запуск синхронной функции в executor"""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.db_executor, func, *args)
