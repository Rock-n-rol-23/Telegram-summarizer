"""
URL Processor - обработка обычных веб-ссылок
"""

import logging
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Optional
import re

logger = logging.getLogger(__name__)


class URLProcessor:
    """Процессор для обработки обычных URL"""

    def __init__(self):
        logger.info("URLProcessor инициализирован")
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    async def process_url(self, url: str) -> tuple[str, str]:
        """
        Обработка URL и извлечение контента

        Args:
            url: URL для обработки

        Returns:
            Tuple (text, title) - извлеченный текст и заголовок из URL
            В случае ошибки возвращает ("", "")
        """
        try:
            logger.info(f"Парсинг URL: {url}")

            # Валидация URL
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=self.headers, allow_redirects=True) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка загрузки URL {url}: статус {response.status}")
                        return "", ""

                    # Проверяем Content-Type
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'text/html' not in content_type:
                        logger.warning(f"URL {url} не является HTML страницей: {content_type}")
                        return "", ""

                    html = await response.text()

            # Парсинг HTML
            soup = BeautifulSoup(html, 'html.parser')

            # Извлекаем заголовок
            title = ""
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text().strip()

            # Удаляем скрипты, стили и другие нежелательные теги
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript']):
                tag.decompose()

            # Пытаемся найти основной контент
            # Приоритет: article > main > body
            main_content = None

            # 1. Ищем <article>
            article = soup.find('article')
            if article:
                main_content = article
                logger.debug("Найден тег <article>")

            # 2. Ищем <main>
            if not main_content:
                main_tag = soup.find('main')
                if main_tag:
                    main_content = main_tag
                    logger.debug("Найден тег <main>")

            # 3. Ищем div с классами content, post-content, article-body и т.д.
            if not main_content:
                content_div = soup.find(['div', 'section'], class_=re.compile(
                    r'(content|article|post|entry|main|body)', re.IGNORECASE
                ))
                if content_div:
                    main_content = content_div
                    logger.debug("Найден div с классом content")

            # 4. Если ничего не найдено, берем весь body
            if not main_content:
                main_content = soup.find('body')
                logger.debug("Используем весь <body>")

            # Извлекаем текст
            if main_content:
                text = main_content.get_text(separator='\n', strip=True)
            else:
                text = soup.get_text(separator='\n', strip=True)

            # Нормализация текста
            text = self._normalize_text(text)

            logger.info(f"Успешно извлечен текст из {url}: {len(text)} символов, заголовок: {title}")
            return text, title

        except asyncio.TimeoutError:
            logger.error(f"Таймаут при загрузке URL: {url}")
            return "", ""
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка при загрузке URL {url}: {e}")
            return "", ""
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при парсинге URL {url}: {e}", exc_info=True)
            return "", ""

    def _normalize_text(self, text: str) -> str:
        """
        Нормализация извлеченного текста

        Args:
            text: Исходный текст

        Returns:
            Нормализованный текст
        """
        if not text:
            return ""

        # Удаляем множественные пробелы
        text = re.sub(r' +', ' ', text)

        # Удаляем множественные переносы строк (больше 2)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Удаляем пробелы в начале и конце строк
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)

        return text.strip()
