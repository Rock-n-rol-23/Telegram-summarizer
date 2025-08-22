"""
Улучшенный экстрактор веб-контента с многоступенчатым пайплайном
Поддерживает trafilatura → readability-lxml → bs4-эвристики с кэшированием
"""

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from lxml import html
from lxml.html.clean import Cleaner
from readability import Document

logger = logging.getLogger(__name__)

# Конфигурация
WEB_ACCEPT_LANGUAGE = os.getenv("WEB_ACCEPT_LANGUAGE", "ru,en-US;q=0.9,en;q=0.8")
WEB_FETCH_TIMEOUT_S = float(os.getenv("WEB_FETCH_TIMEOUT_S", "12"))
WEB_CACHE_TTL_H = int(os.getenv("WEB_CACHE_TTL_H", "72"))

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

@dataclass
class ExtractedPage:
    """Результат извлечения контента со страницы"""
    url: str
    final_url: str
    title: Optional[str]
    byline: Optional[str]
    published_at: Optional[str]  # ISO 8601 если найдено
    lang: Optional[str]
    text: str  # очищенный основной текст
    links: List[Dict[str, str]]  # [{"text": "...", "href": "https://...", "title": "..."}]
    meta: Dict[str, str]  # og:title, og:site_name, description и т.п.
    word_count: int
    char_count: int


class WebExtractionError(Exception):
    """Базовое исключение для ошибок извлечения веб-контента"""
    pass


class NetworkError(WebExtractionError):
    """Сетевые ошибки"""
    pass


class ContentError(WebExtractionError):
    """Ошибки обработки контента"""
    pass


