"""Обработчик выбора между обработкой разных типов контента"""

import logging
from typing import Dict, Optional, List
from .base import BaseHandler
from bot.content_detector import ContentDetector, ContentItem
from llm.provider_router import generate_completion
import re

logger = logging.getLogger(__name__)


class ChoiceHandler(BaseHandler):
    """Обработчик диалога выбора между разными типами контента"""

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
        self.content_detector = ContentDetector()

        # Кэш сообщений пользователей для обработки после выбора
        self.pending_choices: Dict[int, dict] = {}

    async def handle_mixed_content(self, update: dict, content_items: List[ContentItem]):
        """
        Основной метод обработки смешанного контента

        Args:
            update: Telegram update object
            content_items: Список найденных элементов контента
        """
        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]

        logger.info(f"Пользователь {user_id} отправил смешанный контент: {len(content_items)} элементов")

        # Проверяем настройки пользователя
        user_settings = await self._get_user_content_settings(user_id)
        content_mode = user_settings.get("content_mode", "ask")  # ask, smart, all

        if content_mode == "all":
            # Обрабатываем весь контент без вопросов
            await self._process_all_content(update, content_items)
            return
        elif content_mode == "smart":
            # Умный режим - определяем намерение
            await self._smart_process_content(update, content_items)
            return
        else:
            # Режим "ask" - спрашиваем пользователя
            await self._ask_user_choice(update, content_items)

    async def _ask_user_choice(self, update: dict, content_items: List[ContentItem]):
        """
        Спрашивает пользователя, что обработать

        Args:
            update: Telegram update object
            content_items: Список найденных элементов контента
        """
        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]

        # Сохраняем контент для последующей обработки
        self.pending_choices[user_id] = {
            "update": update,
            "content_items": content_items,
            "message_id": message["message_id"]
        }

        # Формируем описание контента
        content_summary = self.content_detector.get_content_summary(content_items)

        # Создаем inline клавиатуру
        keyboard = self._create_content_choice_keyboard(content_items)

        # Формируем сообщение
        choice_text = f"""{content_summary}

🤔 Что обработать?"""

        # Отправляем сообщение с выбором
        await self.send_message(chat_id, choice_text, reply_markup=keyboard)

    async def _smart_process_content(self, update: dict, content_items: List[ContentItem]):
        """
        Умный режим - пытается определить намерение пользователя

        Args:
            update: Telegram update object
            content_items: Список найденных элементов контента
        """
        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]

        # Получаем текст сообщения для анализа контекста
        text = message.get("text") or message.get("caption", "")

        # Анализируем намерение через LLM
        intent = await self._detect_user_intent(text, content_items)

        logger.info(f"Определено намерение пользователя {user_id}: {intent}")

        # Формируем описание того, что будет обработано
        intent_description = self._get_intent_description(intent, content_items)

        # Сохраняем для обработки
        self.pending_choices[user_id] = {
            "update": update,
            "content_items": content_items,
            "intent": intent,
            "message_id": message["message_id"]
        }

        # Создаем клавиатуру с подтверждением
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "▶️ Начать", "callback_data": f"smart_confirm"},
                    {"text": "✏️ Изменить выбор", "callback_data": "smart_change"}
                ]
            ]
        }

        # Отправляем сообщение с подтверждением
        confirmation_text = f"""✓ Обработаю: {intent_description}"""

        await self.send_message(chat_id, confirmation_text, reply_markup=keyboard)

    async def _process_all_content(self, update: dict, content_items: List[ContentItem]):
        """
        Обрабатывает весь контент без вопросов

        Args:
            update: Telegram update object
            content_items: Список найденных элементов контента
        """
        # TODO: Реализовать обработку всего контента сразу
        # Пока используем ask режим
        await self._ask_user_choice(update, content_items)

    async def handle_photo_with_url(self, update: dict, urls: list):
        """
        Обработка сообщения с фото и URL (legacy метод, теперь использует handle_mixed_content)

        Args:
            update: Telegram update object
            urls: Список найденных URL в caption
        """
        # Детектируем контент через новый детектор
        content_items = self.content_detector.detect_content_types(update["message"])

        # Если смешанный контент - используем новый обработчик
        if self.content_detector.is_mixed_content(content_items):
            await self.handle_mixed_content(update, content_items)
        else:
            # Если только URL - обрабатываем напрямую (старая логика)
            await self._process_urls(update, urls)

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
        content_items = pending.get("content_items", [])

        # Удаляем из кэша
        del self.pending_choices[user_id]

        # Удаляем сообщение с выбором
        await self.delete_message(chat_id, message_id)

        # Обрабатываем выбор
        if choice.startswith("content_"):
            await self._process_content_choice(update, content_items, choice)
        elif choice == "smart_confirm":
            # Умный режим подтвержден
            intent = pending.get("intent", {"type": "all"})
            await self._process_content_by_intent(update, content_items, intent)
        elif choice == "smart_change":
            # Пользователь хочет изменить выбор
            await self._ask_user_choice(update, content_items)
        elif choice == "choice_photo":
            # Legacy: Обрабатываем фото
            await self.photo_handler.handle_photo_message(update)
        elif choice == "choice_url":
            # Legacy: Обрабатываем URL
            urls = [item.data for item in content_items if item.type in ["url", "youtube"]]
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

    # ============ Новые методы для смешанного контента ============

    def _create_content_choice_keyboard(self, content_items: List[ContentItem]) -> dict:
        """
        Создает inline клавиатуру для выбора типа контента

        Args:
            content_items: Список элементов контента

        Returns:
            Inline keyboard markup
        """
        buttons = []

        # Группируем по типам
        grouped = {}
        for item in content_items:
            if item.type not in grouped:
                grouped[item.type] = []
            grouped[item.type].append(item)

        # Эмодзи для типов
        emoji_map = {
            "text": "📝",
            "image": "🖼",
            "url": "🔗",
            "youtube": "▶️",
            "pdf": "📄",
            "document": "📎",
            "voice": "🎤",
            "audio": "🎵"
        }

        # Отдельные кнопки для каждого типа
        for content_type, items in grouped.items():
            emoji = emoji_map.get(content_type, "•")
            count = len(items)

            if count == 1:
                if content_type == "text":
                    text = f"{emoji} Текст"
                elif content_type == "image":
                    text = f"{emoji} Изображение"
                elif content_type == "url":
                    text = f"{emoji} Ссылку"
                elif content_type == "youtube":
                    text = f"{emoji} YouTube"
                else:
                    text = f"{emoji} {content_type.capitalize()}"
            else:
                if content_type == "image":
                    text = f"{emoji} Все изображения ({count})"
                elif content_type in ["url", "youtube"]:
                    text = f"{emoji} Все ссылки ({count})"
                else:
                    text = f"{emoji} Все ({count})"

            buttons.append([{
                "text": text,
                "callback_data": f"content_{content_type}"
            }])

        # Комбинированные кнопки если есть текст + картинки/ссылки
        if "text" in grouped and ("image" in grouped or "url" in grouped or "youtube" in grouped):
            combo_text = "📝🖼 Текст + картинки" if "image" in grouped else "📝🔗 Текст + ссылки"
            buttons.append([{
                "text": combo_text,
                "callback_data": "content_text_and_media"
            }])

        # Кнопка "Всё вместе"
        if len(grouped) > 1:
            buttons.append([{
                "text": "🎯 Всё вместе",
                "callback_data": "content_all"
            }])

        # Кнопка "Умный выбор"
        buttons.append([{
            "text": "🤖 Умный выбор",
            "callback_data": "content_smart"
        }])

        return {"inline_keyboard": buttons}

    async def _detect_user_intent(self, text: str, content_items: List[ContentItem]) -> dict:
        """
        Определяет намерение пользователя через LLM

        Args:
            text: Текст сообщения от пользователя
            content_items: Список элементов контента

        Returns:
            dict с информацией о намерении: {"type": "text", "reason": "..."}
        """
        # Формируем описание контента
        content_desc = []
        for item in content_items:
            content_desc.append(f"- {item.type}: {item.description}")

        content_list = "\n".join(content_desc)

        # Промпт для определения намерения
        prompt = f"""Проанализируй сообщение пользователя и определи, какой контент он хочет обработать.

Текст пользователя: "{text}"

Доступный контент:
{content_list}

Определи, что пользователь хочет обработать. Варианты:
- text: только текст
- image: только изображения
- url: только ссылки
- text_and_media: текст вместе с картинками/ссылками
- all: всё вместе

Ответь ТОЛЬКО в формате JSON: {{"type": "...", "reason": "краткое объяснение"}}
Если не уверен - выбери "all"."""

        try:
            response = generate_completion(
                prompt=prompt,
                system="Ты - эксперт по анализу намерений пользователя. Отвечай только валидным JSON.",
                temperature=0.1,
                max_tokens=150
            )

            if response:
                # Парсим JSON ответ
                import json
                # Извлекаем JSON из ответа
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    intent = json.loads(json_match.group())
                    return intent
        except Exception as e:
            logger.error(f"Ошибка определения намерения: {e}")

        # По умолчанию - всё вместе
        return {"type": "all", "reason": "не удалось определить намерение"}

    def _get_intent_description(self, intent: dict, content_items: List[ContentItem]) -> str:
        """
        Формирует описание намерения для пользователя

        Args:
            intent: Результат _detect_user_intent
            content_items: Список элементов контента

        Returns:
            Строка с описанием
        """
        intent_type = intent.get("type", "all")

        # Считаем количество элементов каждого типа
        counts = {}
        for item in content_items:
            counts[item.type] = counts.get(item.type, 0) + 1

        descriptions = {
            "text": "текст",
            "image": f"{counts.get('image', 0)} изображение(й)" if "image" in counts else "изображения",
            "url": f"{counts.get('url', 0) + counts.get('youtube', 0)} ссылку(и)" if ("url" in counts or "youtube" in counts) else "ссылки",
            "text_and_media": "текст + все картинки/ссылки",
            "all": "всё вместе"
        }

        return descriptions.get(intent_type, "весь контент")

    async def _process_content_choice(self, update: dict, content_items: List[ContentItem], choice: str):
        """
        Обрабатывает выбор пользователя по типу контента

        Args:
            update: Telegram update object
            content_items: Список элементов контента
            choice: Выбор пользователя (content_text, content_image, content_url и т.д.)
        """
        choice_type = choice.replace("content_", "")

        if choice_type == "text":
            # Обработать только текст
            text_items = [item for item in content_items if item.type == "text"]
            if text_items:
                text = text_items[0].data
                await self.text_handler.handle_text_message(update, message_text=text)

        elif choice_type == "image":
            # Обработать изображения
            await self.photo_handler.handle_photo_message(update)

        elif choice_type == "url" or choice_type == "youtube":
            # Обработать ссылки
            urls = [item.data for item in content_items if item.type in ["url", "youtube"]]
            if urls:
                await self._process_urls(update, urls)

        elif choice_type == "text_and_media":
            # Обработать текст + медиа (пока просто весь контент)
            await self._process_all_content_together(update, content_items)

        elif choice_type == "all":
            # Обработать всё вместе
            await self._process_all_content_together(update, content_items)

        elif choice_type == "smart":
            # Умный выбор - запускаем определение намерения
            message = update["message"]
            text = message.get("text") or message.get("caption", "")
            intent = await self._detect_user_intent(text, content_items)
            await self._process_content_by_intent(update, content_items, intent)

        else:
            logger.warning(f"Неизвестный тип выбора: {choice_type}")

    async def _process_content_by_intent(self, update: dict, content_items: List[ContentItem], intent: dict):
        """
        Обрабатывает контент согласно определенному намерению

        Args:
            update: Telegram update object
            content_items: Список элементов контента
            intent: Результат определения намерения
        """
        intent_type = intent.get("type", "all")

        # Маппинг намерений на типы выбора
        choice_map = {
            "text": "content_text",
            "image": "content_image",
            "url": "content_url",
            "text_and_media": "content_text_and_media",
            "all": "content_all"
        }

        choice = choice_map.get(intent_type, "content_all")
        await self._process_content_choice(update, content_items, choice)

    async def _process_all_content_together(self, update: dict, content_items: List[ContentItem]):
        """
        Обрабатывает весь контент вместе

        Args:
            update: Telegram update object
            content_items: Список элементов контента
        """
        message = update["message"]
        chat_id = message["chat"]["id"]

        # Собираем весь текстовый контент
        all_text_parts = []

        # Текст из сообщения
        text_items = [item for item in content_items if item.type == "text"]
        if text_items:
            all_text_parts.append(f"📝 Текст сообщения:\n{text_items[0].data}")

        # Текст из URL
        urls = [item.data for item in content_items if item.type in ["url", "youtube"]]
        if urls:
            url_texts = []
            for url in urls:
                text, title = await self.url_processor.process_url(url)
                if text:
                    header = f"🔗 {title}" if title else f"🔗 Контент из {url}"
                    url_texts.append(f"{header}:\n{text}")

            if url_texts:
                all_text_parts.extend(url_texts)

        # Если есть изображения - обрабатываем их отдельно
        if any(item.type == "image" for item in content_items):
            # Сначала обрабатываем фото
            await self.photo_handler.handle_photo_message(update)

        # Объединяем весь текст и обрабатываем
        if all_text_parts:
            combined_text = "\n\n---\n\n".join(all_text_parts)
            modified_update = {
                "message": {
                    **update["message"],
                    "text": combined_text
                }
            }
            await self.text_handler.handle_text_message(modified_update, message_text=combined_text)

    async def _get_user_content_settings(self, user_id: int) -> dict:
        """
        Получает настройки обработки контента для пользователя

        Args:
            user_id: ID пользователя

        Returns:
            dict с настройками: {"content_mode": "ask"|"smart"|"all"}
        """
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            settings = await loop.run_in_executor(None, self.db.get_user_settings, user_id)
            return {
                "content_mode": settings.get("content_mode", "ask")
            }
        except Exception as e:
            logger.error(f"Ошибка получения настроек пользователя {user_id}: {e}")
            return {"content_mode": "ask"}
