#!/usr/bin/env python3
# coding: utf-8
"""
Simple Telegram Bot для суммаризации текста и веб-страниц
Минимальная версия с прямым использованием Telegram Bot API
"""

import logging
import asyncio
import json
import time
import re
from datetime import datetime
from typing import Dict, Set, Optional, Callable, Any
import os
import sys
import aiohttp
import sqlite3
from groq import Groq
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import validators
from urllib.parse import urlparse
from functools import wraps

# Настройка логирования
# Используем JSON формат для production, обычный для development
USE_JSON_LOGGING = os.getenv('USE_JSON_LOGGING', 'false').lower() == 'true'

if USE_JSON_LOGGING:
    # JSON formatter для structured logging
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            log_data = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno
            }
            if record.exc_info:
                log_data['exception'] = self.formatException(record.exc_info)
            return json.dumps(log_data, ensure_ascii=False)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
else:
    # Обычный формат для development
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# from readability import parse  # Убрано из-за проблем с установкой
from youtube_processor import YouTubeProcessor
from file_processor import FileProcessor
from audio_processor import AudioProcessor
from smart_summarizer import SmartSummarizer
from utils.tg_audio import (
    extract_audio_descriptor,
    get_audio_info_text,
    format_duration,
    is_audio_document,
)

# Импорт утилит для обработки текста
from bot.text_utils import extract_text_from_message
from bot.state_manager import StateManager, UserStep

# Импорт интегрированной системы суммаризации
try:
    from integrated_summarizer import IntegratedSummarizer, get_integrated_summarizer
    INTEGRATED_SUMMARIZATION_AVAILABLE = True
    logger.info("Интегрированная система суммаризации доступна")
except ImportError as e:
    INTEGRATED_SUMMARIZATION_AVAILABLE = False
    logger.warning(f"Интегрированная система суммаризации недоступна: {e}")

# Импорты для улучшенной аудио обработки
try:
    from summarizers.audio_pipeline import summarize_audio_file, format_audio_result, get_pipeline_info
    from bot.ui_settings import init_settings_manager, get_user_audio_settings, get_settings_manager
    from bot.ui_settings import generate_settings_keyboard, generate_format_keyboard, generate_verbosity_keyboard
    from bot.ui_settings import format_settings_message, get_format_confirmation_message, get_verbosity_confirmation_message
    ENHANCED_AUDIO_AVAILABLE = True
    logger.info("Улучшенная аудио обработка доступна")
except ImportError as e:
    ENHANCED_AUDIO_AVAILABLE = False
    logger.warning(f"Улучшенная аудио обработка недоступна: {e}")

# HTML константа для приветственного сообщения
WELCOME_MESSAGE_HTML = """👋 <b>Привет!</b> Я превращаю длинные тексты в короткие выжимки с ключевыми мыслями.

🎯 <b>Просто отправь мне:</b>
• 📝 Текст или статью
• 🌐 Ссылку на веб-страницу
• 📄 Документ (PDF, DOCX, TXT)
• 📚 Книгу (EPUB, FB2)
• ▶️ YouTube видео
• 🗣️ Аудио или голосовое

<b>Я автоматически:</b>
✨ Выберу лучший формат
✨ Адаптирую стиль под тип контента
✨ Выделю самое важное

🎛️ <b>Не нравится результат?</b>
<code>/short</code> — покороче (главные мысли)
<code>/balanced</code> — сбалансированно (по умолчанию)
<code>/detailed</code> — поподробнее (всё важное)

💡 <code>/help</code> — полная справка
📊 <code>/stats</code> — твоя статистика

🚀 <b>Готов!</b> Отправь текст или ссылку прямо сейчас."""

# ============================================================================
# Retry decorator для API вызовов
# ============================================================================

def retry_on_failure(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Декоратор для retry с экспоненциальным backoff

    Args:
        max_retries: Максимальное количество попыток
        delay: Начальная задержка в секундах
        backoff: Множитель для экспоненциального backoff
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    # Проверяем, стоит ли повторять
                    if attempt < max_retries - 1:
                        # Логируем только для важных ошибок
                        error_msg = str(e).lower()
                        if any(keyword in error_msg for keyword in ['rate limit', 'timeout', 'connection', 'temporary']):
                            logger.warning(f"Попытка {attempt + 1}/{max_retries} не удалась: {e}. Повтор через {current_delay:.1f}s")
                            time.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            # Не повторяем для критичных ошибок (invalid key, etc)
                            raise
                    else:
                        logger.error(f"Все {max_retries} попыток исчерпаны")

            # Если все попытки исчерпаны, пробрасываем последнюю ошибку
            raise last_exception

        return wrapper
    return decorator


class SimpleTelegramBot:
    """Простой Telegram бот для суммаризации текста"""
    
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.groq_api_key = os.getenv('GROQ_API_KEY')

        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN не найден в переменных окружения")

        # Инициализация Groq клиента
        self.groq_client = None
        if self.groq_api_key:
            try:
                self.groq_client = Groq(api_key=self.groq_api_key)
                logger.info("Groq API клиент инициализирован")
            except (ValueError, KeyError, ImportError) as e:
                logger.error(f"Ошибка инициализации Groq API: {e}")

        # Базовый URL для Telegram API
        self.base_url = f"https://api.telegram.org/bot{self.token}"

        # Централизованная aiohttp сессия (будет создана при запуске)
        self.session: Optional[aiohttp.ClientSession] = None

        # Защита от спама
        self.user_requests: Dict[int, list] = {}
        self.processing_users: Set[int] = set()

        # Метрики для мониторинга
        self.metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'api_retries': 0,
            'start_time': time.time()
        }

        # Состояния пользователей для настраиваемой суммаризации
        # TODO: Legacy dictionaries - постепенно мигрируем на StateManager
        self.user_states: Dict[int, dict] = {}
        self.user_settings: Dict[int, dict] = {}

        # Временное хранение сообщений для объединения
        self.user_messages_buffer: Dict[int, list] = {}

        # Новый менеджер состояний (параллельно со старыми словарями)
        self.state_manager = StateManager()
        logger.info("StateManager инициализирован")

        # Инициализация базы данных
        from database import DatabaseManager
        from concurrent.futures import ThreadPoolExecutor
        database_url = os.getenv('DATABASE_URL', 'sqlite:///bot_database.db')
        self.db = DatabaseManager(database_url)
        self.db.init_database()

        # Executor для синхронных DB операций (избегаем блокировки event loop)
        self.db_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="db_")
        
        # Инициализация YouTube процессора
        self.youtube_processor = YouTubeProcessor(groq_client=self.groq_client)
        logger.info("YouTube процессор инициализирован")
        
        # Инициализация файлового процессора
        self.file_processor = FileProcessor()
        logger.info("Файловый процессор инициализирован")
        
        # Инициализация аудио процессора
        if self.groq_client:
            self.audio_processor = AudioProcessor(groq_client=self.groq_client)
            logger.info("Аудио процессор инициализирован")
        else:
            self.audio_processor = None
            logger.warning("Аудио процессор не инициализирован - отсутствует Groq API key")
        
        # Инициализация умного суммаризатора
        if self.groq_client:
            self.smart_summarizer = SmartSummarizer(groq_client=self.groq_client)
            logger.info("Умный суммаризатор инициализирован")
        else:
            self.smart_summarizer = None
            logger.warning("Умный суммаризатор не инициализирован - отсутствует Groq API key")
        
        # Инициализация улучшенной аудио системы
        if ENHANCED_AUDIO_AVAILABLE:
            try:
                init_settings_manager(self.db)
                logger.info("Менеджер настроек аудио инициализирован")
            except (sqlite3.Error, ValueError) as e:
                logger.warning(f"Ошибка инициализации настроек аудио: {e}")
        
        # Инициализация системы дайджестов
        try:
            from digest.db import init_digest_db
            from digest.scheduler import start_scheduler
            
            # Инициализация базы данных дайджестов
            init_digest_db()
            logger.info("База данных дайджестов инициализирована")
            
            # Запуск планировщика дайджестов
            start_scheduler(self)
            logger.info("Планировщик дайджестов запущен")
            
            self.digest_enabled = True
        except Exception as e:
            logger.warning(f"Ошибка инициализации системы дайджестов: {e}")
            self.digest_enabled = False
        
        logger.info("Simple Telegram Bot инициализирован")

    def get_metrics(self) -> dict:
        """Получить метрики бота для мониторинга"""
        uptime = time.time() - self.metrics['start_time']
        return {
            **self.metrics,
            'uptime_seconds': int(uptime),
            'active_users': len(self.user_requests),
            'processing_users': len(self.processing_users)
        }

    async def _create_session(self):
        """Создание aiohttp сессии"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=60, connect=10)
            self.session = aiohttp.ClientSession(timeout=timeout)
            logger.info("HTTP сессия создана")

    async def _close_session(self):
        """Закрытие aiohttp сессии"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("HTTP сессия закрыта")

    async def _run_in_executor(self, func, *args):
        """Запуск синхронной функции в executor (для DB операций)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.db_executor, func, *args)

    async def _shutdown(self):
        """Полное закрытие всех ресурсов"""
        logger.info("Закрытие ресурсов бота...")
        await self._close_session()
        if hasattr(self, 'db_executor'):
            self.db_executor.shutdown(wait=True)
            logger.info("DB executor остановлен")

    def extract_urls_from_message(self, text: str) -> list:
        """Извлекает все URL из текста сообщения"""
        # Паттерн для поиска URL
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, text)
        
        # Проверяем валидность каждого URL
        valid_urls = []
        for url in urls:
            if validators.url(url):
                valid_urls.append(url)
        
        return valid_urls
    
    def extract_webpage_content(self, url: str, timeout: int = 30) -> dict:
        """Извлекает основной текст с веб-страницы"""
        try:
            # Расширенные заголовки для лучшего обхода блокировок
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
            
            # Загрузка страницы с увеличенным timeout для медленных сайтов
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            
            # Проверка размера контента (максимум 5MB)
            if len(response.content) > 5 * 1024 * 1024:
                raise Exception("Файл слишком большой для обработки")
            
            # Парсинг HTML
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Получение заголовка страницы
            title_tag = soup.find('title')
            title = title_tag.get_text().strip() if title_tag else "Без заголовка"
            
            # Проверка на Cloudflare и другие блокировки
            cloudflare_indicators = [
                'just a moment', 'challenge-platform', 'cloudflare',
                'please wait while your request is being verified',
                'enable javascript and cookies to continue',
                '_cf_chl_opt', 'cf-browser-verification'
            ]
            
            page_text = response.text.lower()
            if any(indicator in page_text for indicator in cloudflare_indicators):
                return {
                    'success': False,
                    'error': f'Сайт использует защиту от ботов (Cloudflare). Попробуйте скопировать текст статьи вручную или найти альтернативный источник.',
                    'title': title,
                    'blocked': True
                }
            
            # Удаление ненужных элементов
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript']):
                element.decompose()
            
            # Извлечение основного контента
            # Пытаемся найти основной контент по распространенным селекторам
            main_content = None
            content_selectors = [
                'article', 'main', '.content', '#content', '.post-content', 
                '.article-content', '.entry-content', '.post-body', '.story-body',
                '.news-content', '.article-body'
            ]
            
            for selector in content_selectors:
                content_element = soup.select_one(selector)
                if content_element and len(content_element.get_text().strip()) > 200:
                    main_content = content_element
                    break
            
            # Если основной контент не найден, используем весь текст
            if main_content:
                text = main_content.get_text()
            else:
                text = soup.get_text()
            
            # Очистка текста
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            # Проверка на минимальную длину контента
            if len(text) < 100:
                return {
                    'success': False,
                    'error': 'Страница не содержит достаточно текстового контента или контент не удалось извлечь',
                    'title': title,
                    'content_too_short': True
                }
            
            return {
                'title': title,
                'content': text,
                'url': url,
                'success': True
            }
            
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Время ожидания истекло (сайт отвечает слишком медленно)'}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'Не удается подключиться к сайту (проверьте URL или доступность сайта)'}
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 'неизвестный'
            error_msg = {
                403: 'Доступ запрещен (сайт блокирует ботов)',
                404: 'Страница не найдена',
                429: 'Слишком много запросов (сайт временно ограничил доступ)',
                500: 'Внутренняя ошибка сервера',
                502: 'Плохой шлюз',
                503: 'Сервис временно недоступен'
            }.get(status_code, f'Ошибка HTTP {status_code}')
            return {'success': False, 'error': error_msg}
        except Exception as e:
            return {'success': False, 'error': f'Ошибка при обработке: {str(e)[:100]}...'}
    
    def is_url_allowed(self, url: str) -> bool:
        """Проверяет, разрешен ли URL для обработки"""
        blocked_domains = [
            'facebook.com', 'instagram.com', 'twitter.com', 'x.com',
            'youtube.com', 'tiktok.com', 'vk.com'  # Социальные сети сложно парсить
        ]
        
        domain = urlparse(url).netloc.lower()
        
        for blocked in blocked_domains:
            if blocked in domain:
                return False
        return True
    
    def simple_text_summary(self, text: str, max_sentences: int = 3) -> str:
        """Простая суммаризация без AI - берет первые предложения"""
        # Разбивка на предложения
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        
        # Берем первые несколько предложений
        summary_sentences = sentences[:max_sentences]
        summary = '. '.join(summary_sentences)
        
        if len(summary) > 500:
            summary = summary[:500] + "..."
        
        return summary
    
    async def get_user_compression_level(self, user_id: int) -> int:
        """Получение уровня сжатия пользователя из базы данных (async)"""
        try:
            settings = await self._run_in_executor(self.db.get_user_settings, user_id)
            return settings.get('compression_level', 30)  # По умолчанию 30%
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Ошибка получения настроек пользователя {user_id}: {e}")
            return 30

    def update_user_compression_level(self, user_id: int, compression_level: int, username: str = ""):
        """Обновление уровня сжатия пользователя в базе данных"""
        try:
            logger.info(f"SimpleTelegramBot: начинаю обновление уровня сжатия для пользователя {user_id}: {compression_level}%")
            self.db.update_compression_level(user_id, compression_level, username)
            logger.info(f"SimpleTelegramBot: уровень сжатия для пользователя {user_id} успешно обновлен: {compression_level}%")
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"SimpleTelegramBot: ошибка обновления уровня сжатия для пользователя {user_id}: {e}")
            raise


    
    async def send_message(self, chat_id: int, text: str, parse_mode: Optional[str] = None, reply_markup: Optional[dict] = None):
        """Отправка сообщения с поддержкой inline-клавиатур"""
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text[:4096]  # Telegram ограничивает длину сообщения
        }
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = reply_markup  # Убираем json.dumps()
        
        logger.info(f"📤 SEND_MESSAGE: Отправка сообщения в чат {chat_id}")

        try:
            # Используем json=data когда есть reply_markup, иначе data=data
            if reply_markup:
                async with self.session.post(url, json=data) as response:
                    result = await response.json()
            else:
                async with self.session.post(url, data=data) as response:
                    result = await response.json()

            if result.get("ok"):
                logger.info(f"Сообщение успешно отправлено в чат {chat_id}")
            else:
                logger.error(f"Ошибка отправки сообщения в чат {chat_id}: {result}")
            return result
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка отправки сообщения в чат {chat_id}: {e}")
            return None
    

    
    def check_user_rate_limit(self, user_id: int) -> bool:
        """Проверка лимита запросов пользователя"""
        now = time.time()
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        
        # Удаляем запросы старше 1 минуты
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id] 
            if now - req_time < 60
        ]
        
        # Проверяем лимит (10 запросов в минуту)
        if len(self.user_requests[user_id]) >= 10:
            return False
        
        self.user_requests[user_id].append(now)
        return True
    
    async def summarize_text(self, text: str, target_ratio: float = 0.3) -> str:
        """Суммаризация текста с помощью Groq API"""
        if not self.groq_client:
            return "❌ Groq API недоступен. Пожалуйста, проверьте настройки."
        
        try:
            # Дополнительная нормализация текста перед отправкой в API
            try:
                import re
                # Убираем проблемные символы и нормализуем пробелы
                text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)  # Удаляем управляющие символы
                text = re.sub(r'\s+', ' ', text)  # Заменяем множественные пробелы
                text = text.strip()
                
                if not text:
                    return "❌ Текст пуст после нормализации"
                    
            except (RuntimeError, ValueError) as norm_error:
                logger.warning(f"Ошибка при дополнительной нормализации: {norm_error}")
                # Продолжаем с исходным текстом
            
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

            # Используем retry для устойчивости к временным сбоям API
            @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
            def call_groq_api():
                return self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.3,
                    max_tokens=2000,
                    top_p=0.9,
                    stream=False
                )

            response = call_groq_api()
            
            if response.choices and response.choices[0].message:
                summary = response.choices[0].message.content
                if summary:
                    return summary.strip()
            return "❌ Не удалось получить ответ от модели"
            
        except Exception as e:
            logger.error(f"Ошибка при суммаризации: {e}")
            import traceback
            logger.error(f"Детали ошибки суммаризации: {traceback.format_exc()}")
            return f"❌ Ошибка при обработке текста: {str(e)[:100]}"

    def _detect_content_type(self, title: str, text: str, url: str = "") -> str:
        """Определение типа веб-контента для адаптивного промпта"""
        combined = f"{title} {text[:500]}".lower()

        # Ключевые слова для определения типа
        if any(word in combined for word in ['tutorial', 'how to', 'guide', 'инструкция', 'как ', 'шаг']):
            return 'tutorial'
        elif any(word in combined for word in ['research', 'study', 'analysis', 'исследование', 'анализ', 'научн']):
            return 'research'
        elif any(word in combined for word in ['news', 'breaking', 'новост', 'сообщается', 'заявил']):
            return 'news'
        elif any(word in combined for word in ['blog', 'opinion', 'блог', 'мнение', 'думаю', 'считаю']):
            return 'blog'
        elif any(word in combined for word in ['documentation', 'docs', 'api', 'документация']):
            return 'documentation'
        else:
            return 'article'

    async def summarize_web_content(self, text: str, title: str = "", url: str = "", target_ratio: float = 0.3) -> str:
        """Адаптивная саммаризация веб-контента с учетом типа"""
        if not self.groq_client:
            return "❌ Groq API недоступен"

        try:
            # Определяем тип контента
            content_type = self._detect_content_type(title, text, url)

            # Адаптивный промпт в зависимости от типа
            if content_type == 'tutorial':
                structure = """• **Цель:** [Чему учит]
