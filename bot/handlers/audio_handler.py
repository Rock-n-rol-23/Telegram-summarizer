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

        # Временное хранилище для аудио данных (transcript, segments, reasoning)
        # Ключ: message_id, значение: {transcript, segments, speaker_data, reasoning}
        self.audio_data_cache = {}

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
            segments = result.get("segments", [])
            speaker_emotion_data = result.get("speaker_emotion_data")

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

            # Суммаризация с reasoning
            summary = None
            reasoning = None

            try:
                logger.info(f"Начинаю суммаризацию для пользователя {user_id}")
                compression_level = await self.get_user_compression_level(user_id)
                target_ratio = compression_level / 100.0
                result = await self.summarize_audio_with_reasoning(transcript, target_ratio)
                summary = result.get("summary", "")
                reasoning = result.get("reasoning", "")
                logger.info(f"Суммаризация завершена. Summary: {len(summary) if summary else 0} символов, Reasoning: {len(reasoning) if reasoning else 0} символов")
            except Exception as e:
                logger.error(f"Суммаризация с reasoning не сработала: {e}", exc_info=True)

            # Если нет саммаризации, показываем транскрипт
            if not summary:
                summary = (
                    "Краткое изложение недоступно. Вот полный текст:\n\n"
                    + transcript[:1000]
                    + ("..." if len(transcript) > 1000 else "")
                )

            # Формируем финальный ответ (только саммари, без транскрипта по умолчанию)
            duration_text = f" ({format_duration(duration)})" if duration else ""

            # Заголовок
            final_message = f"🎧 {audio_info}{duration_text}\n\n"

            # Информация о спикерах
            if speaker_emotion_data and speaker_emotion_data.get("num_speakers", 1) > 1:
                num_speakers = speaker_emotion_data["num_speakers"]
                final_message += f"👥 Обнаружено спикеров: {num_speakers}\n\n"

            # Развёрнутое саммари
            final_message += summary

            # Ограничиваем длину сообщения (Telegram лимит 4096)
            if len(final_message) > 4000:
                # Урезаем саммари
                summary_limit = 4000 - len(f"🎧 {audio_info}{duration_text}\n\n") - 100
                summary_short = summary[:summary_limit] + "\n\n... [саммари урезано из-за лимита длины сообщения]"
                final_message = f"🎧 {audio_info}{duration_text}\n\n" + summary_short

            # Создаём inline-клавиатуру с кнопками
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "📋 Показать транскрипт", "callback_data": f"audio_transcript_{message['message_id']}"},
                        {"text": "🧠 Показать reasoning", "callback_data": f"audio_reasoning_{message['message_id']}"}
                    ]
                ]
            }

            # Сохраняем данные в кэш для последующего показа
            self.audio_data_cache[message['message_id']] = {
                "transcript": transcript,
                "segments": segments,
                "speaker_emotion_data": speaker_emotion_data,
                "reasoning": reasoning,
                "duration": duration
            }

            # Отправляем результат с кнопками
            logger.info(f"Отправляю финальное сообщение пользователю {user_id}, длина: {len(final_message)} символов")
            message_sent = False

            if progress_message_id and isinstance(progress_message_id, int):
                try:
                    response = await self.edit_message_with_keyboard(
                        chat_id,
                        progress_message_id,
                        final_message,
                        keyboard
                    )
                    logger.info(f"Ответ от edit_message_with_keyboard: {response}")

                    # Проверяем успешность редактирования
                    if response and response.get('ok'):
                        logger.info(f"Сообщение успешно отредактировано")
                        message_sent = True
                    else:
                        error_desc = response.get('description', 'Unknown error') if response else 'No response'
                        logger.warning(f"Редактирование сообщения вернуло ok=False: {error_desc}")
                        # Пробуем отправить новое сообщение
                        raise Exception(f"Edit failed: {error_desc}")

                except Exception as e:
                    logger.error(f"Не удалось отредактировать сообщение: {e}", exc_info=True)
                    try:
                        logger.info("Пробую отправить новое сообщение вместо редактирования")
                        response = await self.send_message_with_keyboard(chat_id, final_message, keyboard)
                        logger.info(f"Ответ от send_message_with_keyboard: {response}")

                        if response and response.get('ok'):
                            logger.info(f"Новое сообщение успешно отправлено")
                            message_sent = True
                        else:
                            error_desc = response.get('description', 'Unknown error') if response else 'No response'
                            logger.error(f"Отправка нового сообщения вернула ok=False: {error_desc}")
                    except Exception as e2:
                        logger.error(f"Не удалось отправить новое сообщение: {e2}", exc_info=True)
            else:
                try:
                    logger.info("Progress message ID отсутствует, отправляю новое сообщение")
                    response = await self.send_message_with_keyboard(chat_id, final_message, keyboard)
                    logger.info(f"Ответ от send_message_with_keyboard: {response}")

                    if response and response.get('ok'):
                        logger.info(f"Сообщение успешно отправлено")
                        message_sent = True
                    else:
                        error_desc = response.get('description', 'Unknown error') if response else 'No response'
                        logger.error(f"Отправка сообщения вернула ok=False: {error_desc}")
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение: {e}", exc_info=True)

            if not message_sent:
                logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Пользователь {user_id} не получил финальное сообщение!")

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
            logger.error(f"Ошибка обработки аудио для пользователя {user_id}: {e}", exc_info=True)
            error_msg = f"❌ Произошла ошибка при обработке аудио\n\n{str(e)[:200]}..."

            try:
                if progress_message_id:
                    await self.edit_message_text(chat_id, progress_message_id, error_msg)
                else:
                    await self.send_message(chat_id, error_msg)
            except Exception as send_error:
                logger.error(f"Не удалось отправить сообщение об ошибке: {send_error}", exc_info=True)

        finally:
            # Убираем пользователя из списка обрабатываемых
            logger.info(f"Завершена обработка аудио для пользователя {user_id}, удаляю из processing_users")
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

    async def summarize_audio_with_reasoning(self, text: str, target_ratio: float = 0.3) -> dict:
        """
        Суммаризация аудио текста с reasoning (объяснением хода мыслей).

        Returns:
            dict с ключами 'summary' и 'reasoning'
        """
        if not self.groq_client and not self.openrouter_client:
            return {"summary": "❌ LLM API недоступен", "reasoning": ""}

        try:
            import re

            # Нормализация текста
            text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
            text = re.sub(r"\s+", " ", text)
            text = text.strip()

            if not text:
                return {"summary": "❌ Текст пуст после нормализации", "reasoning": ""}

            target_length = int(len(text) * target_ratio)

            prompt = f"""Ты - эксперт по анализу голосовых сообщений. Создай развёрнутое саммари транскрипта голосового сообщения.

**Текст транскрипта:**
{text}

**Требования к саммари:**
- Развёрнутое и детальное (минимум {target_length} символов)
- Сохрани ВСЕ ключевые моменты: даты, имена, цифры, решения, договорённости
- Используй структурированный формат с секциями:
  📌 **Главное** - основная суть в 1-2 предложениях
  🔍 **Детали** - важные подробности в bullet points
  ✅ **Выводы/Договорённости** - конкретные действия и решения (если есть)
- Пиши естественным языком на том же языке, что и исходный текст
- Если это диалог - отмечай ключевые реплики разных участников

**ВАЖНО:** Также добавь секцию с твоим reasoning (рассуждением):

🧠 **Reasoning:**
Объясни, как ты анализировал этот текст:
- Какую главную тему ты определил?
- На какие ключевые моменты обратил внимание?
- Какой контекст важен для понимания?
- Какие детали можно опустить, а какие критичны?

Ответь СТРОГО в формате JSON:
{{
  "summary": "Развёрнутое саммари со всеми секциями",
  "reasoning": "Объяснение твоего хода мыслей при анализе"
}}"""

            # Пробуем Groq
            if self.groq_client:
                try:
                    logger.info("Отправляю запрос к Groq API для суммаризации с reasoning")
                    # Обёртываем синхронный вызов в executor чтобы не блокировать event loop
                    import asyncio
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        self.db_executor,
                        lambda: self.groq_client.chat.completions.create(
                            messages=[{"role": "user", "content": prompt}],
                            model="llama-3.3-70b-versatile",
                            temperature=0.3,
                            max_tokens=3000,
                            response_format={"type": "json_object"}
                        )
                    )
                    logger.info("Получен ответ от Groq API")
                    if response.choices and response.choices[0].message:
                        content = response.choices[0].message.content
                        # При response_format="json_object" Groq может вернуть dict или строку
                        if isinstance(content, str):
                            import json
                            result = json.loads(content)
                        else:
                            result = content

                        logger.info(f"Успешно распарсен JSON ответ от Groq: summary={len(result.get('summary', ''))} chars, reasoning={len(result.get('reasoning', ''))} chars")
                        return {
                            "summary": result.get("summary", "").strip() if isinstance(result.get("summary"), str) else str(result.get("summary", "")),
                            "reasoning": result.get("reasoning", "").strip() if isinstance(result.get("reasoning"), str) else str(result.get("reasoning", ""))
                        }
                except Exception as e:
                    logger.error(f"Groq API error: {e}", exc_info=True)

            # Fallback на OpenRouter (если есть)
            if self.openrouter_client:
                try:
                    response = await self.openrouter_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model="deepseek/deepseek-chat-v3.1:free",
                        temperature=0.3,
                        max_tokens=3000,
                    )
                    if response.choices and response.choices[0].message:
                        import json
                        result = json.loads(response.choices[0].message.content)
                        return {
                            "summary": result.get("summary", "").strip(),
                            "reasoning": result.get("reasoning", "").strip()
                        }
                except Exception as e:
                    logger.error(f"OpenRouter API error: {e}")

            return {"summary": "❌ Не удалось получить ответ от модели", "reasoning": ""}

        except Exception as e:
            logger.error(f"Ошибка при суммаризации: {e}")
            return {"summary": f"❌ Ошибка: {str(e)[:100]}", "reasoning": ""}

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

    def _get_emotion_emoji(self, emotion: str) -> str:
        """Возвращает эмодзи для эмоции"""
        emotion_emojis = {
            "радостно": "😊",
            "взволнованно": "😰",
            "серьезно": "😐",
            "напряженно": "😬",
            "спокойно": "😌",
            "нейтрально": "",
            "удивленно": "😲",
            "грустно": "😔",
            "сердито": "😠",
            "задумчиво": "🤔"
        }
        return emotion_emojis.get(emotion.lower(), "")

    async def send_message_with_keyboard(self, chat_id: int, text: str, keyboard: dict):
        """Отправляет сообщение с inline клавиатурой"""
        url = f"{self.base_url}/sendMessage"

        # Сначала пробуем с Markdown
        data = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": keyboard,
            "parse_mode": "Markdown"
        }

        async with self.session.post(url, json=data) as response:
            result = await response.json()

            # Если ошибка связана с parse_mode, пробуем без него
            if not result.get('ok') and 'parse' in result.get('description', '').lower():
                logger.warning(f"Markdown parsing failed, retrying without parse_mode: {result.get('description')}")
                data_no_parse = {
                    "chat_id": chat_id,
                    "text": text,
                    "reply_markup": keyboard
                }
                async with self.session.post(url, json=data_no_parse) as response2:
                    return await response2.json()

            return result

    async def edit_message_with_keyboard(self, chat_id: int, message_id: int, text: str, keyboard: dict):
        """Редактирует сообщение с inline клавиатурой"""
        url = f"{self.base_url}/editMessageText"

        # Сначала пробуем с Markdown
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "reply_markup": keyboard,
            "parse_mode": "Markdown"
        }

        async with self.session.post(url, json=data) as response:
            result = await response.json()

            # Если ошибка связана с parse_mode, пробуем без него
            if not result.get('ok') and 'parse' in result.get('description', '').lower():
                logger.warning(f"Markdown parsing failed, retrying without parse_mode: {result.get('description')}")
                data_no_parse = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "reply_markup": keyboard
                }
                async with self.session.post(url, json=data_no_parse) as response2:
                    return await response2.json()

            return result

    async def handle_audio_callback(self, callback_query: dict):
        """Обработка callback запросов от кнопок аудио"""
        data = callback_query.get("data", "")
        message = callback_query.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")

        # Парсим callback data
        if data.startswith("audio_transcript_"):
            audio_msg_id = int(data.replace("audio_transcript_", ""))
            await self._show_transcript(chat_id, message_id, audio_msg_id)
        elif data.startswith("audio_reasoning_"):
            audio_msg_id = int(data.replace("audio_reasoning_", ""))
            await self._show_reasoning(chat_id, message_id, audio_msg_id)

        # Отвечаем на callback чтобы убрать "часики"
        await self.answer_callback_query(callback_query["id"])

    async def _show_transcript(self, chat_id: int, message_id: int, audio_msg_id: int):
        """Показывает транскрипт аудио с спикерами и эмоциями"""
        if audio_msg_id not in self.audio_data_cache:
            await self.send_message(chat_id, "❌ Данные не найдены. Возможно, они устарели.")
            return

        data = self.audio_data_cache[audio_msg_id]
        transcript = data["transcript"]
        segments = data["segments"]
        speaker_data = data["speaker_emotion_data"]
        duration = data["duration"]

        from utils.tg_audio import format_duration
        duration_text = f" ({format_duration(duration)})" if duration else ""

        # Формируем сообщение с транскриптом
        response = f"💬 **Транскрипт{duration_text}**\n\n"

        if segments and speaker_data:
            speaker_map = speaker_data.get("speaker_map", {})
            emotion_map = speaker_data.get("emotion_map", {})

            for i, seg in enumerate(segments):
                speaker = speaker_map.get(i, "Спикер 1")
                emotion = emotion_map.get(i, "")
                emotion_emoji = self._get_emotion_emoji(emotion)
                text = seg["text"].strip()
                timestamp = self.audio_processor.format_timestamp(seg["start"])

                if emotion and emotion != "нейтрально":
                    response += f"[{timestamp}] {speaker} {emotion_emoji}: {text}\n"
                else:
                    response += f"[{timestamp}] {speaker}: {text}\n"

                # Ограничиваем длину
                if len(response) > 3800:
                    response += f"\n... и ещё {len(segments) - i - 1} фраз"
                    break
        else:
            # Показываем просто текст
            response += transcript[:3800]
            if len(transcript) > 3800:
                response += "..."

        await self.send_message(chat_id, response)

    async def _show_reasoning(self, chat_id: int, message_id: int, audio_msg_id: int):
        """Показывает reasoning (объяснение хода мыслей LLM)"""
        if audio_msg_id not in self.audio_data_cache:
            await self.send_message(chat_id, "❌ Данные не найдены. Возможно, они устарели.")
            return

        data = self.audio_data_cache[audio_msg_id]
        reasoning = data["reasoning"]

        if reasoning:
            response = f"🧠 **Reasoning (ход мыслей при анализе):**\n\n{reasoning}"
            # Ограничиваем длину
            if len(response) > 4000:
                response = response[:4000] + "..."
            await self.send_message(chat_id, response)
        else:
            await self.send_message(chat_id, "❌ Reasoning недоступен для этого аудио.")

    async def answer_callback_query(self, callback_query_id: str, text: str = ""):
        """Отвечает на callback query"""
        url = f"{self.base_url}/answerCallbackQuery"
        data = {"callback_query_id": callback_query_id}
        if text:
            data["text"] = text
        async with self.session.post(url, json=data) as response:
            return await response.json()
