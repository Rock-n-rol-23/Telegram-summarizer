"""Детектор типов контента в сообщениях"""

import logging
import re
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ContentItem:
    """Элемент контента"""
    type: str  # 'text', 'image', 'url', 'pdf', 'youtube'
    data: any  # данные элемента (текст, file_id, url и т.д.)
    size: int = 0  # размер в символах/байтах для отображения
    description: str = ""  # описание для пользователя


class ContentDetector:
    """Детектор смешанного контента в сообщениях"""

    def __init__(self):
        self.youtube_patterns = [
            r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
        ]
        self.url_pattern = r'https?://[^\s]+'

    def detect_content_types(self, message: dict) -> List[ContentItem]:
        """
        Определяет все типы контента в сообщении

        Args:
            message: Telegram message object

        Returns:
            List[ContentItem]: Список найденных элементов контента
        """
        content_items = []

        # 1. Текст (из text или caption)
        text = message.get("text") or message.get("caption", "")
        if text:
            # Извлекаем URL из текста для отдельной обработки
            youtube_urls = self._extract_youtube_urls(text)
            regular_urls = self._extract_urls(text)

            # Удаляем URL из текста для проверки оставшегося контента
            clean_text = text
            for url in youtube_urls + regular_urls:
                clean_text = clean_text.replace(url, "").strip()

            # Если есть текст помимо URL
            if clean_text and len(clean_text) >= 50:
                content_items.append(ContentItem(
                    type="text",
                    data=clean_text,
                    size=len(clean_text),
                    description=f"Текст ({len(clean_text)} символов)"
                ))

            # YouTube ссылки
            for url in youtube_urls:
                content_items.append(ContentItem(
                    type="youtube",
                    data=url,
                    size=0,
                    description=f"YouTube видео"
                ))

            # Обычные URL
            for url in regular_urls:
                content_items.append(ContentItem(
                    type="url",
                    data=url,
                    size=0,
                    description=f"Ссылка: {self._shorten_url(url)}"
                ))

        # 2. Фото
        if "photo" in message:
            photo = message["photo"][-1]  # Самое большое разрешение
            content_items.append(ContentItem(
                type="image",
                data=photo,
                size=photo.get("file_size", 0),
                description=f"Изображение ({photo.get('width', 0)}×{photo.get('height', 0)} px)"
            ))

        # 3. Документы (PDF и др.)
        if "document" in message:
            doc = message["document"]
            mime_type = doc.get("mime_type", "")
            file_name = doc.get("file_name", "document")
            file_size = doc.get("file_size", 0)

            # Определяем тип документа
            if "pdf" in mime_type.lower() or file_name.lower().endswith(".pdf"):
                doc_type = "pdf"
                desc = f"PDF: {file_name} ({self._format_size(file_size)})"
            else:
                doc_type = "document"
                desc = f"Документ: {file_name} ({self._format_size(file_size)})"

            content_items.append(ContentItem(
                type=doc_type,
                data=doc,
                size=file_size,
                description=desc
            ))

        # 4. Аудио/Голосовые сообщения
        if "voice" in message:
            voice = message["voice"]
            duration = voice.get("duration", 0)
            content_items.append(ContentItem(
                type="voice",
                data=voice,
                size=voice.get("file_size", 0),
                description=f"Голосовое сообщение ({self._format_duration(duration)})"
            ))

        if "audio" in message:
            audio = message["audio"]
            duration = audio.get("duration", 0)
            title = audio.get("title", "Аудиофайл")
            content_items.append(ContentItem(
                type="audio",
                data=audio,
                size=audio.get("file_size", 0),
                description=f"Аудио: {title} ({self._format_duration(duration)})"
            ))

        return content_items

    def is_mixed_content(self, content_items: List[ContentItem]) -> bool:
        """Проверяет, является ли контент смешанным (>1 типа)"""
        # Считаем уникальные типы контента
        content_types = set(item.type for item in content_items)

        # Группируем похожие типы
        # YouTube и обычные URL - это один тип "ссылки"
        if "youtube" in content_types or "url" in content_types:
            content_types.discard("youtube")
            content_types.discard("url")
            content_types.add("links")

        # voice и audio - это один тип "аудио"
        if "voice" in content_types or "audio" in content_types:
            content_types.discard("voice")
            content_types.discard("audio")
            content_types.add("audio")

        return len(content_types) > 1

    def get_content_summary(self, content_items: List[ContentItem]) -> str:
        """
        Формирует текстовое описание найденного контента

        Returns:
            Строка вида:
            "📎 Обнаружено несколько типов контента:
             ┣ 📝 Текст (250 символов)
             ┣ 🖼 2 изображения
             ┗ 🔗 1 ссылка"
        """
        if not content_items:
            return "❌ Контент не найден"

        # Группируем по типам
        grouped = {}
        for item in content_items:
            if item.type not in grouped:
                grouped[item.type] = []
            grouped[item.type].append(item)

        # Формируем описание
        lines = ["📎 Обнаружено несколько типов контента:"]

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

        # Названия типов
        type_names = {
            "text": "Текст",
            "image": "изображение",
            "url": "ссылка",
            "youtube": "YouTube видео",
            "pdf": "PDF",
            "document": "документ",
            "voice": "голосовое сообщение",
            "audio": "аудиофайл"
        }

        items_sorted = sorted(grouped.items(), key=lambda x: (
            0 if x[0] == "text" else
            1 if x[0] == "image" else
            2 if x[0] in ["url", "youtube"] else
            3
        ))

        for i, (content_type, items) in enumerate(items_sorted):
            emoji = emoji_map.get(content_type, "•")
            type_name = type_names.get(content_type, content_type)
            count = len(items)

            # Формируем строку
            if count == 1:
                detail = items[0].description
                if content_type == "text":
                    line = f"┣ {emoji} {detail}"
                else:
                    line = f"┣ {emoji} {type_name}"
            else:
                # Множественное число
                if content_type == "image":
                    plural = f"{count} изображения" if count < 5 else f"{count} изображений"
                elif content_type in ["url", "youtube"]:
                    plural = f"{count} ссылки" if count < 5 else f"{count} ссылок"
                else:
                    plural = f"{count} {type_name}"

                line = f"┣ {emoji} {plural}"

            # Последний элемент с другим символом
            if i == len(items_sorted) - 1:
                line = line.replace("┣", "┗")

            lines.append(line)

        return "\n".join(lines)

    # ============ Вспомогательные методы ============

    def _extract_youtube_urls(self, text: str) -> List[str]:
        """Извлечение YouTube URL из текста"""
        urls = []
        for pattern in self.youtube_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                urls.append(f"https://www.youtube.com/watch?v={match}")
        return urls

    def _extract_urls(self, text: str) -> List[str]:
        """Извлечение обычных URL из текста (без YouTube)"""
        urls = re.findall(self.url_pattern, text)
        # Фильтруем YouTube URL
        urls = [url for url in urls if 'youtube.com' not in url and 'youtu.be' not in url]
        return urls

    def _shorten_url(self, url: str, max_length: int = 40) -> str:
        """Сокращает URL для отображения"""
        if len(url) <= max_length:
            return url
        return url[:max_length-3] + "..."

    def _format_size(self, size_bytes: int) -> str:
        """Форматирует размер файла"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _format_duration(self, seconds: int) -> str:
        """Форматирует длительность"""
        if seconds < 60:
            return f"{seconds}с"
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}м {secs}с"