• **Основные шаги:** [Пошаговая инструкция]
• **Важные моменты:** [Ключевые детали и советы]
• **Результат:** [Что получится в итоге]"""
            elif content_type == 'research':
                structure = """• **Тема исследования:** [Что изучалось]
• **Методология:** [Как проводилось]
• **Результаты:** [Что обнаружили]
• **Выводы:** [Заключения авторов]"""
            elif content_type == 'news':
                structure = """• **Суть новости:** [Что произошло - 1-2 предложения]
• **Детали:** [Ключевые факты]
• **Цитаты:** [Важные высказывания, если есть]
• **Контекст:** [Почему это важно]"""
            elif content_type == 'blog':
                structure = """• **Главная мысль:** [О чем пишет автор]
• **Аргументы:** [Ключевые тезисы]
• **Примеры:** [Конкретные случаи, если есть]
• **Вывод автора:** [Заключение]"""
            else:  # article или documentation
                structure = """• **Тема:** [О чем статья]
• **Ключевые моменты:** [3-5 главных пунктов]
• **Важные детали:** [Факты, цифры, термины]
• **Выводы:** [Главные заключения]"""

            target_length = int(len(text) * target_ratio)

            prompt = f"""Проанализируй веб-страницу и создай структурированное резюме на том же языке, что и текст.

📄 ИНФОРМАЦИЯ:
Заголовок: {title}
Тип контента: {content_type}

📋 СТРУКТУРА РЕЗЮМЕ (~{target_length} символов):
{structure}

ТРЕБОВАНИЯ:
- Пиши кратко и структурированно
- Сохраняй все факты, цифры, имена
- Используй bullet points (•)
- Не добавляй информацию, которой нет в тексте

