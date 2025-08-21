#!/usr/bin/env python3
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
from typing import Dict, Set, Optional
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
# from readability import parse  # Убрано из-за проблем с установкой
from youtube_processor import YouTubeProcessor
from file_processor import FileProcessor
from audio_processor import AudioProcessor
from smart_summarizer import SmartSummarizer
from ui_keyboards import keyboards, callback_parser
from user_settings import UserSettingsManager

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# HTML константа для приветственного сообщения
WELCOME_MESSAGE_HTML = """👋 Привет! Я превращаю длинные тексты, ссылки, видео и <b>даже голосовые/аудио</b> в короткие, понятные выжимки. Экономлю твоё время — оставляю только главное.

🧠 <b>Что умею:</b>
• 📝 Тексты и пересланные сообщения — выделю суть и ключевые пункты
• 🌐 Статьи по ссылке — аккуратно вытащу главное с веб-страницы
• ▶️ YouTube (до 2 часов) — сделаю саммари по субтитрам
• 📎 Документы: PDF, DOCX, DOC, TXT (до 20 MB) — верну структурированное резюме
• 🗣️ <b>Аудио и голосовые</b> — расшифрую и выдам краткое саммари (удобно для встреч и заметок)

🌍 <b>Автоматическое определение языка:</b> бот определяет русский/английский текст и создает саммари на том же языке

🎛 <b>Гибкая длина саммари:</b> используй <code>/10</code>, <code>/30</code>, <code>/50</code> — выбери уровень сжатия 10%/30%/50%

🚀 <b>Как начать:</b>
• Пришли текст — получи выжимку
• Отправь ссылку — вернусь с резюме статьи
• Скинь YouTube-ссылку — получишь краткое содержание
• Загрузишь документ — верну структурированное саммари
• Отправь голосовое/аудио — пришлю транскрипт + краткое саммари

📋 <b>Команды:</b>
/help — подробная справка
/stats — твоя статистика

🔥 Powered by <b>Llama 3.3 70B</b> — одна из сильнейших моделей для русского языка!"""

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
            except Exception as e:
                logger.error(f"Ошибка инициализации Groq API: {e}")
        
        # Базовый URL для Telegram API
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        
        # Защита от спама
        self.user_requests: Dict[int, list] = {}
        self.processing_users: Set[int] = set()
        
        # Состояния пользователей для настраиваемой суммаризации
        self.user_states: Dict[int, dict] = {}
        self.user_settings: Dict[int, dict] = {}
        
        # Временное хранение сообщений для объединения
        self.user_messages_buffer: Dict[int, list] = {}
        
        # Инициализация базы данных
        from database import DatabaseManager
        database_url = os.getenv('DATABASE_URL', 'sqlite:///bot_database.db')
        self.db = DatabaseManager(database_url)
        self.db.init_database()
        
        # Инициализация менеджера настроек пользователей
        self.user_settings_manager = UserSettingsManager(self.db)
        
        # Хранение контекста последних сообщений для smart кнопки
        self.user_last_context: Dict[int, dict] = {}
        
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
        
        logger.info("Simple Telegram Bot инициализирован")
    
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
    
    def get_user_compression_level(self, user_id: int) -> int:
        """Получение уровня сжатия пользователя из базы данных"""
        try:
            settings = self.db.get_user_settings(user_id)
            return settings.get('compression_level', 30)  # По умолчанию 30%
        except Exception as e:
            logger.error(f"Ошибка получения настроек пользователя {user_id}: {e}")
            return 30

    def update_user_compression_level(self, user_id: int, compression_level: int, username: str = ""):
        """Обновление уровня сжатия пользователя в базе данных"""
        try:
            logger.info(f"SimpleTelegramBot: начинаю обновление уровня сжатия для пользователя {user_id}: {compression_level}%")
            self.db.update_compression_level(user_id, compression_level, username)
            logger.info(f"SimpleTelegramBot: уровень сжатия для пользователя {user_id} успешно обновлен: {compression_level}%")
        except Exception as e:
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
            data["reply_markup"] = reply_markup
        
        logger.info(f"📤 SEND_MESSAGE: Отправка сообщения в чат {chat_id}")
        
        try:
            async with aiohttp.ClientSession() as session:
                # Используем json=data когда есть reply_markup, иначе data=data
                if reply_markup:
                    async with session.post(url, json=data) as response:
                        result = await response.json()
                else:
                    async with session.post(url, data=data) as response:
                        result = await response.json()
                        
                if result.get("ok"):
                    logger.info(f"Сообщение успешно отправлено в чат {chat_id}")
                else:
                    logger.error(f"Ошибка отправки сообщения в чат {chat_id}: {result}")
                return result
        except Exception as e:
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
                    
            except Exception as norm_error:
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
            
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                max_tokens=2000,
                top_p=0.9,
                stream=False
            )
            
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
    
    async def handle_start_command(self, update: dict):
        """Обработка команды /start"""
        chat_id = update["message"]["chat"]["id"]
        user = update["message"]["from"]
        user_id = user.get("id")
        username = user.get("username", "")
        
        logger.info(f"Обработка команды /start от пользователя {user_id} в чате {chat_id}")
        
        # Получаем настройки пользователя
        user_settings = self.user_settings_manager.get_user_settings(user_id)
        lang = user_settings.get('language', 'ru').lower()
        
        # Отмечаем что пользователь завершил первое взаимодействие
        if user_settings.get('first_interaction', True):
            self.user_settings_manager.mark_first_interaction_complete(user_id)
        
        # Создаем reply-клавиатуру с кнопкой меню
        reply_keyboard = keyboards.build_reply_keyboard(lang)
        
        # Создаем inline-клавиатуру с главным меню
        inline_keyboard = keyboards.build_main_menu(user_settings)
        
        # Отправляем приветственное сообщение с обеими клавиатурами
        await self.send_message(chat_id, WELCOME_MESSAGE_HTML, parse_mode="HTML", reply_markup=reply_keyboard)
        
        # Отправляем главное меню как отдельное сообщение с inline-кнопками
        menu_text = keyboards.get_text('menu_title', lang)
        await self.send_message(chat_id, menu_text, reply_markup=inline_keyboard)
    
    async def handle_help_command(self, update: dict):
        """Обработка команды /help"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        # Получаем настройки пользователя для языка
        user_settings = self.user_settings_manager.get_user_settings(user_id)
        lang = user_settings.get('language', 'ru').lower()
        
        help_text = """📖 Как использовать бота:

🔥 **БЫСТРАЯ СУММАРИЗАЦИЯ:**
• Отправьте текст → получите сжатие 30%
• Перешлите сообщение → автоматическая обработка

🔗 **СУММАРИЗАЦИЯ ВЕБ-СТРАНИЦ:**
• Отправьте ссылку на статью → получите краткое резюме
• Поддержка: Хабр, РБК, новостных сайтов, блогов
• Максимум 3 ссылки за раз

🎥 **СУММАРИЗАЦИЯ YOUTUBE ВИДЕО:**
• Отправьте ссылку на YouTube → резюме видео
• Извлечение субтитров и описания видео
• Структурированное резюме с ключевыми моментами
• ⏱️ Длительность видео: до 2 часов (120 минут)

📄 **СУММАРИЗАЦИЯ ДОКУМЕНТОВ:**
• Прикрепите файл → получите структурированное резюме
• Поддерживаемые форматы: PDF, DOCX, DOC, TXT
• Максимальный размер файла: 20MB (лимит Telegram)
• Автоматическое извлечение текста из документов

🎵 **СУММАРИЗАЦИЯ АУДИО:**
• Отправьте аудио файл или голосовое сообщение → резюме речи
• Поддержка: MP3, WAV, M4A, OGG, FLAC, AAC, OPUS
• Автоматическая транскрипция речи в текст
• Максимум 50MB, до 1 часа длительности
• Работает на русском и английском языках

⚡ **КОМАНДЫ СУММАРИЗАЦИИ:**
• /10 → максимальное сжатие (10%)
• /30 → сбалансированное сжатие (30%)  
• /50 → умеренное сжатие (50%)

🧠 **УМНАЯ СУММАРИЗАЦИЯ:**
• /smart → включить/отключить интеллектуальный анализ
• Автоматическое определение типа контента
• Извлечение ключевых инсайтов и структурирование

💬 **ТЕКСТОВЫЕ КОМАНДЫ:**
• Отправьте: 10%, 30% или 50%
• Потом отправьте текст для обработки

📊 **ДРУГИЕ КОМАНДЫ:**
• /stats → ваша статистика
• /help → эта справка

💡 **Особенности:**
• Минимум 20 символов для текста
• Поддержка emoji и спецсимволов
• Автосохранение ваших настроек сжатия
• До 10 запросов в минуту
• Работает на Llama 3.3 70B

📋 **НОВЫЙ ИНТЕРФЕЙС:** Используйте кнопки внизу экрана для быстрого доступа ко всем функциям!"""
        
        # Добавляем кнопку "Назад в меню"
        back_keyboard = keyboards.build_back_menu(lang)
        await self.send_message(chat_id, help_text, reply_markup=back_keyboard)
    
    async def handle_smart_mode_command(self, update: dict):
        """Обработка команды /smart - переключение в режим умной суммаризации"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        username = update["message"]["from"].get("username", "")
        
        # Переключаем режим умной суммаризации через менеджер настроек
        new_mode = self.user_settings_manager.toggle_smart_mode(user_id, username)
        
        if new_mode:
            mode_text = """🧠 **Умная суммаризация включена!**

Теперь бот создает концентрированные резюме с ключевыми инсайтами:

🎯 **Что получаете:**
• Только самые важные выводы и инсайты
• Автоматическое определение типа контента
• Извлечение критически важной информации

📊 **Управление детальностью:**
• /10 → 2 ключевых инсайта (максимальное сжатие)
• /30 → 3 ключевых инсайта (сбалансированно)
• /50 → 4 ключевых инсайта (подробно)

Отправьте любой текст, документ, аудио или ссылку для умной обработки!

_Чтобы вернуться к обычной суммаризации, снова нажмите /smart_"""
        else:
            mode_text = """📝 **Обычная суммаризация восстановлена**

Теперь бот использует стандартный режим суммаризации с настраиваемыми уровнями сжатия (10%, 30%, 50%).

Чтобы снова включить умную суммаризацию, нажмите /smart"""

        # Получаем язык пользователя и добавляем кнопку возврата в меню
        user_settings = self.user_settings_manager.get_user_settings(user_id)
        lang = user_settings.get('language', 'ru').lower()
        back_keyboard = keyboards.build_back_menu(lang)
        
        await self.send_message(chat_id, mode_text, reply_markup=back_keyboard)
        logger.info(f"Пользователь {user_id} {'включил' if new_mode else 'отключил'} умную суммаризацию")
    
    async def handle_stats_command(self, update: dict):
        """Обработка команды /stats"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        try:
            user_stats = self.db.get_user_stats(user_id)
        except Exception as e:
            logger.error(f"Ошибка получения статистики пользователя {user_id}: {e}")
            user_stats = {
                'total_requests': 0,
                'total_chars': 0,
                'total_summary_chars': 0,
                'avg_compression': 0,
                'first_request': None
            }
        
        stats_text = f"""📊 Ваша статистика:

• Обработано текстов: {user_stats['total_requests']}
• Символов обработано: {user_stats['total_chars']:,}
• Символов в саммари: {user_stats['total_summary_chars']:,}
• Среднее сжатие: {user_stats['avg_compression']:.1%}
• Первый запрос: {user_stats['first_request'] or 'Нет данных'}

📈 Используйте бота для обработки длинных текстов и статей!"""
        
        # Получаем настройки пользователя для языка
        user_settings = self.user_settings_manager.get_user_settings(user_id)
        lang = user_settings.get('language', 'ru').lower()
        
        # Добавляем кнопку "Назад в меню"
        back_keyboard = keyboards.build_back_menu(lang)
        await self.send_message(chat_id, stats_text, reply_markup=back_keyboard)

    async def handle_compression_command(self, update: dict, compression_level: int):
        """Обработка команд уровня сжатия (/10, /30, /50 или 10%, 30%, 50%)"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        username = update["message"]["from"].get("username", "")
        
        try:
            # Сохраняем новый уровень сжатия через менеджер настроек
            success = self.user_settings_manager.set_compression_level(user_id, compression_level, username)
            
            if success:
                # Получаем обновленные настройки и показываем меню
                user_settings = self.user_settings_manager.get_user_settings(user_id)
                lang = user_settings.get('language', 'ru').lower()
                
                compression_text = f"{compression_level}%"
                confirmation_text = f"""✅ Уровень сжатия обновлен: {compression_text}

Теперь все ваши тексты будут суммаризированы с уровнем сжатия {compression_text}."""
                
                # Показываем обновленное меню с отмеченным активным уровнем
                menu_keyboard = keyboards.build_main_menu(user_settings)
                await self.send_message(chat_id, confirmation_text, reply_markup=menu_keyboard)
                
                logger.info(f"Пользователь {user_id} изменил уровень сжатия на {compression_level}%")
            else:
                await self.send_message(chat_id, "❌ Произошла ошибка при изменении настроек. Попробуйте еще раз.")
            
        except Exception as e:
            logger.error(f"Ошибка обработки команды сжатия {compression_level}% для пользователя {user_id}: {e}")
            await self.send_message(chat_id, "❌ Произошла ошибка при изменении настроек. Попробуйте еще раз.")
    
    async def handle_callback_query(self, update: dict):
        """Обработка callback-запросов от inline-кнопок"""
        callback_query = update.get("callback_query")
        if not callback_query:
            return
        
        # Отвечаем на callback для убирания индикатора загрузки
        await self.answer_callback_query(callback_query["id"])
        
        user_id = callback_query["from"]["id"]
        username = callback_query["from"].get("username", "")
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]
        callback_data = callback_query["data"]
        
        logger.info(f"Callback от пользователя {user_id}: {callback_data}")
        
        # Парсим callback_data
        parsed = callback_parser.parse(callback_data)
        action = parsed.get('action')
        
        try:
            if action == 'smart':
                await self.handle_callback_smart(chat_id, user_id, username, message_id)
            
            elif action == 'cmp':  # compression
                level = int(parsed.get('sub', '30'))
                await self.handle_callback_compression(chat_id, user_id, username, message_id, level)
            
            elif action == 'lang':  # language
                sub_action = parsed.get('sub', '')
                if sub_action == 'toggle':
                    await self.handle_callback_language_toggle(chat_id, user_id, username, message_id)
            
            elif action == 'stats':
                await self.handle_callback_stats(chat_id, user_id, message_id)
            
            elif action == 'help':
                await self.handle_callback_help(chat_id, user_id, message_id)
            
            elif action == 'menu':
                await self.handle_callback_menu(chat_id, user_id, message_id)
            
            else:
                logger.warning(f"Неизвестный callback action: {action}")
                
        except Exception as e:
            logger.error(f"Ошибка обработки callback {callback_data} от пользователя {user_id}: {e}")
            await self.edit_message(
                chat_id, message_id, 
                "❌ Произошла ошибка при обработке запроса. Попробуйте еще раз."
            )
    
    async def answer_callback_query(self, callback_query_id: str, text: str = None, show_alert: bool = False):
        """Отвечает на callback_query"""
        try:
            url = f"{self.base_url}/answerCallbackQuery"
            data = {"callback_query_id": callback_query_id}
            
            if text:
                data["text"] = text
            if show_alert:
                data["show_alert"] = show_alert
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    return await response.json()
                    
        except Exception as e:
            logger.error(f"Ошибка ответа на callback query: {e}")
            return None
    
    async def handle_callback_smart(self, chat_id: int, user_id: int, username: str, message_id: int):
        """Обработка callback для smart суммаризации"""
        # Проверяем есть ли контекст для суммаризации
        if user_id not in self.user_last_context:
            user_settings = self.user_settings_manager.get_user_settings(user_id)
            lang = user_settings.get('language', 'ru').lower()
            
            no_context_text = {
                'ru': "🧠 Умная суммаризация\n\nПришлите текст, документ, ссылку или аудио, затем нажмите эту кнопку для интеллектуальной обработки.",
                'en': "🧠 Smart Summary\n\nSend text, document, link or audio, then click this button for intelligent processing."
            }.get(lang, "🧠 Пришлите контент для умной суммаризации.")
            
            menu_keyboard = keyboards.build_main_menu(user_settings)
            await self.edit_message(chat_id, message_id, no_context_text, reply_markup=menu_keyboard)
            return
        
        # Если есть контекст, запускаем умную суммаризацию
        context = self.user_last_context[user_id]
        
        processing_text = "🧠 Запускаю умную суммаризацию..."
        await self.edit_message(chat_id, message_id, processing_text)
        
        # Здесь будет логика smart суммаризации
        # Пока заглушка
        await asyncio.sleep(1)
        
        result_text = "🧠 Умная суммаризация выполнена!\n\n[Результат будет здесь]"
        user_settings = self.user_settings_manager.get_user_settings(user_id)
        menu_keyboard = keyboards.build_main_menu(user_settings)
        
        await self.edit_message(chat_id, message_id, result_text, reply_markup=menu_keyboard)
    
    async def handle_callback_compression(self, chat_id: int, user_id: int, username: str, message_id: int, level: int):
        """Обработка callback для изменения уровня сжатия"""
        success = self.user_settings_manager.set_compression_level(user_id, level, username)
        
        if success:
            user_settings = self.user_settings_manager.get_user_settings(user_id)
            lang = user_settings.get('language', 'ru').lower()
            
            # Создаем обновленное меню с отмеченным новым уровнем
            menu_keyboard = keyboards.build_main_menu(user_settings)
            
            confirmation_text = {
                'ru': f"✅ Уровень сжатия: {level}%\n\n📋 Главное меню",
                'en': f"✅ Compression level: {level}%\n\n📋 Main menu"
            }.get(lang, f"✅ Уровень сжатия: {level}%")
            
            await self.edit_message(chat_id, message_id, confirmation_text, reply_markup=menu_keyboard)
        else:
            await self.edit_message(chat_id, message_id, "❌ Ошибка изменения настроек")
    
    async def handle_callback_language_toggle(self, chat_id: int, user_id: int, username: str, message_id: int):
        """Обработка callback для переключения языка"""
        new_lang = self.user_settings_manager.toggle_language(user_id, username)
        
        user_settings = self.user_settings_manager.get_user_settings(user_id)
        menu_keyboard = keyboards.build_main_menu(user_settings)
        
        confirmation_text = {
            'ru': "✅ Язык изменен на русский\n\n📋 Главное меню",
            'en': "✅ Language changed to English\n\n📋 Main menu"
        }.get(new_lang, "✅ Язык изменен")
        
        await self.edit_message(chat_id, message_id, confirmation_text, reply_markup=menu_keyboard)
    
    async def handle_callback_stats(self, chat_id: int, user_id: int, message_id: int):
        """Обработка callback для показа статистики"""
        try:
            user_stats = self.db.get_user_stats(user_id)
        except Exception as e:
            logger.error(f"Ошибка получения статистики пользователя {user_id}: {e}")
            user_stats = {
                'total_requests': 0,
                'total_chars': 0, 
                'total_summary_chars': 0,
                'avg_compression': 0,
                'first_request': None
            }
        
        user_settings = self.user_settings_manager.get_user_settings(user_id)
        lang = user_settings.get('language', 'ru').lower()
        
        stats_text = f"""📊 {'Статистика' if lang == 'ru' else 'Statistics'}:

• {'Обработано текстов' if lang == 'ru' else 'Processed texts'}: {user_stats['total_requests']}
• {'Символов обработано' if lang == 'ru' else 'Characters processed'}: {user_stats['total_chars']:,}
• {'Символов в саммари' if lang == 'ru' else 'Summary characters'}: {user_stats['total_summary_chars']:,}
• {'Среднее сжатие' if lang == 'ru' else 'Average compression'}: {user_stats['avg_compression']:.1%}
• {'Первый запрос' if lang == 'ru' else 'First request'}: {user_stats['first_request'] or ('Нет данных' if lang == 'ru' else 'No data')}"""
        
        back_keyboard = keyboards.build_back_menu(lang)
        await self.edit_message(chat_id, message_id, stats_text, reply_markup=back_keyboard)
    
    async def handle_callback_help(self, chat_id: int, user_id: int, message_id: int):
        """Обработка callback для показа помощи"""
        user_settings = self.user_settings_manager.get_user_settings(user_id)
        lang = user_settings.get('language', 'ru').lower()
        
        if lang == 'en':
            help_text = """📖 How to use the bot:

🔥 **QUICK SUMMARIZATION:**
• Send text → get 30% compression
• Forward a message → automatic processing

🔗 **WEB PAGE SUMMARIZATION:**
• Send article link → get brief summary
• Support: news sites, blogs, articles

🎥 **YOUTUBE VIDEO SUMMARIZATION:**  
• Send YouTube link → video summary
• Extract subtitles and description
• Up to 2 hours duration

📄 **DOCUMENT SUMMARIZATION:**
• Attach file → get structured summary
• Formats: PDF, DOCX, DOC, TXT, PPTX
• Max size: 20MB

🎵 **AUDIO SUMMARIZATION:**
• Send audio/voice → speech summary
• Formats: MP3, WAV, M4A, OGG, etc
• Max: 50MB, up to 1 hour

⚡ **COMPRESSION LEVELS:**
• 10% → maximum compression
• 30% → balanced compression  
• 50% → moderate compression

📋 **USE BUTTONS:** Use interface buttons for quick access!"""
        else:
            help_text = """📖 Как использовать бота:

🔥 **БЫСТРАЯ СУММАРИЗАЦИЯ:**
• Отправьте текст → получите сжатие 30%
• Перешлите сообщение → автоматическая обработка

🔗 **СУММАРИЗАЦИЯ ВЕБ-СТРАНИЦ:**
• Отправьте ссылку на статью → получите краткое резюме
• Поддержка: новостные сайты, блоги, статьи

🎥 **СУММАРИЗАЦИЯ YOUTUBE:**
• Отправьте ссылку на YouTube → резюме видео
• Извлечение субтитров и описания
• До 2 часов длительности

📄 **СУММАРИЗАЦИЯ ДОКУМЕНТОВ:**
• Прикрепите файл → получите резюме
• Форматы: PDF, DOCX, DOC, TXT, PPTX
• Максимум: 20MB

🎵 **СУММАРИЗАЦИЯ АУДИО:**
• Отправьте аудио/голосовое → резюме речи
• Форматы: MP3, WAV, M4A, OGG и др.
• Максимум: 50MB, до 1 часа

⚡ **УРОВНИ СЖАТИЯ:**
• 10% → максимальное сжатие
• 30% → сбалансированное сжатие
• 50% → умеренное сжатие

📋 **ИСПОЛЬЗУЙТЕ КНОПКИ:** Кнопки интерфейса для быстрого доступа!"""
        
        back_keyboard = keyboards.build_back_menu(lang)
        await self.edit_message(chat_id, message_id, help_text, reply_markup=back_keyboard)
    
    async def handle_callback_menu(self, chat_id: int, user_id: int, message_id: int):
        """Обработка callback для возврата в главное меню"""
        user_settings = self.user_settings_manager.get_user_settings(user_id)
        lang = user_settings.get('language', 'ru').lower()
        
        menu_text = keyboards.get_text('menu_title', lang)
        menu_keyboard = keyboards.build_main_menu(user_settings)
        
        await self.edit_message(chat_id, message_id, menu_text, reply_markup=menu_keyboard)
    
    async def handle_menu_button(self, update: dict):
        """Обработка нажатия кнопки 'Меню' из reply-клавиатуры"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        # Получаем настройки пользователя
        user_settings = self.user_settings_manager.get_user_settings(user_id)
        lang = user_settings.get('language', 'ru').lower()
        
        # Создаем и отправляем главное меню
        menu_text = keyboards.get_text('menu_title', lang)
        menu_keyboard = keyboards.build_main_menu(user_settings)
        
        await self.send_message(chat_id, menu_text, reply_markup=menu_keyboard)
    

    

    

    
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
                self.db.save_user_request(user_id, "", total_chars, len(summary), 0.0, 'groq')
            except Exception as save_error:
                logger.error(f"Ошибка сохранения запроса в БД: {save_error}")
            
            # Очищаем состояние пользователя
            if user_id in self.user_states:
                del self.user_states[user_id]
            if user_id in self.user_settings:
                del self.user_settings[user_id]
            if user_id in self.user_messages_buffer:
                del self.user_messages_buffer[user_id]
                
        except Exception as e:
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
                response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                max_tokens=2000,
                top_p=0.9,
                stream=False
            )
            
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
            # Функция для извлечения и нормализации текста из сообщения
            def extract_text_from_message(msg):
                text = None
                if "text" in msg:
                    text = msg["text"]
                elif "caption" in msg:
                    text = msg["caption"]
                
                logger.info(f"DEBUG handle_text_message: Исходный текст: '{text}'")
                
                # Нормализация текста для обработки сообщений с отступами
                if text:
                    try:
                        # Убираем лишние пробелы и отступы
                        import re
                        # Удаляем избыточные пробелы в начале и конце строк
                        text = '\n'.join(line.strip() for line in text.split('\n'))
                        # Заменяем множественные пробелы на одиночные
                        text = re.sub(r' +', ' ', text)
                        # Заменяем множественные переносы строк на двойные
                        text = re.sub(r'\n{3,}', '\n\n', text)
                        # Убираем пробелы в начале и конце всего текста
                        text = text.strip()
                        
                        # Проверяем, что после нормализации остался смысловой текст
                        # НЕ фильтруем команды (начинающиеся с /)
                        clean_text = text.replace(' ', '').replace('\n', '').replace('\t', '')
                        if text.startswith('/'):
                            logger.info(f"DEBUG: Команда обнаружена и пропущена через фильтр в handle_text_message: '{text}'")
                        elif len(clean_text) < 10:
                            logger.warning(f"Текст после нормализации слишком короткий: '{text[:100]}'")
                            return None
                            
                        logger.info(f"Текст нормализован: было {len(msg.get('text', msg.get('caption', '')))}, стало {len(text)} символов")
                        return text
                    except Exception as e:
                        logger.error(f"Ошибка при нормализации текста: {e}")
                        # В случае ошибки возвращаем исходный текст
                        return text.strip() if text else None
                
                return None
            
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
            user_compression_level = self.get_user_compression_level(user_id)
            target_ratio = user_compression_level / 100.0
            
            # Выполняем суммаризацию с пользовательскими настройками
            summary = await self.summarize_text(text, target_ratio=target_ratio)
            
            processing_time = time.time() - start_time
            
            if summary and not summary.startswith("❌"):
                # Сохраняем запрос в базу данных
                try:
                    self.db.save_user_request(user_id, username, len(text), len(summary), processing_time, 'groq')
                except Exception as save_error:
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
        
        except Exception as e:
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
                    {"file_path": file_path}, file_name, file_size
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
                compression_ratio = self.get_user_compression_level(user_id)
                
                # Суммаризируем извлеченный текст
                summary = await self.summarize_file_content(extracted_text, file_name, download_result["file_extension"], compression_ratio)
                
                if summary:
                    # Определяем иконку и заголовок по типу файла
                    if extension == '.pptx':
                        icon = "📊"
                        doc_type = "презентации"
                    elif extension in ('.png', '.jpg', '.jpeg'):
                        icon = "🖼️"
                        doc_type = "изображения"
                    else:
                        icon = "📄"
                        doc_type = "документа"
                    
                    # Формируем дополнительную информацию
                    extra_info = ""
                    if extraction_meta.get("ocr_pages"):
                        extra_info = f"\n• OCR страницы: {', '.join(map(str, extraction_meta['ocr_pages']))}"
                    elif extraction_meta.get("total_slides"):
                        extra_info = f"\n• Слайды обработаны: {extraction_meta['slides_with_content']}/{extraction_meta['total_slides']}"
                    
                    # Формируем итоговый ответ
                    response_text = f"""{icon} **Резюме {doc_type}: {file_name}**

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
                    except Exception as save_error:
                        logger.error(f"Ошибка сохранения запроса в БД: {save_error}")
                    
                    logger.info(f"Успешно обработан документ {file_name} пользователя {user_id}")
                    
                else:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, "❌ Ошибка при создании резюме документа!\n\nПопробуйте позже или обратитесь к администратору.")
                    
            except Exception as e:
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
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    return await response.json()
        except Exception as e:
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
                    compression_level = self.get_user_compression_level(user_id)
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
                # Фоллбек через LLM Groq — короткое саммари по пунктам
                prompt = (
                    "Суммируй содержание стенограммы голосового сообщения кратко, по пунктам (5–8 пунктов). "
                    "Сохраняй только факты, действия, решения, даты и цифры.\n\n"
                    f"СТЕНОГРАММА:\n{transcript}"
                )
                resp = self.groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    temperature=0.2,
                    messages=[{"role":"user","content": prompt}]
                )
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
            except Exception as save_error:
                logger.error(f"Ошибка сохранения аудио запроса в БД: {save_error}")
            
            logger.info(f"🎵 Успешно обработан аудио {filename_hint} пользователя {user_id}")
                
        except Exception as e:
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
        from utils.tg_audio import extract_audio_descriptor, get_audio_info_text, format_duration
        
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
            filename_hint = audio_descriptor.get("file_name", "audio")
            
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
                    compression_level = self.get_user_compression_level(user_id)
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
                    compression_level = self.get_user_compression_level(user_id)
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
            except Exception as e:
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
    
    async def edit_message(self, chat_id: int, message_id: int, text: str, reply_markup: Optional[dict] = None, parse_mode: Optional[str] = None):
        """Редактирует существующее сообщение"""
        try:
            url = f"{self.base_url}/editMessageText"
            data = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": parse_mode or "Markdown"
            }
            
            if reply_markup:
                data["reply_markup"] = reply_markup
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    return await response.json()
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
            return None
    
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
            
            prompt = f"""Ты - эксперт по анализу документов. Создай подробное резюме {file_type_desc} на том же языке, что и исходный текст.

Требования к резюме:
- Длина: {summary_length} (сжатие {compression_ratio:.0%})
- Структурированный формат с заголовками
- Сохрани все ключевые моменты и важную информацию
- Если документ на русском - отвечай на русском языке

Формат резюме:
📝 **Основное содержание:**
• Ключевые темы и идеи (2-3 пункта)

🔍 **Детали:**
• Важные факты и данные (3-5 пунктов)

💡 **Выводы:**
• Основные заключения (1-2 пункта)

Начни ответ сразу с резюме, без вступлений.

Содержимое документа:
{text}"""
            
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                max_tokens=max_tokens,
                top_p=0.9,
                stream=False
            )
            
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
        try:
            logger.info(f"Полученное обновление: {update}")
            
            if "callback_query" in update:
                # Обработка callback-запросов от inline-кнопок
                await self.handle_callback_query(update)
            elif "message" in update:
                message = update["message"]
                logger.info(f"Найдено сообщение в обновлении: {message}")
                
                # Проверяем наличие текста в сообщении (обычном или пересланном)
                text = None
                chat_id = message["chat"]["id"]
                user_id = message["from"]["id"]
                
                # Функция для извлечения и нормализации текста из сообщения
                def extract_text_from_message_handle_update(msg):
                    text = None
                    if "text" in msg:
                        text = msg["text"]
                    elif "caption" in msg:
                        text = msg["caption"]
                    
                    logger.info(f"DEBUG handle_update extract: Исходный текст: '{text}'")
                    
                    # Для команд - НЕ нормализуем, возвращаем как есть
                    if text and text.startswith('/'):
                        logger.info(f"DEBUG handle_update extract: Команда обнаружена - возвращаем как есть: '{text}'")
                        return text.strip()
                    
                    # Нормализация текста для обработки сообщений с отступами
                    if text:
                        try:
                            # Убираем лишние пробелы и отступы
                            import re
                            # Удаляем избыточные пробелы в начале и конце строк
                            text = '\n'.join(line.strip() for line in text.split('\n'))
                            # Заменяем множественные пробелы на одиночные
                            text = re.sub(r' +', ' ', text)
                            # Заменяем множественные переносы строк на двойные
                            text = re.sub(r'\n{3,}', '\n\n', text)
                            # Убираем пробелы в начале и конце всего текста
                            text = text.strip()
                            
                            # Проверяем длину для обычных текстов (не команд)
                            # Более мягкая проверка длины - считаем только символы, исключая пробелы
                            clean_text = ''.join(c for c in text if not c.isspace())
                            if len(clean_text) < 5:  # Уменьшили минимум для emoji
                                logger.warning(f"Текст после нормализации слишком короткий: '{text[:100]}'")
                                return None
                                
                            logger.info(f"Текст нормализован: было {len(msg.get('text', msg.get('caption', '')))}, стало {len(text)} символов")
                            return text
                        except Exception as e:
                            logger.error(f"Ошибка при нормализации текста: {e}")
                            # В случае ошибки возвращаем исходный текст
                            return text.strip() if text else None
                    
                    return None
                
                # Извлекаем текст из сообщения (работает для обычных и пересланных)
                text = extract_text_from_message_handle_update(message)
                logger.info(f"DEBUG handle_update: Результат extract_text_from_message: '{text}'")
                
                # Проверяем кнопку "Меню"
                if text and text in ['📋 Меню', '📋 Menu']:
                    await self.handle_menu_button(update)
                    return
                
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

                        elif text in ["/10"]:
                            await self.handle_compression_command(update, 10)
                        elif text in ["/30"]:
                            await self.handle_compression_command(update, 30)
                        elif text in ["/50"]:
                            await self.handle_compression_command(update, 50)
                        else:
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
                                smart_mode = self.user_settings.get(user_id, {}).get("smart_mode", False)
                                
                                if smart_mode and self.smart_summarizer:
                                    # Умная суммаризация
                                    user_compression_level = self.get_user_compression_level(user_id)
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
                                    user_compression_level = self.get_user_compression_level(user_id)
                                    target_ratio = user_compression_level / 100.0
                                    summary = await self.summarize_text(text, target_ratio=target_ratio)
                                    processing_time = time.time() - start_time
                                
                                if summary and not summary.startswith("❌"):
                                    # Сохраняем запрос в базу данных
                                    try:
                                        self.db.save_user_request(user_id, username, len(text), len(summary), processing_time, 'groq')
                                    except Exception as save_error:
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
                            
                            except Exception as e:
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
                    from utils.tg_audio import is_audio_document
                    
                    doc = message["document"]
                    
                    if is_audio_document(doc):
                        if ("forward_from" in message) or ("forward_from_chat" in message) or ("forward_origin" in message):
                            logger.info("Пересланный аудио документ без текста — направляю в handle_audio_message")
                        await self.handle_audio_message(update)
                    else:
                        # Обработка документов (PDF, DOCX, DOC, TXT)
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
            "allowed_updates": ["message", "callback_query"]
        }
        
        if offset:
            params["offset"] = offset
        
        logger.info(f"🔄 GET_UPDATES: Запрос обновлений с offset={offset}, timeout={timeout}")
        logger.info(f"🔄 GET_UPDATES: Allowed updates: {params['allowed_updates']}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    result = await response.json()
                    
                    if result and result.get("ok"):
                        update_list = result.get("result", [])
                        logger.info(f"🔄 GET_UPDATES: Получено {len(update_list)} обновлений")
                        for update in update_list:
                            if "message" in update:
                                msg = update["message"]
                                logger.info(f"📨 GET_UPDATES: Получено сообщение от {msg.get('from', {}).get('id', 'unknown')}: {msg.get('text', msg.get('caption', 'no_text'))[:50]}")
                    
                    return result
        except Exception as e:
            logger.error(f"❌ GET_UPDATES ERROR: Ошибка получения обновлений: {e}")
            import traceback
            logger.error(f"🔍 GET_UPDATES TRACEBACK: {traceback.format_exc()}")
            return None
    
    async def clear_webhook(self):
        """Очистка webhook для устранения конфликтов 409"""
        try:
            url = f"{self.base_url}/deleteWebhook"
            params = {"drop_pending_updates": "true"}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params) as response:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info("Webhook успешно удален")
                        return True
                    else:
                        logger.warning(f"Не удалось удалить webhook: {result}")
                        return False
        except Exception as e:
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
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    result = await response.json()
                    if result.get("ok"):
                        # Удаляем сообщение об обновлении после короткой задержки
                        message_id = result["result"]["message_id"]
                        await asyncio.sleep(1)
                        await self.delete_message(chat_id, message_id)
                        logger.info(f"Пользовательские клавиатуры очищены для чата {chat_id}")
                    
        except Exception as e:
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
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info("Команды бота установлены: /help, /stats, /10, /30, /50")
                    else:
                        logger.warning(f"Не удалось установить команды: {result}")
                        
        except Exception as e:
            logger.error(f"Ошибка при установке команд бота: {e}")
    
    async def clear_all_commands(self):
        """Очистка всех команд бота"""
        try:
            url = f"{self.base_url}/deleteMyCommands"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url) as response:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info("Все команды бота удалены")
                    else:
                        logger.warning(f"Не удалось удалить команды: {result}")
                        
        except Exception as e:
            logger.error(f"Ошибка при удалении команд: {e}")

    async def run(self):
        """Запуск бота"""
        logger.info("Запуск Simple Telegram Bot")
        
        # Очищаем webhook для предотвращения конфликтов 409
        await self.clear_webhook()
        await asyncio.sleep(2)  # Даем время на очистку
        
        # Устанавливаем команды бота
        await self.setup_bot_commands()
        
        # Проверяем подключение к Telegram API
        try:
            url = f"{self.base_url}/getMe"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    me_response = await response.json()
                    if me_response and me_response.get("ok"):
                        bot_info = me_response.get("result", {})
                        logger.info(f"Подключение к Telegram API успешно. Бот: {bot_info.get('first_name', 'Unknown')}")
                    else:
                        logger.error("Не удалось подключиться к Telegram API")
                        return
        except Exception as e:
            logger.error(f"Ошибка проверки подключения: {e}")
            return
        
        offset = None
        
        logger.info("Бот запущен и готов к работе!")
        
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
                
            except Exception as e:
                logger.error(f"Ошибка в основном цикле: {e}")
                await asyncio.sleep(5)
    
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
                    user_compression_level = self.get_user_compression_level(user_id)
                    target_ratio = user_compression_level / 100.0
                    
                    # Суммаризируем с помощью AI
                    summary = await self.summarize_text(content_result['content'], target_ratio=target_ratio)
                    
                    if summary and not summary.startswith("❌"):
                        # Успешная AI суммаризация
                        processing_time = time.time() - start_time
                        
                        # Сохраняем запрос в базу данных
                        try:
                            self.db.save_user_request(user_id, username, len(content_result['content']), len(summary), processing_time, 'groq_web')
                        except Exception as save_error:
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

                        response_text = f"""📄 Резюме статьи (Уровень сжатия: {user_compression_level}%)

🔗 Источник: {content_result['title'][:100]}
📎 Ссылка: {url}

📝 Основные моменты:
{summary}{links_section}

📊 Статистика:
• Исходный текст: {len(content_result['content']):,} символов
• Саммари: {len(summary):,} символов  
• Сжатие: {compression_ratio:.1%}
• Время обработки: {processing_time:.1f}с"""

                        await self.send_message(chat_id, response_text)
                        successful_summaries += 1
                        
                        logger.info(f"🔗 Успешно обработан URL {i+1}/{len(urls_to_process)}: {url}")
                        
                    else:
                        # Fallback на простую суммаризацию
                        simple_summary = self.simple_text_summary(content_result['content'])
                        processing_time = time.time() - start_time
                        
                        response_text = f"""📄 Резюме статьи (упрощенная обработка)

🔗 Источник: {content_result['title'][:100]}
📎 Ссылка: {url}

📝 Основные моменты:
{simple_summary}

⚠️ Замечание: Использована упрощенная суммаризация
📊 Исходный текст: {len(content_result['content']):,} символов"""

                        await self.send_message(chat_id, response_text)
                        successful_summaries += 1
                        
                        logger.info(f"🔗 Обработан URL с fallback {i+1}/{len(urls_to_process)}: {url}")
                    
                except Exception as e:
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
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    return result.get("ok", False)
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
            return False
    


    async def handle_direct_compression_command(self, update: dict, compression_level: str):
        """Обработка прямых команд сжатия /10, /30, /50"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        logger.info(f"🚀 DIRECT COMPRESSION: Команда /{compression_level} от пользователя {user_id}")
        
        # Инициализируем состояние пользователя
        self.user_states[user_id] = {"step": "format_selection"}
        self.user_settings[user_id] = {"compression": compression_level}
        self.user_messages_buffer[user_id] = []
        
        # Устанавливаем состояние ожидания текста сразу с настройками по умолчанию
        self.user_states[user_id]["step"] = "waiting_text"
        self.user_settings[user_id]["format"] = "bullets"  # Всегда маркированный список
        
        await self.send_text_request(chat_id, user_id)

    async def handle_youtube_message(self, update: dict, youtube_urls: list):
        """Обработчик сообщений с YouTube URL для суммаризации видео"""
        from utils.tg_audio import format_duration
        
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
            user_compression_level = self.get_user_compression_level(user_id)
            
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
                except Exception as save_error:
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
                
        except Exception as e:
            logger.error(f"Критическая ошибка при обработке YouTube видео: {str(e)}")
            await self.edit_message(
                chat_id, processing_message_id,
                f"❌ Произошла критическая ошибка!\n\nПожалуйста, попробуйте позже или обратитесь к администратору."
            )
        
        finally:
            # Удаляем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)

    async def edit_message(self, chat_id: int, message_id: int, text: str):
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
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
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
                        async with session.post(url, json=data_plain) as response_plain:
                            result = await response_plain.json()
                    
                    if not result.get("ok"):
                        logger.warning(f"Не удалось отредактировать сообщение: {result}")
                    return result
        except Exception as e:
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