class WebCache:
    """Простой кэш для веб-страниц в SQLite"""
    
    def __init__(self, db_path: str = "web_cache.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Инициализация таблицы кэша"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS web_cache (
                    url_hash TEXT PRIMARY KEY,
                    final_url TEXT,
                    fetched_at INTEGER,
                    etag TEXT,
                    last_modified TEXT,
                    text_hash TEXT,
                    meta_json TEXT,
                    text BLOB
                )
            """)
            conn.commit()
    
    def _url_hash(self, url: str) -> str:
        """Создает хэш URL для ключа кэша"""
        return hashlib.sha256(url.encode('utf-8')).hexdigest()
    
    def get(self, url: str) -> Optional[ExtractedPage]:
        """Получает страницу из кэша, если она не устарела"""
        url_hash = self._url_hash(url)
        ttl_seconds = WEB_CACHE_TTL_H * 3600
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM web_cache WHERE url_hash = ? AND fetched_at > ?",
                (url_hash, int(time.time()) - ttl_seconds)
            )
            row = cursor.fetchone()
            
            if row:
                try:
                    meta = json.loads(row['meta_json'])
                    return ExtractedPage(
                        url=url,
                        final_url=row['final_url'],
                        title=meta.get('title'),
                        byline=meta.get('byline'),
                        published_at=meta.get('published_at'),
                        lang=meta.get('lang'),
                        text=row['text'],
                        links=meta.get('links', []),
                        meta=meta.get('page_meta', {}),
                        word_count=meta.get('word_count', 0),
                        char_count=meta.get('char_count', 0)
                    )
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Ошибка десериализации кэша для {url}: {e}")
        
        return None
    
    def put(self, page: ExtractedPage):
        """Сохраняет страницу в кэш"""
        url_hash = self._url_hash(page.url)
        text_hash = hashlib.sha256(page.text.encode('utf-8')).hexdigest()
        
        meta = {
            'title': page.title,
            'byline': page.byline,
            'published_at': page.published_at,
            'lang': page.lang,
            'links': page.links,
            'page_meta': page.meta,
            'word_count': page.word_count,
            'char_count': page.char_count
        }
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO web_cache 
                (url_hash, final_url, fetched_at, etag, last_modified, text_hash, meta_json, text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                url_hash,
                page.final_url,
                int(time.time()),
                None,  # etag
                None,  # last_modified
                text_hash,
                json.dumps(meta, ensure_ascii=False),
                page.text
            ))
            conn.commit()


# Глобальный экземпляр кэша
_cache = WebCache()


async def extract_url(url: str, *, accept_lang: str = WEB_ACCEPT_LANGUAGE, timeout_s: float = WEB_FETCH_TIMEOUT_S) -> ExtractedPage:
    """
    Главная функция: скачивает страницу, извлекает основной контент многоступенчато, 
    нормализует и возвращает ExtractedPage.
    """
    logger.info(f"Извлечение контента с {url}")
    
    # Проверяем кэш
    cached_page = _cache.get(url)
    if cached_page:
        logger.info(f"Найдена кэшированная версия для {url}")
        return cached_page
    
    # Скачиваем страницу
    raw_html, final_url = await _fetch_page(url, accept_lang, timeout_s)
    
    # Извлекаем контент многоступенчато
    page = _extract_content(url, final_url, raw_html)
    
    # Сохраняем в кэш
    _cache.put(page)
    
    logger.info(f"Извлечено {page.char_count} символов с {final_url}")
    return page


async def _fetch_page(url: str, accept_lang: str, timeout_s: float) -> tuple[str, str]:
    """Скачивает HTML страницы с правильными заголовками и таймаутами"""
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": accept_lang,
        "Cache-Control": "no-cache",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    timeout = httpx.Timeout(
        connect=5.0,
        read=timeout_s - 5.0,
        write=5.0,
        pool=5.0
    )
    
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=5,
            timeout=timeout,
            headers=headers
        ) as client:
            
            # Опциональная проверка HEAD запросом
            try:
                head_response = await client.head(url)
                content_type = head_response.headers.get("content-type", "").lower()
                if content_type and "text/html" not in content_type:
                    raise ContentError(f"Похоже, это не статья (тип: {content_type}). Пришлите обычную веб-страницу.")
            except httpx.RequestError:
                # Если HEAD не работает, продолжаем с GET
                pass
            
            # Основной GET запрос
            response = await client.get(url)
            response.raise_for_status()
            
            # Проверяем Content-Type в ответе
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type:
                raise ContentError(f"Похоже, это не статья (тип: {content_type}). Пришлите обычную веб-страницу.")
            
            final_url = str(response.url)
            html_content = response.text
            
            if not html_content or len(html_content) < 100:
                raise ContentError("Страница слишком короткая или пустая")
            
            return html_content, final_url
            
    except httpx.TimeoutException:
        raise NetworkError(f"Не удалось загрузить страницу за {timeout_s}с. Попробуйте позже.")
    except httpx.ConnectError:
        raise NetworkError("Не удалось подключиться к серверу. Проверьте ссылку.")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise NetworkError("Страница не найдена (404)")
        elif e.response.status_code == 403:
            raise NetworkError("Доступ к странице запрещен (403)")
        elif e.response.status_code >= 500:
            raise NetworkError("Ошибка сервера. Попробуйте позже.")
        else:
            raise NetworkError(f"Ошибка HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при загрузке {url}: {e}")
        raise NetworkError("Не удалось загрузить страницу. Проверьте ссылку или попробуйте позже.")


def _extract_content(original_url: str, final_url: str, raw_html: str) -> ExtractedPage:
    """Извлекает контент многоступенчато: trafilatura → readability → bs4"""
    
    logger.debug(f"Начинаю извлечение контента с {final_url}")
    
    # Шаг A: trafilatura
    extracted_text, metadata = _extract_with_trafilatura(raw_html, final_url)
    if extracted_text and len(extracted_text) >= 800:
        logger.debug("Успешно извлечено с помощью trafilatura")
        links = _extract_links_from_html(raw_html, final_url)
        meta = _extract_page_metadata(raw_html)
        return _build_extracted_page(
            original_url, final_url, extracted_text, metadata, links, meta
        )
    
    # Шаг B: readability-lxml
    extracted_text, metadata = _extract_with_readability(raw_html, final_url)
    if extracted_text and len(extracted_text) >= 500:
        logger.debug("Успешно извлечено с помощью readability-lxml")
        links = _extract_links_from_html(raw_html, final_url)
        meta = _extract_page_metadata(raw_html)
        return _build_extracted_page(
            original_url, final_url, extracted_text, metadata, links, meta
        )
    
    # Шаг C: bs4-эвристики
    extracted_text, metadata = _extract_with_bs4_heuristics(raw_html, final_url)
    if extracted_text and len(extracted_text) >= 350:
        logger.debug("Успешно извлечено с помощью bs4-эвристик")
        links = _extract_links_from_html(raw_html, final_url)
        meta = _extract_page_metadata(raw_html)
        return _build_extracted_page(
            original_url, final_url, extracted_text, metadata, links, meta
        )
    
    # Если все методы не сработали
    raise ContentError(
        "Не удалось извлечь полезный текст со страницы. "
        "Возможно, это динамический/защищённый контент или страница требует JavaScript."
    )


def _extract_with_trafilatura(raw_html: str, final_url: str) -> tuple[Optional[str], dict]:
    """Извлечение с помощью trafilatura"""
    try:
        # Извлекаем текст
        text = trafilatura.extract(
            raw_html,
            url=final_url,
            include_comments=False,
            include_tables=True,  # Включаем таблицы
            output_format="txt"
        )
        
        # Добавляем извлеченные таблицы в Markdown формате
        tables_markdown = extract_tables_as_markdown(raw_html)
        if tables_markdown:
            text = text + "\n\n[Таблицы]\n" + tables_markdown
        
        # Извлекаем метаданные
        metadata = {}
        try:
            from trafilatura.metadata import extract_metadata
            meta_result = extract_metadata(raw_html, url=final_url)
            if meta_result:
                metadata = {
                    'title': meta_result.title,
                    'byline': meta_result.author,
                    'published_at': meta_result.date,
                    'lang': meta_result.language,
                    'site_name': meta_result.sitename
                }
        except Exception as e:
            logger.debug(f"Ошибка извлечения метаданных trafilatura: {e}")
        
        return text, metadata
        
    except Exception as e:
        logger.debug(f"Ошибка trafilatura: {e}")
        return None, {}


def _extract_with_readability(raw_html: str, final_url: str) -> tuple[Optional[str], dict]:
    """Извлечение с помощью readability-lxml"""
    try:
        doc = Document(raw_html)
        
        # Получаем HTML контент
        content_html = doc.summary()
        
        if content_html:
            # Очищаем HTML от ненужных тегов
            cleaner = Cleaner(
                scripts=True,
                style=True,
                embedded=True,
                forms=True,
                remove_unknown_tags=False,
                kill_tags=['nav', 'header', 'footer', 'aside']
            )
            
            try:
                clean_tree = html.fromstring(content_html)
                cleaner(clean_tree)
                text = clean_tree.text_content()
            except Exception:
                # Fallback: простое удаление тегов
                soup = BeautifulSoup(content_html, 'html.parser')
                text = soup.get_text()
            
            # Нормализуем текст
            text = _normalize_text(text)
            
            metadata = {
                'title': doc.title() or None,
                'lang': None  # readability не извлекает язык
            }
            
            return text, metadata
        
    except Exception as e:
        logger.debug(f"Ошибка readability: {e}")
    
    return None, {}


def _extract_with_bs4_heuristics(raw_html: str, final_url: str) -> tuple[Optional[str], dict]:
    """Извлечение с помощью bs4-эвристик"""
    try:
        soup = BeautifulSoup(raw_html, 'html5lib')
        
        # Удаляем ненужные элементы
        for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
        
        # Удаляем элементы по классам и ID
        unwanted_selectors = [
            '.ad', '.ads', '.advertisement', '.social', '.breadcrumbs', 
            '.subscribe', '.newsletter', '.sidebar', '.menu', '.navigation',
            '#header', '#footer', '#sidebar', '#nav', '#navigation'
        ]
        
        for selector in unwanted_selectors:
            try:
                for element in soup.select(selector):
                    element.decompose()
            except Exception:
                continue
        
        # Ищем основной контент
        content_candidates = []
        
        # Ищем по семантическим тегам
        for tag in ['article', 'main', 'section', 'div']:
            elements = soup.find_all(tag)
            for element in elements:
                text = element.get_text()
                if len(text.strip()) > 200:
                    content_candidates.append((len(text), element))
        
        if content_candidates:
            # Берем самый длинный контейнер
            content_candidates.sort(key=lambda x: x[0], reverse=True)
            best_element = content_candidates[0][1]
            
            # Извлекаем текст из параграфов и заголовков
            text_parts = []
            for element in best_element.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li']):
                text = element.get_text().strip()
                if text and len(text) > 20:
                    text_parts.append(text)
            
            if text_parts:
                full_text = '\n\n'.join(text_parts)
                normalized_text = _normalize_text(full_text)
                
                # Извлекаем заголовок
                title = None
                title_element = soup.find('h1') or soup.find('title')
                if title_element:
                    title = title_element.get_text().strip()
                
                metadata = {'title': title}
                return normalized_text, metadata
        
    except Exception as e:
        logger.debug(f"Ошибка bs4-эвристик: {e}")
    
    return None, {}


def _normalize_text(text: str) -> str:
    """Нормализует текст: убирает лишние пробелы, разбивает на абзацы"""
    if not text:
        return ""
    
    # Заменяем неразрывные пробелы
    text = text.replace('\xa0', ' ')
    
    # Нормализуем пробелы, но сохраняем переводы строк для абзацев
    text = re.sub(r'[ \t]+', ' ', text)  # Множественные пробелы и табы
    text = re.sub(r'\n[ \t]*\n', '\n\n', text)  # Множественные переводы строк
    
    # Убираем распространенные "хвосты"
    patterns_to_remove = [
        r'поделиться.*?$',
        r'читать также.*?$', 
        r'подписыв.*?$',
        r'следить за.*?$',
        r'комментарии.*?$'
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    # Разбиваем слишком длинные абзацы
    paragraphs = text.split('\n\n')
    result_paragraphs = []
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
            
        if len(paragraph) <= 1000:
            result_paragraphs.append(paragraph)
        else:
            # Разбиваем длинный абзац по предложениям
            sentences = re.split(r'[.!?]+\s+', paragraph)
            current_part = ""
            
            for sentence in sentences:
                if len(current_part + sentence) <= 1000:
                    current_part += sentence + ". "
                else:
                    if current_part:
                        result_paragraphs.append(current_part.strip())
                    current_part = sentence + ". "
            
            if current_part:
                result_paragraphs.append(current_part.strip())
    
    return '\n\n'.join(result_paragraphs).strip()


def extract_tables_as_markdown(html: str) -> str:
    """Извлекает таблицы из HTML и конвертирует их в Markdown"""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table')
        
        if not tables:
            return ""
        
        markdown_tables = []
        
        for i, table in enumerate(tables[:5]):  # Ограничиваем до 5 таблиц
            try:
                # Извлекаем заголовки
                headers = []
                header_row = table.find('thead') or table.find('tr')
                if header_row:
                    header_cells = header_row.find_all(['th', 'td'])
                    for cell in header_cells:
                        text = cell.get_text().strip()
                        headers.append(text if text else f"Колонка {len(headers) + 1}")
                
                if not headers:
                    continue
                
                # Извлекаем данные
                rows = []
                tbody = table.find('tbody') or table
                data_rows = tbody.find_all('tr')[1 if table.find('thead') else 0:]  # Пропускаем заголовочную строку
                
                for row in data_rows[:20]:  # Ограничиваем до 20 строк
                    cells = row.find_all(['td', 'th'])
                    if cells:
                        row_data = []
                        for j, cell in enumerate(cells):
                            if j >= len(headers):  # Не больше чем заголовков
                                break
                            text = cell.get_text().strip()
                            # Очищаем от переносов и лишних пробелов
                            text = ' '.join(text.split())
                            row_data.append(text if text else "-")
                        
                        # Дополняем недостающие колонки
                        while len(row_data) < len(headers):
                            row_data.append("-")
                        
                        rows.append(row_data)
                
                if rows:
                    # Формируем Markdown таблицу
                    markdown_table = []
                    
                    # Заголовки
                    markdown_table.append("| " + " | ".join(headers) + " |")
                    # Разделитель
                    markdown_table.append("| " + " | ".join(["---"] * len(headers)) + " |")
                    
                    # Данные
                    for row in rows:
                        markdown_table.append("| " + " | ".join(row) + " |")
                    
                    table_name = f"Таблица {i + 1}"
                    if len(tables) == 1:
                        table_name = "Таблица"
                    
                    markdown_tables.append(f"{table_name}:\n" + "\n".join(markdown_table))
            
            except Exception as e:
                logger.debug(f"Ошибка обработки таблицы {i + 1}: {e}")
                continue
        
        return "\n\n".join(markdown_tables) if markdown_tables else ""
    
    except Exception as e:
        logger.debug(f"Ошибка извлечения таблиц: {e}")
        return ""


def _extract_links_from_html(raw_html: str, final_url: str) -> List[Dict[str, str]]:
    """Извлекает и нормализует ссылки из HTML"""
    try:
        soup = BeautifulSoup(raw_html, 'html.parser')
        links = []
        seen_hrefs = set()
        
        for link in soup.find_all('a', href=True):
            href = link['href'].strip()
            text = link.get_text().strip()
            title = link.get('title', '').strip()
            
            # Пропускаем якоря, mailto, tel
            if href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
                continue
            
            # Нормализуем URL
            try:
                full_url = urljoin(final_url, href)
                parsed = urlparse(full_url)
                
                # Оставляем только http(s) ссылки
                if parsed.scheme not in ('http', 'https'):
                    continue
                
                # Дедупликация
                if full_url in seen_hrefs:
                    continue
                
                seen_hrefs.add(full_url)
                
                if text and len(text) > 3:  # Пропускаем слишком короткие тексты
                    links.append({
                        'text': text[:100],  # Ограничиваем длину
                        'href': full_url,
                        'title': title[:100] if title else ''
                    })
                
                # Ограничиваем количество ссылок
                if len(links) >= 50:
                    break
                    
            except Exception:
                continue
        
        return links[:10]  # Возвращаем только первые 10
        
    except Exception as e:
        logger.debug(f"Ошибка извлечения ссылок: {e}")
        return []


def _extract_page_metadata(raw_html: str) -> Dict[str, str]:
    """Извлекает метаданные страницы"""
    try:
        soup = BeautifulSoup(raw_html, 'html.parser')
        meta = {}
        
        # Open Graph метаданные
        for tag in soup.find_all('meta', property=True):
            prop = tag.get('property', '').lower()
            content = tag.get('content', '').strip()
            if prop.startswith('og:') and content:
                meta[prop] = content
        
        # Стандартные метаданные
        for tag in soup.find_all('meta', attrs={'name': True}):
            name = tag.get('name', '').lower()
            content = tag.get('content', '').strip()
            if name in ['description', 'keywords', 'author', 'date'] and content:
                meta[name] = content
        
        # Даты из различных источников
        date_selectors = [
            'meta[property="article:published_time"]',
            'meta[name="date"]',
            'meta[name="DC.date"]',
            'time[datetime]'
        ]
        
        for selector in date_selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    date_value = element.get('content') or element.get('datetime')
                    if date_value:
                        meta['published_date'] = date_value
                        break
            except Exception:
                continue
        
        return meta
        
    except Exception as e:
        logger.debug(f"Ошибка извлечения метаданных: {e}")
        return {}


def _build_extracted_page(
    original_url: str,
    final_url: str, 
    text: str,
    metadata: dict,
    links: List[Dict[str, str]],
    page_meta: Dict[str, str]
) -> ExtractedPage:
    """Строит финальный объект ExtractedPage"""
    
    # Подсчитываем статистику
    word_count = len(text.split())
    char_count = len(text)
    
    # Определяем заголовок (приоритет: og:title > title из metadata)
    title = page_meta.get('og:title') or metadata.get('title')
    
    # Если заголовок все еще не найден, пытаемся извлечь из raw HTML
    if not title:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup('', 'html.parser')  # Placeholder, так как у нас нет HTML здесь
            # В реальности это должно работать с исходным HTML
        except:
            pass
    
    # Определяем язык
    lang = metadata.get('lang')
    
    # Нормализуем дату
    published_at = metadata.get('published_at') or page_meta.get('published_date')
    
    return ExtractedPage(
        url=original_url,
        final_url=final_url,
        title=title,
        byline=metadata.get('byline'),
        published_at=published_at,
        lang=lang,
        text=text,
        links=links,
        meta=page_meta,
        word_count=word_count,
        char_count=char_count
    )