ТЕКСТ СТРАНИЦЫ:
{text[:8000]}"""

            @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
            def call_groq_api():
                return self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.3,
                    max_tokens=2000,
                    top_p=0.9,
                    stream=False
                )

            response = call_groq_api()

            if response.choices and response.choices[0].message:
                summary = response.choices[0].message.content
                if summary:
                    return summary.strip()
            return "❌ Не удалось получить ответ от модели"

        except Exception as e:
            logger.error(f"Ошибка при веб-саммаризации: {e}")
            return f"❌ Ошибка: {str(e)[:100]}"

    async def handle_start_command(self, update: dict):
        """Обработка команды /start"""
        chat_id = update["message"]["chat"]["id"]
        user = update["message"]["from"]
        
        logger.info(f"Обработка команды /start от пользователя {user.get('id')} в чате {chat_id}")
        
        # Очищаем любые пользовательские клавиатуры
        await self.clear_custom_keyboards(chat_id)
        
        await self.send_message(chat_id, WELCOME_MESSAGE_HTML, parse_mode="HTML")
    
    async def handle_help_command(self, update: dict):
        """Обработка команды /help"""
        chat_id = update["message"]["chat"]["id"]

        help_text = (
            "\U0001F4D6 **Полная справка**\n\n"
            "\U0001F3AF **КАК ПОЛЬЗОВАТЬСЯ:**\n"
            "Просто отправь текст, ссылку, документ или аудио — я автоматически подберу лучший формат саммари!\n\n"
            "\U0001F4DD **ЧТО Я УМЕЮ:**\n"
            "• Тексты и статьи — выжимка с фактами\n"
            "• Веб-ссылки — адаптивное резюме\n"
            "• PDF, DOCX, TXT — структурированное саммари\n"
            "• Книги (EPUB, FB2) — сюжет и идеи\n"
            "• YouTube (до 2 часов) — резюме по субтитрам\n"
            "• Аудио/голосовые — транскрипция + саммари\n\n"
            "\U0001F39B **УПРАВЛЕНИЕ ДЕТАЛЬНОСТЬЮ:**\n"
            "• <code>/short</code> — кратко (2-3 главные мысли)\n"
            "• <code>/balanced</code> — сбалансированно (рекомендуется) \u2728\n"
            "• <code>/detailed</code> — подробно (всё важное)\n\n"
            "\U0001F4CA **ДРУГИЕ КОМАНДЫ:**\n"
            "• <code>/stats</code> — твоя статистика\n"
            "• <code>/help</code> — эта справка\n"
            "• <code>/start</code> — перезапустить бота\n\n"
            "\U0001F4A1 **ЛИМИТЫ:**\n"
            "• 10 запросов в минуту\n"
            "• Документы до 20MB\n"
            "• Аудио до 50MB (~1 час)\n\n"
            "\U0001F525 **Powered by Llama 3.3 70B + Whisper large v3**\n\n"
            "\U0001F4AC Остались вопросы? Просто начни отправлять контент!"
        )

        await self.send_message(chat_id, help_text)

    async def handle_audio_settings_command(self, update: dict):
        """Обработка команды настроек аудио"""
        if not ENHANCED_AUDIO_AVAILABLE:
            await self.send_message(
                update["message"]["chat"]["id"], 
                "❌ Улучшенные настройки аудио недоступны - обновите бота"
            )
            return
        
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        try:
            settings_manager = get_settings_manager()
            if settings_manager:
                user_settings = settings_manager.get_user_settings(user_id)
                message_text = format_settings_message(user_settings)
                keyboard = generate_settings_keyboard()
                
                await self.send_message_with_keyboard(chat_id, message_text, keyboard)
            else:
                await self.send_message(chat_id, "❌ Система настроек недоступна")
                
        except Exception as e:
            logger.error(f"Ошибка настроек аудио для пользователя {user_id}: {e}")
            await self.send_message(chat_id, "❌ Ошибка загрузки настроек")

    async def handle_smart_mode_command(self, update: dict):
        """Обработка команды /smart - переключение в режим умной суммаризации"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]

        # Используем StateManager для управления smart_mode
        state = self.state_manager.get_state(user_id)
        state.smart_mode = not state.smart_mode
        new_mode = state.smart_mode

        # Синхронизация с legacy словарем (временно для обратной совместимости)
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {}
        self.user_settings[user_id]["smart_mode"] = new_mode
        
        if new_mode:
            mode_text = ("\U0001F9E0 **Умная суммаризация включена!**\n\n"
                        "Теперь бот создает концентрированные резюме с ключевыми инсайтами:\n\n"
                        "\U0001F3AF **Что получаете:**\n"
                        "• Только самые важные выводы и инсайты\n"
                        "• Автоматическое определение типа контента\n"
                        "• Извлечение критически важной информации\n\n"
                        "\U0001F4CA **Управление детальностью:**\n"
                        "• /10 → 2 ключевых инсайта (максимальное сжатие)\n"
                        "• /30 → 3 ключевых инсайта (сбалансированно)\n"
                        "• /50 → 4 ключевых инсайта (подробно)\n\n"
                        "Отправьте любой текст, документ, аудио или ссылку для умной обработки!\n\n"
                        "_Чтобы вернуться к обычной суммаризации, снова нажмите /smart_")
        else:
            mode_text = ("\U0001F4DD **Обычная суммаризация восстановлена**\n\n"
                        "Теперь бот использует стандартный режим суммаризации с настраиваемыми уровнями сжатия (10%, 30%, 50%).\n\n"
                        "Чтобы снова включить умную суммаризацию, нажмите /smart")

        await self.send_message(chat_id, mode_text)
        logger.info(f"Пользователь {user_id} {'включил' if new_mode else 'отключил'} умную суммаризацию")
    
    async def handle_stats_command(self, update: dict):
        """Обработка команды /stats"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        try:
            user_stats = self.db.get_user_stats(user_id)
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Ошибка получения статистики пользователя {user_id}: {e}")
            user_stats = {
                'total_requests': 0,
                'total_chars': 0,
                'total_summary_chars': 0,
                'avg_compression': 0,
                'first_request': None
            }
        
        stats_text = (
            f"\U0001F4CA Ваша статистика:\n\n"
            f"• Обработано текстов: {user_stats['total_requests']}\n"
            f"• Символов обработано: {user_stats['total_chars']:,}\n"
            f"• Символов в саммари: {user_stats['total_summary_chars']:,}\n"
            f"• Среднее сжатие: {user_stats['avg_compression']:.1%}\n"
            f"• Первый запрос: {user_stats['first_request'] or 'Нет данных'}\n\n"
            f"\U0001F4C8 Используйте бота для обработки длинных текстов и статей!"
        )
        
        await self.send_message(chat_id, stats_text)

    def get_compression_keyboard(self, current_level: int = None) -> dict:
        """Создание inline клавиатуры для выбора уровня сжатия"""
        buttons = [
            [
                {"text": "\U0001F525 Кратко" + (" ✓" if current_level == 15 else ""), "callback_data": "compression_15"},
                {"text": "\U0001F4CA Сбалансированно" + (" ✓" if current_level == 30 else ""), "callback_data": "compression_30"},
                {"text": "\U0001F4D6 Подробно" + (" ✓" if current_level == 50 else ""), "callback_data": "compression_50"}
            ]
        ]
        return {"inline_keyboard": buttons}

    async def handle_callback_query(self, callback_query: dict):
        """Обработка нажатий на inline кнопки"""
        try:
            query_id = callback_query["id"]
            user_id = callback_query["from"]["id"]
            username = callback_query["from"].get("username", "")
            callback_data = callback_query["data"]
            message = callback_query.get("message", {})
            chat_id = message.get("chat", {}).get("id")

            logger.info(f"Callback query от {user_id}: {callback_data}")

            # Обработка кнопок сжатия
            if callback_data.startswith("compression_"):
                compression_level = int(callback_data.split("_")[1])

                # Обновляем уровень сжатия в БД
                self.update_user_compression_level(user_id, compression_level, username)

                # Названия уровней
                level_names = {
                    15: "\U0001F525 Кратко",
                    30: "\U0001F4CA Сбалансированно",
                    50: "\U0001F4D6 Подробно"
                }
                level_name = level_names.get(compression_level, f"{compression_level}%")

                # Отправляем уведомление (всплывающее окно)
                await self.answer_callback_query(query_id, f"Выбран стиль: {level_name}")

                # Обновляем сообщение с новыми кнопками (галочка на выбранной)
                updated_text = (
                    f"\u2705 Стиль саммаризации изменён: {level_name}\n\n"
                    f"Теперь твои тексты будут обрабатываться в стиле \"{level_name}\".\n\n"
                    f"\U0001F4DD Просто отправь текст, статью или документ!\n\n"
                    f"\U0001F4A1 Используй кнопки ниже для быстрого переключения стиля:"
                )

                keyboard = self.get_compression_keyboard(current_level=compression_level)
                await self.edit_message(chat_id, message["message_id"], updated_text, reply_markup=keyboard)

                logger.info(f"Пользователь {user_id} изменил сжатие на {compression_level}% через кнопку")

        except Exception as e:
            logger.error(f"Ошибка обработки callback query: {e}")
            # Пытаемся ответить на callback чтобы убрать "часики" у пользователя
            try:
                await self.answer_callback_query(callback_query["id"], "Произошла ошибка")
            except:
                pass

    async def answer_callback_query(self, query_id: str, text: str = "", show_alert: bool = False):
        """Отправка ответа на callback query"""
        url = f"{self.api_url}/answerCallbackQuery"
        data = {
            "callback_query_id": query_id,
            "text": text,
            "show_alert": show_alert
        }
        async with self.session.post(url, json=data) as response:
            result = await response.json()
            if not result.get("ok"):
                logger.error(f"Ошибка answerCallbackQuery: {result}")
            return result

    async def handle_compression_command(self, update: dict, compression_level: int):
        """Обработка команд уровня детальности саммари"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]

        try:
            # Получаем username пользователя для логирования
            username = update["message"]["from"].get("username", "")

            # Сохраняем новый уровень сжатия в базе данных
            self.update_user_compression_level(user_id, compression_level, username)

            # Понятные названия уровней
            level_names = {
                10: "\U0001F525 Ультра-кратко",
                15: "\U0001F525 Кратко",
                30: "\U0001F4CA Сбалансированно",
                50: "\U0001F4D6 Подробно"
            }
            level_name = level_names.get(compression_level, f"{compression_level}%")

            confirmation_text = (
                f"\u2705 Стиль саммаризации изменён: {level_name}\n\n"
                f"Теперь твои тексты будут обрабатываться в стиле \"{level_name}\".\n\n"
                f"\U0001F4DD Просто отправь текст, статью или документ!\n\n"
                f"\U0001F4A1 Используй кнопки ниже для быстрого переключения стиля:"
            )

            # Отправляем с inline кнопками
            keyboard = self.get_compression_keyboard(current_level=compression_level)
            await self.send_message(chat_id, confirmation_text, reply_markup=keyboard)
            logger.info(f"Пользователь {user_id} изменил уровень сжатия на {compression_level}%")

        except Exception as e:
            logger.error(f"Ошибка обработки команды сжатия {compression_level}% для пользователя {user_id}: {e}")
            await self.send_message(chat_id, "\u274C Произошла ошибка при изменении настроек. Попробуйте еще раз.")
    

    

    

    
    async def send_text_request(self, chat_id: int, user_id: int):
        """Запрос текста для суммаризации"""
        settings = self.user_settings[user_id]
        compression_text = {"10": "10%", "30": "30%", "50": "50%"}[settings["compression"]]
        format_text = {
            "bullets": "маркированный список", 
            "paragraph": "связный абзац", 
            "keywords": "ключевые слова"
        }[settings["format"]]
        
        text = f"""✅ Настройки применены:
• Сжатие: {compression_text}
• Формат: {format_text}

📝 Теперь отправьте текст для суммаризации любым способом:

1️⃣ Напишите или вставьте текст прямо в чат
2️⃣ Перешлите одно или несколько сообщений
3️⃣ Отправьте несколько сообщений подряд - я их объединю

Минимум: 100 символов
Максимум: 10,000 символов

💡 Для отмены используйте команду /start"""
        
        await self.send_message(chat_id, text)
        
        # Устанавливаем состояние ожидания текста
        self.user_states[user_id]["step"] = "waiting_text"
    

    
    async def handle_custom_summarize_text(self, update: dict, text: str):
        """Обработка текста в режиме настраиваемой суммаризации"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        try:
            # Добавляем текст в буфер сообщений пользователя
            self.user_messages_buffer[user_id].append({
                "text": text,
                "timestamp": datetime.now(),
                "is_forwarded": "forward_from" in update["message"] or "forward_from_chat" in update["message"]
            })
            
            # Проверяем, нужно ли ждать еще сообщений
            total_chars = sum(len(msg["text"]) for msg in self.user_messages_buffer[user_id])
            
            if len(self.user_messages_buffer[user_id]) == 1 and total_chars >= 100:
                # Если это первое сообщение и оно достаточно длинное - обрабатываем сразу
                await self.process_custom_summarization(chat_id, user_id)
            elif len(self.user_messages_buffer[user_id]) > 1:
                # Если уже есть несколько сообщений - спрашиваем, продолжать ли сбор
                await self.send_message(chat_id, 
                    f"📝 Собрано сообщений: {len(self.user_messages_buffer[user_id])}\n"
                    f"📊 Общий объем: {total_chars:,} символов\n\n"
                    f"Отправьте текст: 'ok' для обработки или еще текст для добавления")
            else:
                # Слишком мало символов
                await self.send_message(chat_id, 
                    f"📝 Получено: {total_chars} символов\n"
                    f"Минимум: 100 символов\n\n"
                    f"Отправьте больше текста или пересланных сообщений.")
                    
        except Exception as e:
            logger.error(f"Ошибка обработки текста настраиваемой суммаризации: {e}")
            await self.send_message(chat_id, "❌ Произошла ошибка при обработке текста. Попробуйте снова.")
    
    async def process_custom_summarization(self, chat_id: int, user_id: int):
        """Выполнение настраиваемой суммаризации с выбранными параметрами"""
        try:
            if user_id not in self.user_settings or user_id not in self.user_messages_buffer:
                await self.send_message(chat_id, "❌ Настройки суммаризации не найдены. Используйте /summarize для начала.")
                return
            
            # Объединяем все сообщения
            combined_text = ""
            for msg in self.user_messages_buffer[user_id]:
                if combined_text:
                    combined_text += "\n\n"
                combined_text += msg["text"]
            
            total_chars = len(combined_text)
            
            if total_chars < 100:
                await self.send_message(chat_id, f"❌ Недостаточно текста для суммаризации ({total_chars} символов). Минимум: 100 символов.")
                return
                
            if total_chars > 10000:
                await self.send_message(chat_id, f"❌ Слишком много текста ({total_chars:,} символов). Максимум: 10,000 символов.")
                return
            
            # Отправляем сообщение о начале обработки
            processing_msg = await self.send_message(chat_id, "⏳ Обрабатываю текст с выбранными настройками...")
            
            # Получаем настройки пользователя
            settings = self.user_settings[user_id]
            compression_ratio = int(settings["compression"]) / 100.0
            format_type = settings["format"]
            
            # Выполняем настраиваемую суммаризацию
            summary = await self.custom_summarize_text(combined_text, compression_ratio, format_type)
            
            # Удаляем сообщение о обработке
            if processing_msg:
                await self.delete_message(chat_id, processing_msg.get("message_id"))
            
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
                # username = update["message"]["from"].get("username", "")
                # Используем executor для неблокирующей записи в БД
                await self._run_in_executor(
                    self.db.save_user_request,
                    user_id, "", total_chars, len(summary), 0.0, 'groq'
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
            await self.send_message(chat_id, "❌ Произошла ошибка при суммаризации. Попробуйте позже.")
    
    async def custom_summarize_text(self, text: str, compression_ratio: float, format_type: str) -> str:
        """Настраиваемая суммаризация текста с заданными параметрами"""
        try:
            target_length = int(len(text) * compression_ratio)
            
            # Определяем специфичные инструкции для каждого формата
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
- Расположи по важности: сначала центральные концепции"""
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
                @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
                def call_groq_api():
                    return self.groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.3,
                        max_tokens=2000,
                        top_p=0.9,
                        stream=False
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
    
    async def handle_text_message(self, update: dict, message_text: Optional[str] = None):
        """Обработка текстовых сообщений"""
        chat_id = update["message"]["chat"]["id"]
        user = update["message"]["from"]
        user_id = user["id"]
        username = user.get("username", "")
        

        
        # Используем переданный текст или извлекаем из сообщения
        if message_text:
            text = message_text
        else:
            # Используем импортированную функцию из bot.text_utils
            text = extract_text_from_message(update["message"])
            if not text:
                logger.error("Не удалось извлечь текст из сообщения")
                return
        
        logger.info(f"Получен текст от пользователя {user_id} ({username}), длина: {len(text)} символов")
        
        # Проверка лимита запросов
        if not self.check_user_rate_limit(user_id):
            await self.send_message(chat_id, "⏰ Превышен лимит запросов!\n\nПожалуйста, подождите минуту перед отправкой нового текста. Лимит: 10 запросов в минуту.")
            return
        
        # Проверка на повторную обработку
        if user_id in self.processing_users:
            await self.send_message(chat_id, "⚠️ Обработка в процессе!\n\nПожалуйста, дождитесь завершения предыдущего запроса.")
            return
        
        # Проверка минимальной длины текста
        if len(text) < 50:
            await self.send_message(chat_id, f"📝 Текст слишком короткий!\n\nДля качественной суммаризации нужно минимум 50 символов.\nВаш текст: {len(text)} символов.")
            return
        
        # Добавляем пользователя в список обрабатываемых
        self.processing_users.add(user_id)
        
        try:
            # Отправляем сообщение о начале обработки
            processing_response = await self.send_message(chat_id, "🤖 Обрабатываю ваш текст...\n\nЭто может занять несколько секунд.")
            processing_message_id = processing_response.get("result", {}).get("message_id") if processing_response else None
            
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
                        user_id, username, len(text), len(summary), processing_time, 'groq'
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
                
                await self.send_message(chat_id, response_text)
                
                logger.info(f"Успешно обработан текст пользователя {user_id}, сжатие: {compression_ratio:.1%}")
                
            else:
                # Удаляем сообщение о обработке
                if processing_message_id:
                    await self.delete_message(chat_id, processing_message_id)
                
                await self.send_message(chat_id, "❌ Ошибка при обработке текста!\n\nПопробуйте позже или обратитесь к администратору.")
                
                logger.error(f"Не удалось обработать текст пользователя {user_id}")
        
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Ошибка при обработке текста пользователя {user_id}: {str(e)}")
            
            await self.send_message(chat_id, f"❌ Произошла ошибка!\n\nПожалуйста, попробуйте позже.")
        
        finally:
            # Удаляем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)
    
    async def handle_document_message(self, update: dict):
        """Обработка документов (PDF, DOCX, DOC, TXT)"""
        try:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            username = message["from"].get("username", "")
            document = message["document"]
            
            # Проверка лимита запросов
            if not self.check_user_rate_limit(user_id):
                await self.send_message(chat_id, "⏰ Превышен лимит запросов!\n\nПожалуйста, подождите минуту перед отправкой нового файла. Лимит: 10 запросов в минуту.")
                return
            
            # Проверка на повторную обработку
            if user_id in self.processing_users:
                await self.send_message(chat_id, "⚠️ Обработка в процессе!\n\nПожалуйста, дождитесь завершения предыдущего запроса.")
                return
            
            # Добавляем пользователя в список обрабатываемых
            self.processing_users.add(user_id)
            
            # Проверяем информацию о файле
            file_name = document.get("file_name", "unknown")
            file_size = document.get("file_size", 0)
            
            logger.info(f"Получен документ от пользователя {user_id}: {file_name} ({file_size} байт)")
            
            # Отправляем сообщение о начале обработки
            processing_message = await self.send_message(chat_id, f"📄 Обрабатываю документ: {file_name}\n\n⏳ Извлекаю текст...")
            processing_message_id = processing_message.get("result", {}).get("message_id") if processing_message and processing_message.get("ok") else None
            
            try:
                # Получаем информацию о файле от Telegram
                file_info_response = await self.get_file_info(document["file_id"])
                if not file_info_response or not file_info_response.get("ok"):
                    await self.send_message(chat_id, "❌ Не удалось получить информацию о файле")
                    return
                
                file_info = file_info_response["result"]
                file_path = f"https://api.telegram.org/file/bot{self.token}/{file_info['file_path']}"
                
                # Обновляем сообщение о прогрессе
                if processing_message_id:
                    await self.edit_message(chat_id, processing_message_id, f"📄 Обрабатываю документ: {file_name}\n\n📥 Скачиваю файл...")
                
                # Используем file_processor для скачивания и обработки
                download_result = await self.file_processor.download_telegram_file(
                    {"file_path": file_path}, file_name, file_size, self.session
                )
                
                if not download_result["success"]:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, f"❌ {download_result['error']}")
                    return
                
                # Определяем прогресс сообщение в зависимости от типа файла
                extension = download_result["file_extension"].lower()
                if extension == '.pdf':
                    progress_text = f"📄 Обрабатываю документ: {file_name}\n\n🔍 Извлекаю текст (PDF → текстовый слой + OCR)..."
                elif extension == '.pptx':
                    progress_text = f"📊 Обрабатываю презентацию: {file_name}\n\n🎯 Извлекаю слайды и заметки..."
                elif extension in ('.png', '.jpg', '.jpeg'):
                    progress_text = f"🖼️ Обрабатываю изображение: {file_name}\n\n👁️ Распознаю текст (OCR)..."
                else:
                    progress_text = f"📄 Обрабатываю документ: {file_name}\n\n📝 Извлекаю текст..."
                
                if processing_message_id:
                    await self.edit_message(chat_id, processing_message_id, progress_text)
                
                # Извлекаем текст из файла
                text_result = self.file_processor.extract_text_from_file(
                    download_result["file_path"], 
                    download_result["file_extension"]
                )
                
                # Очищаем временные файлы
                self.file_processor.cleanup_temp_file(download_result["temp_dir"])
                
                if not text_result["success"]:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, f"❌ {text_result['error']}")
                    return
                
                extracted_text = text_result["text"]
                extraction_method = text_result.get("method", "unknown")
                extraction_meta = text_result.get("meta", {})
                
                # Проверяем длину извлеченного текста
                if len(extracted_text) < 100:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, f"📝 Текст слишком короткий!\n\nИз документа извлечено {len(extracted_text)} символов. Для качественной суммаризации нужно минимум 100 символов.")
                    return
                
                # Показываем информацию о методе извлечения
                if "ocr" in extraction_method and extraction_meta.get("ocr_pages"):
                    ocr_info = f"🔎 Режим: PDF → OCR (страницы: {','.join(map(str, extraction_meta['ocr_pages']))})"
                elif extraction_method == "python-pptx" and extraction_meta.get("slides"):
                    slides_count = extraction_meta.get("total_slides", len(extraction_meta["slides"]))
                    ocr_info = f"📊 Обнаружена презентация: {slides_count} слайдов"
                elif "ocr" in extraction_method:
                    ocr_info = f"👁️ Режим: OCR (распознавание текста)"
                else:
                    ocr_info = f"📝 Режим: {extraction_method}"
                
                if processing_message_id:
                    await self.edit_message(chat_id, processing_message_id, f"📄 Обрабатываю документ: {file_name}\n\n{ocr_info}\n\n🤖 Создаю резюме...")
                
                # Получаем уровень сжатия пользователя
                compression_ratio = await self.get_user_compression_level(user_id)

                # Определяем тип документа
                doc_type = self._detect_document_type(
                    extracted_text,
                    file_name,
                    download_result["file_extension"],
                    extraction_meta
                )

                # Саммаризируем с учетом типа документа
                if doc_type == 'book':
                    logger.info(f"📚 Обнаружена книга, используем специализированную саммаризацию")
                    summary = await self.summarize_book_content(
                        extracted_text,
                        metadata=extraction_meta,
                        compression_ratio=compression_ratio
                    )
                else:
                    summary = await self.summarize_file_content(
                        extracted_text,
                        file_name,
                        download_result["file_extension"],
                        compression_ratio
                    )
                
                if summary:
                    # Определяем иконку и заголовок по типу файла/документа
                    if doc_type == 'book':
                        icon = "📚"
                        display_type = "книги"
                        # Добавляем метаданные книги если есть
                        if extraction_meta.get('title') and extraction_meta.get('author'):
                            file_name = f"{extraction_meta['title']} ({extraction_meta['author']})"
                    elif extension == '.pptx':
                        icon = "📊"
                        display_type = "презентации"
                    elif extension in ('.png', '.jpg', '.jpeg'):
                        icon = "🖼️"
                        display_type = "изображения"
                    elif extension in ['.epub', '.fb2']:
                        icon = "📖"
                        display_type = "книги"
                    else:
                        icon = "📄"
                        display_type = "документа"

                    # Формируем дополнительную информацию
                    extra_info = ""
                    if extraction_meta.get("ocr_pages"):
                        extra_info = f"\n• OCR страницы: {', '.join(map(str, extraction_meta['ocr_pages']))}"
                    elif extraction_meta.get("total_slides"):
                        extra_info = f"\n• Слайды обработаны: {extraction_meta['slides_with_content']}/{extraction_meta['total_slides']}"
                    elif doc_type == 'book' and extraction_meta.get('author'):
                        extra_info = f"\n• Автор: {extraction_meta['author']}"
                        if extraction_meta.get('language'):
                            extra_info += f"\n• Язык: {extraction_meta['language']}"
                    
                    # Формируем итоговый ответ
                    response_text = f"""{icon} **Резюме {display_type}: {file_name}**

{summary}

📊 **Статистика:**
• Исходный текст: {len(extracted_text):,} символов
• Резюме: {len(summary):,} символов  
• Сжатие: {compression_ratio:.0%}
• Метод извлечения: {extraction_method}{extra_info}"""
                    
                    # Удаляем сообщение о обработке
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    
                    await self.send_message(chat_id, response_text)
                    
                    # Сохраняем в базу данных
                    try:
                        self.db.save_user_request(user_id, f"document:{file_name}", len(extracted_text), len(summary), 0.0, 'groq_document')
                    except (OSError, sqlite3.Error) as save_error:
                        logger.error(f"Ошибка сохранения запроса в БД: {save_error}")
                    
                    logger.info(f"Успешно обработан документ {file_name} пользователя {user_id}")
                    
                else:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, "❌ Ошибка при создании резюме документа!\n\nПопробуйте позже или обратитесь к администратору.")
                    
            except (sqlite3.Error, ValueError) as e:
                logger.error(f"Ошибка при обработке документа: {e}")
                if processing_message_id:
                    await self.delete_message(chat_id, processing_message_id)
                await self.send_message(chat_id, f"❌ Произошла ошибка при обработке документа!\n\nПожалуйста, попробуйте позже.")
                
        except Exception as e:
            logger.error(f"Общая ошибка при обработке документа: {e}")
            await self.send_message(chat_id, "❌ Произошла ошибка!\n\nПожалуйста, попробуйте позже.")
            
        finally:
            # Удаляем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)
    
    async def get_file_info(self, file_id: str):
        """Получает информацию о файле от Telegram API"""
        try:
            url = f"{self.base_url}/getFile"
            params = {"file_id": file_id}
            
            async with self.session.get(url, params=params) as response:
                    return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка получения информации о файле: {e}")
            return None
    
    async def _get_file_url(self, file_id: str) -> str:
        """Получает URL файла от Telegram API"""
        file_info_response = await self.get_file_info(file_id)
        if not file_info_response or not file_info_response.get("ok"):
            raise Exception("Не удалось получить информацию о файле")
        
        file_info = file_info_response["result"]
        return f"https://api.telegram.org/file/bot{self.token}/{file_info['file_path']}"

    async def on_voice(self, update: dict):
        """Обработчик голосовых сообщений"""
        voice = update["message"]["voice"]
        file_id = voice["file_id"]
        file_url = await self._get_file_url(file_id)
        await self._handle_audio(update, file_url, filename_hint="voice.ogg")

    async def on_audio(self, update: dict):
        """Обработчик аудио файлов"""
        audio = update["message"]["audio"]
        file_id = audio["file_id"]
        name = audio.get("file_name") or "audio.mp3"
        file_url = await self._get_file_url(file_id)
        await self._handle_audio(update, file_url, filename_hint=name)

    async def on_audio_document(self, update: dict):
        """Обработчик аудио документов"""
        doc = update["message"]["document"]
        file_id = doc["file_id"]
        name = doc.get("file_name") or "audio.bin"
        file_url = await self._get_file_url(file_id)
        await self._handle_audio(update, file_url, filename_hint=name)

    async def _handle_audio(self, update: dict, file_url: str, filename_hint: str):
        """Основной обработчик аудио"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        # Проверка лимита запросов
        if not self.check_user_rate_limit(user_id):
            await self.send_message(chat_id, "⏰ Превышен лимит запросов!\n\nПожалуйста, подождите минуту перед отправкой нового аудио. Лимит: 10 запросов в минуту.")
            return
        
        # Проверка на повторную обработку
        if user_id in self.processing_users:
            await self.send_message(chat_id, "⚠️ Обработка в процессе!\n\nПожалуйста, дождитесь завершения предыдущего запроса.")
            return
        
        # Добавляем пользователя в список обрабатываемых
        self.processing_users.add(user_id)
        
        msg = await self.send_message(chat_id, "🎧 Обрабатываю аудио… конвертирую и распознаю речь…")
        processing_message_id = msg.get("result", {}).get("message_id") if msg and msg.get("ok") else None
        
        try:
            if not self.audio_processor:
                if processing_message_id:
                    await self.edit_message(chat_id, processing_message_id, "❌ Аудио обработка недоступна - нет Groq API ключа")
                else:
                    await self.send_message(chat_id, "❌ Аудио обработка недоступна - нет Groq API ключа")
                return
            
            result = await self.audio_processor.process_audio_from_telegram(file_url, filename_hint)
            if not result.get("success"):
                if processing_message_id:
                    await self.edit_message(chat_id, processing_message_id, f"❌ {result.get('error')}")
                else:
                    await self.send_message(chat_id, f"❌ {result.get('error')}")
                return

            transcript = result["transcript"]
            duration = result.get("duration_sec")

            # Проверяем длину транскрипции
            if len(transcript) < 50:
                if processing_message_id:
                    await self.edit_message(chat_id, processing_message_id, 
                        f"📝 Транскрипция слишком короткая!\n\nРаспознано {len(transcript)} символов. Для качественной суммаризации нужно минимум 50 символов.\n\n📄 Транскрипция:\n{transcript}")
                else:
                    await self.send_message(chat_id, f"📝 Транскрипция слишком короткая!\n\nРаспознано {len(transcript)} символов. Для качественной суммаризации нужно минимум 50 символов.\n\n📄 Транскрипция:\n{transcript}")
                return

            # Обновляем сообщение о прогрессе
            if processing_message_id:
                await self.edit_message(chat_id, processing_message_id, "🎧 Создаю резюме…")

            # Попробуем SmartSummarizer, если он есть, иначе фоллбек
            summary = None
            if hasattr(self, "smart_summarizer") and self.smart_summarizer:
                try:
                    compression_level = await self.get_user_compression_level(user_id)
                    target_ratio = compression_level / 100.0
                    
                    smart_result = await self.smart_summarizer.smart_summarize(
                        transcript, source_type="audio", 
                        source_name=filename_hint, 
                        compression_ratio=target_ratio
                    )
                    
                    if smart_result.get('success'):
                        summary = smart_result.get('summary', '')
                except Exception as e:
                    logger.warning(f"SmartSummarizer не сработал: {e}")

            if not summary and self.groq_client:
                # Улучшенный промпт для структурированного саммари аудио
                prompt = f"""Проанализируй транскрипцию аудио и создай структурированное резюме на том же языке, что и исходный текст.

