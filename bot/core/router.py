"""Маршрутизатор обновлений от Telegram"""

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class UpdateRouter:
    """Маршрутизатор обновлений к соответствующим handlers"""

    def __init__(self):
        self.logger = logger

    def route(self, update: dict) -> Tuple[str, Optional[dict]]:
        """
        Определяет тип обновления и возвращает соответствующий handler и данные

        Returns:
            Tuple[handler_type, extra_data]
            handler_type: 'command', 'text', 'document', 'audio', 'callback', 'youtube', 'url'
            extra_data: дополнительные данные для handler (например, название команды)
        """

        # Callback query (нажатия на inline кнопки)
        if "callback_query" in update:
            return ("callback", None)

        # Обычные сообщения
        if "message" not in update:
            logger.warning(f"Неизвестный тип обновления: {update.keys()}")
            return ("unknown", None)

        message = update["message"]

        # Команды (начинаются с /)
        if "text" in message and message["text"].startswith("/"):
            command = message["text"].split()[0].lower()
            return self._route_command(command)

        # Документы
        if "document" in message:
            return ("document", None)

        # Аудио (voice, audio, video_note)
        if any(key in message for key in ["voice", "audio", "video_note"]):
            return ("audio", None)

        # Фото - проверяем наличие URL в caption
        if "photo" in message:
            # Проверяем caption на наличие URL
            caption = message.get("caption", "")
            if caption:
                # Проверяем наличие обычных URL
                urls = self._extract_urls(caption)
                if urls:
                    logger.info(f"Получено фото с {len(urls)} URL в caption, маршрутизация в ChoiceHandler")
                    return ("photo_with_url", {"urls": urls})

            logger.info("Получено фото, маршрутизация в PhotoHandler")
            return ("photo", None)

        # Видео, стикеры и другие медиа - обрабатываем caption или игнорируем
        if any(key in message for key in ["video", "sticker", "animation", "video_note"]):
            # Если есть caption, обрабатываем как текст
            if "caption" in message and message["caption"].strip():
                text = message["caption"]

                # Проверяем наличие YouTube ссылок
                youtube_urls = self._extract_youtube_urls(text)
                if youtube_urls:
                    return ("youtube", {"urls": youtube_urls})

                # Проверяем наличие обычных URL
                urls = self._extract_urls(text)
                if urls:
                    return ("url", {"urls": urls})

                # Обычный текст из caption
                return ("text", None)
            else:
                # Медиа без текста - игнорируем
                logger.info(f"Получено медиа без caption, игнорируем: {list(message.keys())}")
                return ("unknown", None)

        # Текстовые сообщения с URL
        if "text" in message:
            text = message["text"]

            # Проверяем наличие YouTube ссылок
            youtube_urls = self._extract_youtube_urls(text)
            if youtube_urls:
                return ("youtube", {"urls": youtube_urls})

            # Проверяем наличие обычных URL
            urls = self._extract_urls(text)
            if urls:
                return ("url", {"urls": urls})

            # Обычный текст
            return ("text", None)

        # Неизвестный тип
        logger.warning(f"Не удалось определить тип сообщения: {message.keys()}")
        return ("unknown", None)

    def _route_command(self, command: str) -> Tuple[str, dict]:
        """Маршрутизация команд"""

        # Команды обработки
        command_map = {
            "/start": "start",
            "/help": "help",
            "/stats": "stats",
            "/smart": "smart_mode",
            "/audio_settings": "audio_settings",
            "/short": "compression_10",
            "/balanced": "compression_30",
            "/detailed": "compression_60",
            "/10": "direct_compression_10",
            "/30": "direct_compression_30",
            "/50": "direct_compression_50",
        }

        if command in command_map:
            return ("command", {"command": command_map[command]})

        # Неизвестная команда - обрабатываем как обычный текст
        logger.info(f"Неизвестная команда: {command}, обрабатываем как текст")
        return ("text", None)

    def _extract_youtube_urls(self, text: str) -> list:
        """Извлечение YouTube URL из текста"""
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
        ]

        urls = []
        for pattern in youtube_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                urls.append(f"https://www.youtube.com/watch?v={match}")

        return urls

    def _extract_urls(self, text: str) -> list:
        """Извлечение обычных URL из текста"""
        # Простой паттерн для URL
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, text)

        # Фильтруем YouTube URL (они обрабатываются отдельно)
        urls = [url for url in urls if 'youtube.com' not in url and 'youtu.be' not in url]

        return urls