📋 СТРУКТУРА ОТВЕТА:
• **Тема:** [О чем говорится - 1 предложение]
• **Ключевые моменты:** [3-5 основных пунктов]
• **Решения/Выводы:** [Конкретные решения, если есть]
• **Действия:** [Action items - что нужно сделать, если упоминалось]
• **Важные детали:** [Даты, цифры, имена, если есть]

ТРЕБОВАНИЯ:
- Пиши кратко и по делу
- Сохраняй все конкретные факты (даты, цифры, имена)
- Используй bullet points (•)
- Не добавляй информацию, которой нет в транскрипции
- Если какая-то секция не применима - пропусти её

ТРАНСКРИПЦИЯ:
{transcript}"""

                @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
                def call_groq_api():
                    return self.groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        temperature=0.2,
                        messages=[{"role":"user","content": prompt}]
                    )

                resp = call_groq_api()
                summary = resp.choices[0].message.content.strip()
            elif not summary:
                # Если нет API - простая заглушка
                summary = f"Транскрипция аудио готова ({len(transcript)} символов)"

            header = f"🎙️ Аудио распознано ({duration:.0f} сек).\n\n"
            if processing_message_id:
                await self.edit_message(chat_id, processing_message_id, header + summary)
            else:
                await self.send_message(chat_id, header + summary)
                
            # Сохраняем в базу данных
            try:
                audio_duration = duration or 0.0  # Убедимся, что duration не None
                self.db.save_user_request(user_id, f"audio:{filename_hint}", len(transcript), len(summary), float(audio_duration), 'groq_whisper')
            except (OSError, sqlite3.Error) as save_error:
                logger.error(f"Ошибка сохранения аудио запроса в БД: {save_error}")
            
            logger.info(f"🎵 Успешно обработан аудио {filename_hint} пользователя {user_id}")
                
        except (sqlite3.Error, ValueError) as e:
            logger.exception("Ошибка при обработке аудио")
            error_msg = f"❌ Ошибка при обработке аудио: {e}"
            if processing_message_id:
                await self.edit_message(chat_id, processing_message_id, error_msg)
            else:
                await self.send_message(chat_id, error_msg)
        finally:
            # Удаляем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)

    async def handle_audio_message(self, update: dict):
        """Универсальная обработка всех типов аудио сообщений"""
        
        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]
        
        # Извлекаем дескриптор аудио
        audio_descriptor = extract_audio_descriptor(message)
        
        if not audio_descriptor:
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
        progress_message_id = progress_msg.get("result", {}).get("message_id") if progress_msg and progress_msg.get("ok") else None
        
        try:
            # Проверяем доступность аудио процессора
            if not self.audio_processor:
                error_msg = "❌ Аудио обработка недоступна\n\nНет доступа к Groq API для распознавания речи."
                if progress_message_id:
                    await self.edit_message(chat_id, progress_message_id, error_msg)
                else:
                    await self.send_message(chat_id, error_msg)
                return
            
            # Обновляем прогресс - скачивание
            if progress_message_id and isinstance(progress_message_id, int):
                try:
                    await self.edit_message(
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
                    "audio/ogg": ".ogg", "audio/oga": ".oga", "audio/opus": ".ogg",
                    "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
                    "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
                    "audio/aac": ".aac", "audio/flac": ".flac",
                    "audio/wav": ".wav", "audio/x-wav": ".wav",
                    "video/webm": ".webm", "video/mp4": ".m4a",
                    "application/octet-stream": ".ogg",
                }
                filename_hint += ext_by_mime.get(mime, ".ogg")
            
            # Логируем информацию об аудио перед обработкой
            logger.info(f"Audio: mime={audio_descriptor.get('mime_type')} filename_hint={filename_hint}")
            
            # Обновляем прогресс - конвертация
            if progress_message_id and isinstance(progress_message_id, int):
                try:
                    await self.edit_message(
                        chat_id, 
                        progress_message_id, 
                        f"🎛️ Конвертирую аудио…\n\n{audio_info}"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось обновить прогресс (конвертация): {e}")
            
            # Обрабатываем аудио
            result = await self.audio_processor.process_audio_from_telegram(file_url, filename_hint)
            
            if not result.get("success"):
                error_msg = f"❌ Ошибка обработки аудио\n\n{result.get('error', 'Неизвестная ошибка')}"
                if progress_message_id:
                    await self.edit_message(chat_id, progress_message_id, error_msg)
                else:
                    await self.send_message(chat_id, error_msg)
                return
            
            # Обновляем прогресс - распознавание завершено
            if progress_message_id and isinstance(progress_message_id, int):
                try:
                    await self.edit_message(
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
                error_msg = "❌ Речь не распознана\n\nВозможные причины:\n• Слишком тихая запись\n• Фоновый шум\n• Неподдерживаемый язык\n• Файл без речи"
                if progress_message_id:
                    await self.edit_message(chat_id, progress_message_id, error_msg)
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
                        compression_ratio=target_ratio
                    )
                    
                    if smart_result.get('success'):
                        summary = smart_result.get('summary', '')
                except Exception as e:
                    logger.warning(f"SmartSummarizer не сработал: {e}")
            
            # Фолбэк суммаризация через Groq
            if not summary and self.groq_client:
                try:
                    # Используем существующий метод suммаризации
                    compression_level = await self.get_user_compression_level(user_id)
                    target_ratio = compression_level / 100.0
                    summary = await self.summarize_text(transcript, target_ratio)
                except Exception as e:
                    logger.warning(f"Groq суммаризация не сработала: {e}")
            
            # Если нет саммаризации, показываем транскрипт
            if not summary:
                summary = "Краткое изложение недоступно. Вот полный текст:\n\n" + transcript[:1000] + ("..." if len(transcript) > 1000 else "")
            
            # Формируем финальный ответ
            duration_text = f" ({format_duration(duration)})" if duration else ""
            final_message = f"🎧 {audio_info}{duration_text}\n\n📋 **Саммари:**\n{summary}"
            
            # Ограничиваем длину сообщения
            if len(final_message) > 4000:
                summary_limit = 4000 - len(f"🎧 {audio_info}{duration_text}\n\n📋 **Саммари:**\n") - 50
                summary = summary[:summary_limit] + "..."
                final_message = f"🎧 {audio_info}{duration_text}\n\n📋 **Саммари:**\n{summary}"
            
            # Отправляем результат
            if progress_message_id and isinstance(progress_message_id, int):
                try:
                    await self.edit_message(chat_id, progress_message_id, final_message)
                except Exception as e:
                    logger.warning(f"Не удалось отредактировать сообщение: {e}")
                    await self.send_message(chat_id, final_message)
            else:
                await self.send_message(chat_id, final_message)
            
            # Сохраняем в базу
            try:
                username = message["from"].get("username", "")
                self.db.save_user_request(user_id, username, len(transcript), len(summary) if summary else 0, 0.0, 'audio_processing')
            except (sqlite3.Error, ValueError) as e:
                logger.error(f"Ошибка сохранения в БД: {e}")
        
        except Exception as e:
            logger.error(f"Ошибка обработки аудио для пользователя {user_id}: {e}")
            error_msg = f"❌ Произошла ошибка при обработке аудио\n\n{str(e)[:200]}..."
            
            if progress_message_id:
                await self.edit_message(chat_id, progress_message_id, error_msg)
            else:
                await self.send_message(chat_id, error_msg)
        
        finally:
            # Убираем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)
    
    def _detect_document_type(self, text: str, file_name: str = "", file_extension: str = "", metadata: dict = None) -> str:
        """Определяет тип документа для адаптивной саммаризации"""
        # Книжные форматы имеют приоритет
        if file_extension.lower() in ['.epub', '.fb2']:
            return 'book'

        # Проверяем метаданные из EPUB/FB2
        if metadata and ('author' in metadata or 'title' in metadata):
            # Если есть метаданные автора/названия - скорее всего книга
            return 'book'

        # Для PDF проверяем длину - книги обычно длиннее
        if file_extension.lower() == '.pdf' and len(text) > 50000:
            # Дополнительная проверка на характерные признаки книги
            lower_text = text[:5000].lower()
            book_indicators = ['глава', 'chapter', 'содержание', 'table of contents',
                             'предисловие', 'preface', 'введение', 'introduction',
                             'часть', 'part', 'эпилог', 'epilogue']
            if any(indicator in lower_text for indicator in book_indicators):
                return 'book'

        # Презентации
        if file_extension.lower() == '.pptx':
            return 'presentation'

        # По умолчанию - документ
        return 'document'

    async def summarize_book_content(self, text: str, metadata: dict = None, compression_ratio: float = 0.3) -> str:
        """Специализированная саммаризация для книг с чанкингом"""
        try:
            if not self.groq_client:
                return "❌ Groq API недоступен"

            # Извлекаем метаданные если есть
            book_title = metadata.get('title', 'Книга') if metadata else 'Книга'
            book_author = metadata.get('author', 'Неизвестный автор') if metadata else 'Неизвестный автор'

            original_length = len(text)
            logger.info(f"📚 Начинаю саммаризацию книги: {book_title}, длина: {original_length} символов")

            # Для очень длинных книг применяем чанкинг
            if original_length > 30000:
                logger.info(f"📚 Книга длинная ({original_length} символов), применяю чанк-саммаризацию")

                # Разбиваем на чанки по ~15000 символов
                chunk_size = 15000
                chunks = []
                for i in range(0, len(text), chunk_size):
                    chunk = text[i:i + chunk_size]
                    if len(chunk) > 1000:  # Пропускаем слишком короткие чанки
                        chunks.append(chunk)

                logger.info(f"📚 Разбито на {len(chunks)} чанков")

                # Саммаризируем каждый чанк отдельно
                chunk_summaries = []
                for idx, chunk in enumerate(chunks[:5]):  # Максимум 5 чанков чтобы не превысить лимиты API
                    logger.info(f"📚 Обработка чанка {idx + 1}/{min(len(chunks), 5)}")

                    chunk_prompt = f"""Создай краткое резюме этой части книги "{book_title}" (автор: {book_author}).
Выдели ключевые события, идеи и важную информацию. Ответ на том же языке, что и текст.

Формат (150-200 слов):
• **Ключевые моменты:** [2-3 пункта]
• **Важные детали:** [имена, факты, цифры если есть]

Часть книги:
{chunk}"""

                    @retry_on_failure(max_retries=2, delay=1.0, backoff=2.0)
                    def call_groq_for_chunk():
                        return self.groq_client.chat.completions.create(
                            messages=[{"role": "user", "content": chunk_prompt}],
                            model="llama-3.3-70b-versatile",
                            temperature=0.3,
                            max_tokens=300,
                            top_p=0.9
                        )

                    try:
                        response = call_groq_for_chunk()
                        if response.choices and response.choices[0].message:
                            chunk_summaries.append(response.choices[0].message.content.strip())
                    except Exception as e:
                        logger.error(f"📚 Ошибка обработки чанка {idx + 1}: {e}")
                        continue

                # Объединяем резюме чанков в финальное резюме
                if chunk_summaries:
                    combined_summaries = "\n\n".join([f"**Часть {i+1}:**\n{s}" for i, s in enumerate(chunk_summaries)])

                    final_prompt = f"""На основе резюме отдельных частей книги "{book_title}" (автор: {book_author}), создай единое структурированное резюме всей книги.

Структура резюме (400-600 слов):
📖 **О книге:** [1-2 предложения - главная тема]
📚 **Сюжет/Содержание:** [Основная линия повествования или ключевые идеи - 3-5 пунктов]
👥 **Персонажи/Действующие лица:** [Если применимо - основные персонажи]
💡 **Ключевые идеи и темы:** [Главные мысли автора - 2-4 пункта]
🎯 **Выводы:** [Основное заключение - 1-2 пункта]

Резюме частей книги:
{combined_summaries}"""

                    @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
                    def call_groq_for_final():
                        return self.groq_client.chat.completions.create(
                            messages=[{"role": "user", "content": final_prompt}],
                            model="llama-3.3-70b-versatile",
                            temperature=0.3,
                            max_tokens=700,
                            top_p=0.9
                        )

                    response = call_groq_for_final()
                    if response.choices and response.choices[0].message:
                        return response.choices[0].message.content.strip()

            else:
                # Для книг средней длины - одна саммаризация
                logger.info(f"📚 Книга средней длины, одна саммаризация")
                max_chars = 25000  # Для книг увеличиваем лимит
                if len(text) > max_chars:
                    text = text[:max_chars] + "...\n[Текст обрезан для обработки]"

                book_prompt = f"""Проанализируй книгу и создай структурированное резюме на том же языке, что и текст.

📖 **Информация о книге:**
Название: {book_title}
Автор: {book_author}

📋 **Структура резюме (400-600 слов):**
• **О книге:** [1-2 предложения - главная тема или жанр]
• **Сюжет/Содержание:** [Основная линия повествования или ключевые идеи - 3-5 пунктов]
• **Персонажи:** [Если художественная литература - основные персонажи]
• **Ключевые идеи:** [Главные мысли, темы, концепции - 2-4 пункта]
• **Стиль и особенности:** [Отличительные черты книги]
• **Выводы:** [Основное заключение или мораль]

ВАЖНО:
- Сохраняй ключевые факты, имена, события
- Для нон-фикшн акцентируй идеи и аргументы
- Для художественной литературы - сюжет и персонажей
- Не добавляй спойлеры к концовке, если это художественное произведение

Текст книги:
{text}"""

                @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
                def call_groq_api():
                    return self.groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": book_prompt}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.3,
                        max_tokens=750,
                        top_p=0.9
                    )

                response = call_groq_api()
                if response.choices and response.choices[0].message:
                    return response.choices[0].message.content.strip()

            return "❌ Не удалось получить ответ от модели"

        except Exception as e:
            logger.error(f"📚 Ошибка при саммаризации книги: {e}")
            return f"❌ Ошибка при обработке книги: {str(e)[:100]}"

    async def summarize_file_content(self, text: str, file_name: str = "", file_type: str = "", compression_ratio: float = 0.3) -> str:
        """Создает резюме содержимого файла через Groq API"""
        try:
            if not self.groq_client:
                return "❌ Groq API недоступен"
            
            # Ограничиваем длину текста
            max_chars = 15000  # Увеличиваем лимит для документов
            original_length = len(text)
            
            if len(text) > max_chars:
                text = text[:max_chars] + "...\n[Текст обрезан для обработки]"
            
            # Определяем длину резюме в зависимости от размера документа и уровня сжатия
            target_length = int(original_length * compression_ratio)
            
            if target_length < 200:  # Минимальная длина резюме
                summary_length = "100-200 слов"
                max_tokens = 250
            elif target_length < 800:  # Средняя длина
                summary_length = "200-500 слов"
                max_tokens = 550
            else:  # Длинное резюме
                summary_length = "400-800 слов"
                max_tokens = 850
            
            # Определяем тип документа для лучшего промпта
            file_type_desc = {
                '.pdf': 'PDF документа',
                '.docx': 'Word документа',
                '.doc': 'Word документа',
                '.txt': 'текстового файла'
            }.get(file_type, 'документа')
            
            prompt = f"""Ты - эксперт по анализу документов. Создай подробное структурированное резюме {file_type_desc} на том же языке, что и исходный текст.

📋 **Требования к резюме:**
- Длина: {summary_length} (сжатие {compression_ratio:.0%})
- Структурированный формат с заголовками
- Обязательно извлекай КЛЮЧЕВЫЕ ФАКТЫ: имена, даты, цифры, события, решения
- Если документ на русском - отвечай на русском языке

📝 **Формат резюме:**

**Основное содержание:**
• Ключевые темы и идеи документа (2-3 пункта)

**Ключевые факты:**
• Важные данные: цифры, статистика, даты, имена, места
• Конкретные решения, выводы, рекомендации
• Упоминаемые источники, ссылки, документы (если есть)

**Детали и контекст:**
• Дополнительная важная информация
• Методология или процессы (если применимо)

**Выводы:**
• Основные заключения и их практическое значение

ВАЖНО:
- Сохраняй все точные цифры, даты, имена собственные
- Приоритет - извлечению фактической информации
- Избегай общих фраз, фокусируйся на конкретике

Начни ответ сразу с резюме, без вступлений.

Содержимое документа:
{text}"""

            @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
            def call_groq_api():
                return self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.3,
                    max_tokens=max_tokens,
                    top_p=0.9,
                    stream=False
                )

            response = call_groq_api()
            
            if response.choices and response.choices[0].message:
                summary = response.choices[0].message.content
                if summary:
                    return summary.strip()
            return "❌ Не удалось получить ответ от модели"
            
        except Exception as e:
            logger.error(f"Ошибка при суммаризации файла: {e}")
            return f"❌ Ошибка при обработке: {str(e)[:100]}"
    
    async def handle_update(self, update: dict):
        """Обработка обновлений от Telegram"""
        # Инкрементируем счетчик запросов
        self.metrics['total_requests'] += 1

        try:
            logger.info(f"Полученное обновление: {update}")

            # Обработка callback_query (inline кнопки)
            if "callback_query" in update:
                await self.handle_callback_query(update["callback_query"])
                return

            if "message" in update:
                message = update["message"]
                logger.info(f"Найдено сообщение в обновлении: {message}")
                
                # Проверяем наличие текста в сообщении (обычном или пересланном)
                text = None
                chat_id = message["chat"]["id"]
                user_id = message["from"]["id"]
                
                # Извлекаем текст из сообщения (работает для обычных и пересланных)
                # Используем импортированную функцию из bot.text_utils
                text = extract_text_from_message(message)
                logger.info(f"DEBUG handle_update: Результат extract_text_from_message: '{text}'")
                
                if text:
                    # Определяем тип сообщения для логирования
                    if "forward_from" in message or "forward_from_chat" in message or "forward_origin" in message:
                        logger.info(f"Получено пересланное сообщение от пользователя {user_id}: '{text[:50]}...'")
                    else:
                        logger.info(f"Получено сообщение от пользователя {user_id}: '{text[:50]}...'")

                
                if text:
                    logger.info(f"DEBUG: Текст получен для обработки: '{text}'")
                    if text.startswith("/"):
                        # Обработка команд
                        logger.info(f"DEBUG: Начинаю обработку команды: {text}")
                        if text == "/start":
                            await self.handle_start_command(update)
                        elif text == "/help":
                            await self.handle_help_command(update)
                        elif text == "/stats":
                            await self.handle_stats_command(update)
                        elif text == "/smart":
                            await self.handle_smart_mode_command(update)

                        # Новые понятные команды (приоритет)
                        elif text == "/short":
                            await self.handle_compression_command(update, 15)
                        elif text == "/balanced":
                            await self.handle_compression_command(update, 30)
                        elif text == "/detailed":
                            await self.handle_compression_command(update, 50)

                        # Старые команды (для совместимости)
                        elif text in ["/10"]:
                            await self.handle_compression_command(update, 10)
                        elif text in ["/30"]:
                            await self.handle_compression_command(update, 30)
                        elif text in ["/50"]:
                            await self.handle_compression_command(update, 50)
                        else:
                            # Проверка команд дайджестов
                            if self.digest_enabled:
                                try:
                                    from digest.commands import handle_digest_command
                                    digest_handled = await handle_digest_command(update, self)
                                    if digest_handled:
                                        return
                                except Exception as e:
                                    logger.error(f"Ошибка обработки команды дайджеста: {e}")
                            
                            logger.warning(f"Неизвестная команда: {text}")
                            await self.send_message(
                                chat_id,
                                "❓ Неизвестная команда. Используйте /help для получения справки."
                            )
                    else:
                        # Проверяем текстовые команды уровня сжатия
                        if text.strip() in ["10%", "30%", "50%"]:
                            compression_level = int(text.strip().replace('%', ''))
                            await self.handle_compression_command(update, compression_level)
                        elif user_id in self.user_states:
                            current_step = self.user_states[user_id].get("step")
                            
                            # Обработка выбора уровня сжатия текстом
                            if current_step == "compression_level" and text.strip() in ["10%", "30%", "50%"]:
                                compression_level = text.strip().replace("%", "")
                                self.user_settings[user_id] = {"compression": compression_level, "format": "bullets"}
                                self.user_states[user_id]["step"] = "waiting_text"
                                await self.send_text_request(chat_id, user_id)
                                return
                            
                            # Обработка текста в режиме ожидания
                            elif current_step == "waiting_text":
                                if text.strip().lower() == "ok" and user_id in self.user_messages_buffer and len(self.user_messages_buffer[user_id]) > 0:
                                    # Обработка собранных сообщений
                                    await self.process_custom_summarization(chat_id, user_id)
                                    return
                                else:
                                    await self.handle_custom_summarize_text(update, text)
                                    return

                        # Обработка процентов без предварительной настройки (быстрый режим)
                        if text.strip() in ["10%", "30%", "50%"] and user_id not in self.user_states:
                            compression_level = text.strip().replace("%", "")
                            self.user_states[user_id] = {"step": "waiting_text"}
                            self.user_settings[user_id] = {"compression": compression_level, "format": "bullets"}
                            self.user_messages_buffer[user_id] = []
                            
                            await self.send_text_request(chat_id, user_id)
                            return

                        # Проверяем, находится ли пользователь в режиме настраиваемой суммаризации
                        if user_id in self.user_states and self.user_states[user_id].get("step") == "waiting_text":
                            await self.handle_custom_summarize_text(update, text)
                        else:
                            # Проверяем, есть ли YouTube URL в сообщении
                            youtube_urls = self.youtube_processor.extract_youtube_urls(text)
                            if youtube_urls:
                                # Обработка YouTube видео
                                await self.handle_youtube_message(update, youtube_urls)
                                return
                            
                            # Проверяем, есть ли обычные URL в сообщении
                            urls = self.extract_urls_from_message(text)
                            if urls:
                                # Обработка сообщений с URL
                                await self.handle_url_message(update, urls)
                                return
                            
                            # Прямая обработка текста без дублирования в handle_text_message
                            logger.info(f"Обработка текстового сообщения от пользователя {user_id}")
                            
                            # Проверка лимита запросов
                            if not self.check_user_rate_limit(user_id):
                                await self.send_message(chat_id, "⏰ Превышен лимит запросов!\n\nПожалуйста, подождите минуту перед отправкой нового текста. Лимит: 10 запросов в минуту.")
                                return
                            
                            # Проверка на повторную обработку
                            if user_id in self.processing_users:
                                await self.send_message(chat_id, "⚠️ Обработка в процессе!\n\nПожалуйста, дождитесь завершения предыдущего запроса.")
                                return
                            
                            # Проверка минимальной длины текста (с учетом emoji)
                            # Считаем только значимые символы, исключая пробелы
                            significant_chars = ''.join(c for c in text if not c.isspace())
                            if len(significant_chars) < 20:  # Более мягкое ограничение с учетом emoji
                                await self.send_message(chat_id, f"📝 Текст слишком короткий!\n\nДля качественной суммаризации нужно минимум 20 значимых символов.\nВаш текст: {len(significant_chars)} символов.")
                                return
                            
                            # Добавляем пользователя в список обрабатываемых
                            self.processing_users.add(user_id)
                            
                            try:
                                username = update["message"]["from"].get("username", "")
                                
                                # Отправляем сообщение о начале обработки
                                processing_response = await self.send_message(chat_id, "🤖 Обрабатываю ваш текст...\n\nЭто может занять несколько секунд.")
                                processing_message_id = processing_response.get("result", {}).get("message_id") if processing_response else None
                                
                                start_time = time.time()
                                
                                # Проверяем, включена ли умная суммаризация
                                smart_mode = self.user_settings.get(user_id, {}).get("smart_mode", True)
                                
                                if smart_mode and self.smart_summarizer:
                                    # Умная суммаризация
                                    user_compression_level = await self.get_user_compression_level(user_id)
                                    target_ratio = user_compression_level / 100.0
                                    
                                    smart_result = await self.smart_summarizer.smart_summarize(
                                        text, source_type="text", 
                                        source_name="текстовое сообщение", 
                                        compression_ratio=target_ratio
                                    )
                                    processing_time = time.time() - start_time
                                    summary = self.smart_summarizer.format_smart_response(
                                        smart_result, "текстовое сообщение", len(text), processing_time
                                    )
                                else:
                                    # Обычная суммаризация
                                    user_compression_level = await self.get_user_compression_level(user_id)
                                    target_ratio = user_compression_level / 100.0
                                    summary = await self.summarize_text(text, target_ratio=target_ratio)
                                    processing_time = time.time() - start_time
                                
                                if summary and not summary.startswith("❌"):
                                    # Сохраняем запрос в базу данных
                                    try:
                                        self.db.save_user_request(user_id, username, len(text), len(summary), processing_time, 'groq')
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
                                    
                                    await self.send_message(chat_id, response_text)
                                    
                                    logger.info(f"Успешно обработан текст пользователя {user_id}, сжатие: {compression_ratio:.1%}")
                                    
                                else:
                                    # Удаляем сообщение о обработке
                                    if processing_message_id:
                                        await self.delete_message(chat_id, processing_message_id)
                                    
                                    await self.send_message(chat_id, "❌ Ошибка при обработке текста!\n\nПопробуйте позже или обратитесь к администратору.")
                                    
                                    logger.error(f"Не удалось обработать текст пользователя {user_id}")
                            
                            except (sqlite3.Error, ValueError) as e:
                                logger.error(f"Ошибка при обработке текста пользователя {user_id}: {str(e)}")
                                await self.send_message(chat_id, f"❌ Произошла ошибка!\n\nПожалуйста, попробуйте позже.")
                            
                            finally:
                                # Удаляем пользователя из списка обрабатываемых
                                self.processing_users.discard(user_id)
                elif "audio" in message or "voice" in message or "video_note" in message:
                    # Обработка аудио файлов, голосовых сообщений и видео кружочков
                    if ("forward_from" in message) or ("forward_from_chat" in message) or ("forward_origin" in message):
                        logger.info("Пересланное аудио/voice/video_note без текста — направляю в handle_audio_message")
                    await self.handle_audio_message(update)
                    return
                elif "document" in message:
                    # Проверяем, является ли документ аудио файлом
                    doc = message["document"]
                    is_audio = is_audio_document(doc)
                    logger.info(f"DEBUG: document '{doc.get('file_name')}' mime='{doc.get('mime_type')}' -> is_audio={is_audio}")
                    
                    if is_audio:
                        if ("forward_from" in message) or ("forward_from_chat" in message) or ("forward_origin" in message):
                            logger.info("Пересланный аудио документ без текста — направляю в handle_audio_message")
                        await self.handle_audio_message(update)
                    else:
                        # Обработка документов (PDF, DOCX, DOC, TXT, PPTX; сканы через OCR)
                        await self.handle_document_message(update)
                    return
                else:
                    # Проверяем, есть ли другой медиа контент
                    if any(key in message for key in ['photo', 'video', 'sticker', 'animation', 'video_note']):
                        # Медиа сообщение без текста - просто игнорируем без ошибки
                        logger.info(f"Получено медиа сообщение без текста от пользователя {user_id} - игнорируем")
                        return
                    else:
                        # Только если сообщение совсем пустое - тогда показываем ошибку
                        logger.warning(f"DEBUG: Сообщение не содержит ни текста, ни медиа контента: {message}")
                        await self.send_message(chat_id, "❌ Сообщение не содержит текста.\n\nПожалуйста, отправьте текстовое сообщение для суммаризации.")

            # Обработка channel_post и edited_channel_post для дайджестов
            elif self.digest_enabled and ("channel_post" in update or "edited_channel_post" in update):
                try:
                    from digest.sources import handle_channel_update
                    await handle_channel_update(update, self)
                except Exception as e:
                    logger.error(f"Ошибка обработки канального поста: {e}")
            else:
                logger.warning(f"Неизвестный тип обновления: {update}")
                        
        except Exception as e:
            logger.error(f"Ошибка обработки обновления: {e}")
            import traceback
            logger.error(f"Детали ошибки: {traceback.format_exc()}")
    
    async def get_updates(self, offset = None, timeout: int = 30):
        """Получение обновлений от Telegram"""
        url = f"{self.base_url}/getUpdates"
        params = {
            "timeout": timeout,
            "allowed_updates": ["message", "channel_post", "edited_channel_post"]
        }
        
        if offset:
            params["offset"] = offset
        
        logger.info(f"🔄 GET_UPDATES: Запрос обновлений с offset={offset}, timeout={timeout}")
        logger.info(f"🔄 GET_UPDATES: Allowed updates: {params['allowed_updates']}")
        
        try:
            async with self.session.get(url, params=params) as response:
                    result = await response.json()
                    
                    if result and result.get("ok"):
                        update_list = result.get("result", [])
                        logger.info(f"🔄 GET_UPDATES: Получено {len(update_list)} обновлений")
                        for update in update_list:
                            if "message" in update:
                                msg = update["message"]
                                logger.info(f"📨 GET_UPDATES: Получено сообщение от {msg.get('from', {}).get('id', 'unknown')}: {msg.get('text', msg.get('caption', 'no_text'))[:50]}")
                    
                    return result
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"❌ GET_UPDATES ERROR: Ошибка получения обновлений: {e}")
            import traceback
            logger.error(f"🔍 GET_UPDATES TRACEBACK: {traceback.format_exc()}")
            return None
    
    async def clear_webhook(self):
        """Очистка webhook для устранения конфликтов 409"""
        if self.session is None:
            logger.error("Session is None in clear_webhook - creating new session")
            await self._create_session()

        try:
            url = f"{self.base_url}/deleteWebhook"
            params = {"drop_pending_updates": "true"}

            async with self.session.post(url, params=params) as response:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info("Webhook успешно удален")
                        return True
                    else:
                        logger.warning(f"Не удалось удалить webhook: {result}")
                        return False
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка при удалении webhook: {e}")
            return False

    async def clear_custom_keyboards(self, chat_id):
        """Очистка пользовательских клавиатур"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": "🔄 Обновляю интерфейс...",
                "reply_markup": json.dumps({"remove_keyboard": True})
            }
            
            async with self.session.post(url, data=data) as response:
                    result = await response.json()
                    if result.get("ok"):
                        # Удаляем сообщение об обновлении после короткой задержки
                        message_id = result["result"]["message_id"]
                        await asyncio.sleep(1)
                        await self.delete_message(chat_id, message_id)
                        logger.info(f"Пользовательские клавиатуры очищены для чата {chat_id}")
                    
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка при очистке клавиатур: {e}")

    async def setup_bot_commands(self):
        """Настройка команд бота"""
        try:
            # Очищаем все существующие команды
            await self.clear_all_commands()
            
            # Устанавливаем только нужные команды
            commands = [
                {
                    "command": "help",
                    "description": "📖 Помощь по использованию"
                },
                {
                    "command": "stats", 
                    "description": "📊 Статистика использования"
                },
                {
                    "command": "smart",
                    "description": "🧠 Умная суммаризация с анализом"
                },
                {
                    "command": "10",
                    "description": "🔥 Максимальное сжатие (10%)"
                },
                {
                    "command": "30",
                    "description": "📝 Сбалансированное сжатие (30%)"
                },
                {
                    "command": "50",
                    "description": "📄 Умеренное сжатие (50%)"
                }
            ]
            
            url = f"{self.base_url}/setMyCommands"
            data = {"commands": json.dumps(commands)}
            
            async with self.session.post(url, data=data) as response:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info("Команды бота установлены: /help, /stats, /10, /30, /50")
                    else:
                        logger.warning(f"Не удалось установить команды: {result}")
                        
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка при установке команд бота: {e}")
    
    async def clear_all_commands(self):
        """Очистка всех команд бота"""
        try:
            url = f"{self.base_url}/deleteMyCommands"
            
            async with self.session.post(url) as response:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info("Все команды бота удалены")
                    else:
                        logger.warning(f"Не удалось удалить команды: {result}")
                        
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка при удалении команд: {e}")

    async def run(self):
        """Запуск бота"""
        logger.info("Запуск Simple Telegram Bot")

        # Создаем HTTP сессию
        await self._create_session()

        # Очищаем webhook для предотвращения конфликтов 409
        await self.clear_webhook()
        await asyncio.sleep(2)  # Даем время на очистку

        # Устанавливаем команды бота
        await self.setup_bot_commands()

        # Проверяем подключение к Telegram API
        try:
            url = f"{self.base_url}/getMe"
            async with self.session.get(url) as response:
                me_response = await response.json()
                if me_response and me_response.get("ok"):
                    bot_info = me_response.get("result", {})
                    logger.info(f"Подключение к Telegram API успешно. Бот: {bot_info.get('first_name', 'Unknown')}")
                else:
                    logger.error("Не удалось подключиться к Telegram API")
                    await self._close_session()
                    return
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка проверки подключения: {e}")
            await self._close_session()
            return
        
        offset = None

        logger.info("Бот запущен и готов к работе!")

        try:
            while True:
                try:
                    updates = await self.get_updates(offset=offset, timeout=30)

                    if updates and updates.get("ok"):
                        update_list = updates.get("result", [])
                        if update_list:
                            logger.info(f"Получено {len(update_list)} обновлений")

                        for update in update_list:
                            logger.info(f"Обработка обновления: {update.get('update_id')}")
                            await self.handle_update(update)
                            offset = update["update_id"] + 1
                            logger.info(f"Обновлен offset: {offset}")
                    else:
                        if updates:
                            error_code = updates.get("error_code")
                            if error_code == 409:
                                # Конфликт с другим экземпляром бота
                                logger.warning("Обнаружен конфликт 409 - другой экземпляр бота активен")
                                logger.info("Очистка webhook и повторная попытка...")
                                await self.clear_webhook()
                                await asyncio.sleep(5)  # Увеличенная пауза для разрешения конфликта
                                continue
                            else:
                                logger.error(f"Ошибка получения обновлений: {updates}")

                    await asyncio.sleep(0.1)

                except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Ошибка в основном цикле: {e}")
                    await asyncio.sleep(5)
                except Exception as e:
                    # Непредвиденные ошибки - логируем с трейсбеком
                    logger.exception(f"Критическая ошибка в основном цикле: {e}")
                    await asyncio.sleep(10)
        finally:
            # Graceful shutdown - закрываем все ресурсы
            logger.info("Остановка бота...")
            await self._shutdown()
    
    async def handle_url_message(self, update: dict, urls: list):
        """Обработчик сообщений с URL для суммаризации веб-страниц"""
        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]
        
        logger.info(f"🔗 URL обработка: получено {len(urls)} ссылок от пользователя {user_id}")
        
        # Проверка лимита запросов
        if not self.check_user_rate_limit(user_id):
            await self.send_message(chat_id, "⏰ Превышен лимит запросов!\n\nПожалуйста, подождите минуту перед отправкой новых ссылок. Лимит: 10 запросов в минуту.")
            return
        
        # Проверка на повторную обработку
        if user_id in self.processing_users:
            await self.send_message(chat_id, "⚠️ Обработка в процессе!\n\nПожалуйста, дождитесь завершения предыдущего запроса.")
            return
        
        # Ограничиваем количество URL за раз
        urls_to_process = urls[:3]  # Максимум 3 URL за раз
        
        # Отправляем сообщение о начале обработки
        processing_response = await self.send_message(
            chat_id, 
            f"🔄 Обрабатываю {len(urls_to_process)} веб-страниц{'у' if len(urls_to_process) == 1 else 'ы'}...\n\nЭто может занять несколько секунд."
        )
        processing_message_id = processing_response.get("result", {}).get("message_id") if processing_response else None
        
        # Добавляем пользователя в список обрабатываемых
        self.processing_users.add(user_id)
        
        try:
            username = message["from"].get("username", "")
            successful_summaries = 0
            
            for i, url in enumerate(urls_to_process):
                try:
                    logger.info(f"🔗 Обработка URL {i+1}/{len(urls_to_process)}: {url}")
                    
                    # Проверяем, разрешен ли домен
                    if not self.is_url_allowed(url):
                        await self.send_message(
                            chat_id,
                            f"❌ Домен не поддерживается: {urlparse(url).netloc}\n\nСоциальные сети и некоторые другие сайты не поддерживаются."
                        )
                        continue
                    
                    # Извлекаем контент с помощью нового экстрактора
                    start_time = time.time()
                    try:
                        from content_extraction import extract_url
                        extracted_page = await extract_url(url)
                        content_result = {
                            'success': True,
                            'content': extracted_page.text,
                            'title': extracted_page.title or "Без заголовка",
                            'links': extracted_page.links[:5],  # Первые 5 ссылок
                            'word_count': extracted_page.word_count,
                            'char_count': extracted_page.char_count
                        }
                    except Exception as e:
                        logger.warning(f"Новый экстрактор не сработал для {url}: {e}")
                        # Fallback на старый метод
                        content_result = self.extract_webpage_content(url)
                    
                    if not content_result['success']:
                        await self.send_message(
                            chat_id,
                            f"❌ Ошибка при загрузке {url[:50]}...:\n{content_result['error']}"
                        )
                        continue
                    
                    # Проверяем минимальную длину контента
                    if len(content_result['content']) < 100:
                        await self.send_message(
                            chat_id,
                            f"❌ Слишком мало текста на странице {url[:50]}...\n\nСтраница содержит меньше 100 символов текста."
                        )
                        continue
                    
                    # Получаем уровень сжатия пользователя
                    user_compression_level = await self.get_user_compression_level(user_id)
                    target_ratio = user_compression_level / 100.0

                    # Суммаризируем с помощью AI с адаптивным промптом
                    summary = await self.summarize_web_content(
                        content_result['content'],
                        title=content_result.get('title', ''),
                        url=url,
                        target_ratio=target_ratio
                    )
                    
                    if summary and not summary.startswith("❌"):
                        # Успешная AI суммаризация
                        processing_time = time.time() - start_time
                        
                        # Сохраняем запрос в базу данных
                        try:
                            self.db.save_user_request(user_id, username, len(content_result['content']), len(summary), processing_time, 'groq_web')
                        except (OSError, sqlite3.Error) as save_error:
                            logger.error(f"Ошибка сохранения запроса в БД: {save_error}")
                        
                        # Вычисляем статистику
                        compression_ratio = len(summary) / len(content_result['content'])
                        
                        # Формируем красивый ответ
                        # Добавляем блок ссылок, если они есть
                        links_section = ""
                        if 'links' in content_result and content_result['links']:
                            links_list = []
                            for link in content_result['links'][:5]:  # Первые 5 ссылок
                                link_text = link.get('text', '').strip()[:50]
                                if link_text and len(link_text) > 5:
                                    links_list.append(f"• {link_text}")
                            
                            if links_list:
                                links_section = f"""

🔗 Ссылки из статьи:
{chr(10).join(links_list)}"""

                        response_text = (
                            f"\U0001F4C4 Резюме статьи (Уровень сжатия: {user_compression_level}%)\n\n"
                            f"\U0001F517 Источник: {content_result['title'][:100]}\n"
                            f"\U0001F4CE Ссылка: {url}\n\n"
                            f"\U0001F4DD Основные моменты:\n"
                            f"{summary}{links_section}\n\n"
                            f"\U0001F4CA Статистика:\n"
                            f"• Исходный текст: {len(content_result['content']):,} символов\n"
                            f"• Саммари: {len(summary):,} символов\n"
                            f"• Сжатие: {compression_ratio:.1%}\n"
                            f"• Время обработки: {processing_time:.1f}с"
                        )

                        await self.send_message(chat_id, response_text)
                        successful_summaries += 1
                        
                        logger.info(f"🔗 Успешно обработан URL {i+1}/{len(urls_to_process)}: {url}")
                        
                    else:
                        # Fallback на простую суммаризацию
                        simple_summary = self.simple_text_summary(content_result['content'])
                        processing_time = time.time() - start_time
                        
                        response_text = (
                            f"\U0001F4C4 Резюме статьи (упрощенная обработка)\n\n"
                            f"\U0001F517 Источник: {content_result['title'][:100]}\n"
                            f"\U0001F4CE Ссылка: {url}\n\n"
                            f"\U0001F4DD Основные моменты:\n"
                            f"{simple_summary}\n\n"
                            f"\u26A0\uFE0F Замечание: Использована упрощенная суммаризация\n"
                            f"\U0001F4CA Исходный текст: {len(content_result['content']):,} символов"
                        )

                        await self.send_message(chat_id, response_text)
                        successful_summaries += 1
                        
                        logger.info(f"🔗 Обработан URL с fallback {i+1}/{len(urls_to_process)}: {url}")
                    
                except (sqlite3.Error, ValueError) as e:
                    logger.error(f"Ошибка при обработке URL {url}: {str(e)}")
                    await self.send_message(
                        chat_id,
                        f"❌ Произошла ошибка при обработке {url[:50]}...: {str(e)}"
                    )
            
            # Удаляем сообщение о процессе обработки
            if processing_message_id:
                await self.delete_message(chat_id, processing_message_id)
            
            # Отправляем итоговое сообщение
            if successful_summaries > 0:
                if len(urls) > 3:
                    await self.send_message(
                        chat_id,
                        f"✅ Обработано {successful_summaries} из {len(urls_to_process)} ссылок\n\n💡 Максимум 3 ссылки за раз. Оставшиеся {len(urls) - 3} ссылок отправьте отдельно."
                    )
                else:
                    await self.send_message(
                        chat_id,
                        f"✅ Обработано {successful_summaries} из {len(urls_to_process)} ссылок"
                    )
            else:
                await self.send_message(
                    chat_id,
                    "❌ Не удалось обработать ни одну ссылку\n\nПопробуйте другие сайты или обратитесь к администратору."
                )
        
        except Exception as e:
            logger.error(f"Критическая ошибка при обработке URL: {str(e)}")
            # Удаляем сообщение о процессе обработки
            if processing_message_id:
                await self.delete_message(chat_id, processing_message_id)
            
            await self.send_message(
                chat_id,
                f"❌ Произошла критическая ошибка!\n\nПожалуйста, попробуйте позже или обратитесь к администратору."
            )
        
        finally:
            # Удаляем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)

    async def delete_message(self, chat_id: int, message_id: int):
        """Удаление сообщения"""
        try:
            url = f"{self.base_url}/deleteMessage"
            data = {
                "chat_id": chat_id,
                "message_id": message_id
            }
            
            async with self.session.post(url, json=data) as response:
                    result = await response.json()
                    return result.get("ok", False)
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
            return False
    


    async def handle_direct_compression_command(self, update: dict, compression_level: str):
        """Обработка прямых команд сжатия /10, /30, /50"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        logger.info(f"🚀 DIRECT COMPRESSION: Команда /{compression_level} от пользователя {user_id}")
        
        # Инициализируем состояние пользователя
        self.user_states[user_id] = {"step": "format_selection"}
        self.user_settings[user_id] = {"compression": compression_level if compression_level else 30}
        self.user_messages_buffer[user_id] = []
        
        # Устанавливаем состояние ожидания текста сразу с настройками по умолчанию
        self.user_states[user_id]["step"] = "waiting_text"
        self.user_settings[user_id]["format"] = "bullets"  # Всегда маркированный список
        
        await self.send_text_request(chat_id, user_id)

    async def handle_youtube_message(self, update: dict, youtube_urls: list):
        """Обработчик сообщений с YouTube URL для суммаризации видео"""
        
        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]
        
        logger.info(f"🎥 YouTube обработка: получено {len(youtube_urls)} ссылок от пользователя {user_id}")
        
        # Проверка лимита запросов
        if not self.check_user_rate_limit(user_id):
            await self.send_message(chat_id, "⏰ Превышен лимит запросов!\n\nПожалуйста, подождите минуту перед отправкой новых ссылок. Лимит: 10 запросов в минуту.")
            return
        
        # Проверка на повторную обработку
        if user_id in self.processing_users:
            await self.send_message(chat_id, "⚠️ Обработка в процессе!\n\nПожалуйста, дождитесь завершения предыдущего запроса.")
            return
        
        # Ограничиваем количество видео (максимум 1)
        youtube_url_info = youtube_urls[0]
        url = youtube_url_info['url']
        
        if len(youtube_urls) > 1:
            await self.send_message(
                chat_id,
                "⚠️ Обрабатываю только первое видео из списка.\n\nПожалуйста, отправляйте YouTube видео по одному."
            )
        
        # Отправляем сообщение о начале обработки
        processing_response = await self.send_message(
            chat_id, 
            "🎥 Начинаю обработку YouTube видео...\n\n⏳ Извлекаю субтитры и описание..."
        )
        processing_message_id = processing_response.get("result", {}).get("message_id") if processing_response else None
        
        # Добавляем пользователя в список обрабатываемых
        self.processing_users.add(user_id)
        
        try:
            username = message["from"].get("username", "")
            start_time = time.time()
            
            # Этап 1: Проверка видео
            await self.edit_message(
                chat_id, processing_message_id,
                "🔍 Проверяю доступность и параметры видео..."
            )
            
            validation = self.youtube_processor.validate_youtube_url(url)
            if not validation['valid']:
                await self.edit_message(
                    chat_id, processing_message_id,
                    f"❌ {validation['error']}"
                )
                return
            
            video_title = validation['title']
            video_duration = validation['duration']
            video_uploader = validation['uploader']
            
            # Этап 2: Извлечение контента
            await self.edit_message(
                chat_id, processing_message_id,
                f"📝 Извлекаю субтитры и описание...\n📹 {video_title[:60]}..."
            )
            
            content_result = self.youtube_processor.extract_video_info_and_subtitles(url)
            if not content_result['success']:
                await self.edit_message(
                    chat_id, processing_message_id,
                    f"❌ {content_result['error']}\n\nПопробуйте другое видео с субтитрами."
                )
                return
            
            # Этап 3: Создание резюме
            await self.edit_message(
                chat_id, processing_message_id,
                "🤖 Создаю структурированное резюме через Groq AI..."
            )
            
            # Получаем уровень сжатия пользователя
            user_compression_level = await self.get_user_compression_level(user_id)
            
            summary_result = self.youtube_processor.summarize_youtube_content(
                content_result['text'],
                video_title,
                video_duration
            )
            
            if not summary_result['success']:
                # Fallback на простое резюме
                summary_result = self.youtube_processor.create_fallback_summary(
                    content_result['text'],
                    video_title
                )
            
            processing_time = time.time() - start_time
            
            if summary_result['success']:
                summary_text = summary_result['summary']
                
                # Сохраняем запрос в базу данных
                try:
                    self.db.save_user_request(
                        user_id, username, 
                        len(content_result['text']), 
                        len(summary_text), 
                        processing_time, 
                        'groq_youtube'
                    )
                except (OSError, sqlite3.Error) as save_error:
                    logger.error(f"Ошибка сохранения YouTube запроса в БД: {save_error}")
                
                # Формируем финальный ответ
                duration_str = format_duration(video_duration)
                content_length = len(content_result['text'])
                
                # Определяем источники контента
                sources = []
                if content_result.get('has_subtitles'):
                    sources.append("субтитры")
                if content_result.get('has_description'):
                    sources.append("описание")
                sources_text = " + ".join(sources) if sources else "доступный контент"
                
                response = f"""🎥 **Резюме YouTube видео** (Уровень сжатия: {user_compression_level}%)

📺 **Название:** {video_title}
👤 **Автор:** {video_uploader}
⏱️ **Длительность:** {duration_str}
🔗 **Ссылка:** {url}

📋 **Резюме содержания:**
{summary_text}

📊 **Статистика обработки:**
• Источник текста: {sources_text}
• Контент: {content_length:,} символов
• Резюме: {len(summary_text):,} символов
• Время обработки: {processing_time:.1f}с
• Метод: yt-dlp + Groq (Llama 3.3)"""

                # Отправляем результат
                await self.edit_message(
                    chat_id, processing_message_id,
                    response
                )
                
                logger.info(f"✅ Успешно обработано YouTube видео от пользователя {user_id}: {video_title[:50]}...")
                
            else:
                await self.edit_message(
                    chat_id, processing_message_id,
                    "❌ Не удалось создать резюме видео\n\nПопробуйте другое видео или обратитесь к администратору."
                )
                
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Критическая ошибка при обработке YouTube видео: {str(e)}")
            await self.edit_message(
                chat_id, processing_message_id,
                f"❌ Произошла критическая ошибка!\n\nПожалуйста, попробуйте позже или обратитесь к администратору."
            )
        
        finally:
            # Удаляем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)

    async def edit_message(self, chat_id: int, message_id: int, text: str, reply_markup: Optional[dict] = None):
        """Редактирование существующего сообщения"""
        if not message_id:
            return

        url = f"{self.base_url}/editMessageText"

        # Сначала пробуем с Markdown форматированием
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:4096],
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }

        if reply_markup:
            data["reply_markup"] = reply_markup
        
        try:
            async with self.session.post(url, json=data) as response:
                    result = await response.json()
                    
                    # Если ошибка парсинга - пробуем без форматирования
                    if not result.get("ok") and "can't parse entities" in result.get("description", ""):
                        logger.info("Повторная отправка без Markdown форматирования")
                        data_plain = {
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "text": text[:4096],
                            "disable_web_page_preview": True
                        }
                        if reply_markup:
                            data_plain["reply_markup"] = reply_markup
                        async with self.session.post(url, json=data_plain) as response_plain:
                            result = await response_plain.json()
                    
                    if not result.get("ok"):
                        logger.warning(f"Не удалось отредактировать сообщение: {result}")
                    return result
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
            return None

async def main():
    """Главная функция"""
    try:
        bot = SimpleTelegramBot()
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())