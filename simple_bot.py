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
        
        # Инициализация YouTube процессора
        self.youtube_processor = YouTubeProcessor(groq_client=self.groq_client)
        logger.info("YouTube процессор инициализирован")
        
        # Инициализация файлового процессора
        self.file_processor = FileProcessor()
        logger.info("Файловый процессор инициализирован")
        
        # Инициализация аудио процессора
        self.audio_processor = AudioProcessor()
        logger.info("Аудио процессор инициализирован")
        
        # Инициализация умного суммаризатора
        self.smart_summarizer = SmartSummarizer(groq_client=self.groq_client)
        logger.info("Умный суммаризатор инициализирован")
        
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
            # Заголовки для имитации браузера
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Загрузка страницы
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            # Проверка размера контента (максимум 5MB)
            if len(response.content) > 5 * 1024 * 1024:
                raise Exception("Файл слишком большой для обработки")
            
            # Очистка от HTML тегов напрямую
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Удаление ненужных элементов
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                element.decompose()
            
            # Извлечение текста
            text = soup.get_text()
            
            # Очистка текста
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            # Получение заголовка страницы
            title_tag = soup.find('title')
            title = title_tag.get_text().strip() if title_tag else "Без заголовка"
            
            return {
                'title': title,
                'content': text,
                'url': url,
                'success': True
            }
            
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Время ожидания истекло'}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'Не удается подключиться к сайту'}
        except requests.exceptions.HTTPError as e:
            return {'success': False, 'error': f'Ошибка HTTP: {e.response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': f'Ошибка при обработке: {str(e)}'}
    
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
            data["reply_markup"] = reply_markup  # Убираем json.dumps()
        
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
        
        logger.info(f"Обработка команды /start от пользователя {user.get('id')} в чате {chat_id}")
        
        # Очищаем любые пользовательские клавиатуры
        await self.clear_custom_keyboards(chat_id)
        
        welcome_text = """🤖 Привет! Я бот для создания кратких саммари текста, веб-страниц и документов.

📝 **Что я умею:**
• Суммаризация любого текста или пересланного сообщения
• Краткое изложение веб-статей - просто пришли ссылку!
• Резюме YouTube видео с извлечением субтитров (до 2 часов)
• Обработка документов: PDF, DOCX, DOC, TXT (до 20MB)
• Настраиваемые уровни сжатия: 10%, 30%, 50%

🚀 **Начни прямо сейчас:**
• Отправь текст → получи саммари
• Пришли ссылку на статью → получи резюме
• Пришли YouTube ссылку → получи краткое содержание видео
• Прикрепи документ → получи структурированное резюме
• Используй /10, /30, /50 для выбора уровня сжатия

📋 **Команды:**
/help - подробная справка
/stats - твоя статистика

🔥 Powered by Llama 3.3 70B - лучшая модель для русского языка!"""
        
        await self.send_message(chat_id, welcome_text)
    
    async def handle_help_command(self, update: dict):
        """Обработка команды /help"""
        chat_id = update["message"]["chat"]["id"]
        
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
• Работает на Llama 3.3 70B"""
        
        await self.send_message(chat_id, help_text)
    
    async def handle_smart_mode_command(self, update: dict):
        """Обработка команды /smart - переключение в режим умной суммаризации"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        # Устанавливаем флаг умной суммаризации для пользователя
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {}
        
        # Переключаем режим умной суммаризации
        current_mode = self.user_settings[user_id].get("smart_mode", False)
        self.user_settings[user_id]["smart_mode"] = not current_mode
        new_mode = self.user_settings[user_id]["smart_mode"]
        
        if new_mode:
            mode_text = """🧠 **Умная суммаризация включена!**

Теперь бот будет создавать структурированные резюме с извлечением ключевых инсайтов:

🔍 **Что изменилось:**
• Автоматическое определение типа контента (встреча, лекция, новости, etc.)
• Извлечение дат, имён, цифр и ключевых решений
• Структурированный формат с разделами по важности
• Выделение критически важных инсайтов

📝 **Поддерживаемые типы:**
• Встречи → решения, задачи, договорённости
• Лекции → концепции, выводы, применение  
• Новости → суть, участники, последствия
• Обсуждения → мнения, согласие, спорные вопросы

Отправьте любой текст, документ, аудио или ссылку для умной обработки!

_Чтобы вернуться к обычной суммаризации, снова нажмите /smart_"""
        else:
            mode_text = """📝 **Обычная суммаризация восстановлена**

Теперь бот использует стандартный режим суммаризации с настраиваемыми уровнями сжатия (10%, 30%, 50%).

Чтобы снова включить умную суммаризацию, нажмите /smart"""

        await self.send_message(chat_id, mode_text)
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
        
        await self.send_message(chat_id, stats_text)

    async def handle_compression_command(self, update: dict, compression_level: int):
        """Обработка команд уровня сжатия (/10, /30, /50 или 10%, 30%, 50%)"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        try:
            # Получаем username пользователя для логирования
            username = update["message"]["from"].get("username", "")
            
            # Сохраняем новый уровень сжатия в базе данных
            self.update_user_compression_level(user_id, compression_level, username)
            
            compression_text = f"{compression_level}%"
            confirmation_text = f"""✅ Уровень сжатия обновлен: {compression_text}

Теперь все ваши тексты будут суммаризированы с уровнем сжатия {compression_text}.

📝 Отправьте текст для суммаризации или используйте другие команды:
• /10 → максимальное сжатие (10%)
• /30 → сбалансированное сжатие (30%)  
• /50 → умеренное сжатие (50%)
• /help → справка
• /stats → статистика"""
            
            await self.send_message(chat_id, confirmation_text)
            logger.info(f"Пользователь {user_id} изменил уровень сжатия на {compression_level}%")
            
        except Exception as e:
            logger.error(f"Ошибка обработки команды сжатия {compression_level}% для пользователя {user_id}: {e}")
            await self.send_message(chat_id, "❌ Произошла ошибка при изменении настроек. Попробуйте еще раз.")
    

    

    

    
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
                
                # Обновляем сообщение о прогрессе
                if processing_message_id:
                    await self.edit_message(chat_id, processing_message_id, f"📄 Обрабатываю документ: {file_name}\n\n📝 Извлекаю текст...")
                
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
                
                # Проверяем длину извлеченного текста
                if len(extracted_text) < 100:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, f"📝 Текст слишком короткий!\n\nИз документа извлечено {len(extracted_text)} символов. Для качественной суммаризации нужно минимум 100 символов.")
                    return
                
                # Обновляем сообщение о прогрессе
                if processing_message_id:
                    await self.edit_message(chat_id, processing_message_id, f"📄 Обрабатываю документ: {file_name}\n\n🤖 Создаю резюме...")
                
                # Получаем уровень сжатия пользователя
                compression_ratio = self.get_user_compression_level(user_id)
                
                # Суммаризируем извлеченный текст
                summary = await self.summarize_file_content(extracted_text, file_name, download_result["file_extension"], compression_ratio)
                
                if summary:
                    # Формируем итоговый ответ
                    response_text = f"""📄 **Резюме документа: {file_name}**

{summary}

📊 **Статистика:**
• Исходный документ: {len(extracted_text):,} символов
• Резюме: {len(summary):,} символов  
• Сжатие: {compression_ratio:.0%}
• Метод извлечения: {text_result.get('method', 'unknown')}"""
                    
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
    
    async def handle_audio_message(self, update: dict):
        """Обработка аудио файлов и голосовых сообщений"""
        try:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            username = message["from"].get("username", "")
            
            logger.info(f"DEBUG: handle_audio_message вызван для пользователя {user_id}")
            logger.info(f"DEBUG: Содержимое сообщения: {list(message.keys())}")
            
            # Определяем тип аудио (audio, voice или document с аудио MIME)
            audio_info = None
            audio_type = ""
            
            if "audio" in message:
                audio_info = message["audio"]
                audio_type = "audio"
                file_name = audio_info.get("file_name", f"audio_{audio_info['file_id']}.mp3")
                logger.info(f"DEBUG: Обнаружен тип 'audio': {file_name}")
            elif "voice" in message:
                audio_info = message["voice"]
                audio_type = "voice"
                file_name = f"voice_message_{audio_info['file_id']}.ogg"
                logger.info(f"DEBUG: Обнаружен тип 'voice': {file_name}")
            elif "document" in message:
                # Аудио файл, переданный как документ
                audio_info = message["document"]
                audio_type = "document_audio"
                file_name = audio_info.get("file_name", f"document_audio_{audio_info['file_id']}")
                logger.info(f"DEBUG: Обнаружен тип 'document_audio': {file_name}, MIME: {audio_info.get('mime_type', 'unknown')}")
            
            if not audio_info:
                await self.send_message(chat_id, "❌ Не удалось определить тип аудио файла")
                return
            
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
            
            # Проверяем информацию о файле
            file_size = audio_info.get("file_size", 0)
            duration = audio_info.get("duration", 0)
            
            logger.info(f"🎵 Получен {audio_type} от пользователя {user_id}: {file_name} ({file_size} байт, {duration}с)")
            
            # Отправляем сообщение о начале обработки
            processing_message = await self.send_message(chat_id, f"🎵 Обрабатываю аудио: {file_name}\n\n⏳ Транскрибирую речь...")
            processing_message_id = processing_message.get("result", {}).get("message_id") if processing_message and processing_message.get("ok") else None
            
            try:
                # Получаем информацию о файле от Telegram
                file_info_response = await self.get_file_info(audio_info["file_id"])
                if not file_info_response or not file_info_response.get("ok"):
                    await self.send_message(chat_id, "❌ Не удалось получить информацию об аудио файле")
                    return
                
                file_info = file_info_response["result"]
                file_path = f"https://api.telegram.org/file/bot{self.token}/{file_info['file_path']}"
                
                # Обновляем сообщение о прогрессе
                if processing_message_id:
                    await self.edit_message(chat_id, processing_message_id, f"🎵 Обрабатываю аудио: {file_name}\n\n📥 Скачиваю файл...")
                
                # Используем audio_processor для скачивания и обработки
                download_result = await self.audio_processor.download_telegram_audio(
                    {"file_path": file_path}, file_name, file_size
                )
                
                if not download_result["success"]:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, f"❌ {download_result['error']}")
                    return
                
                # Обновляем сообщение о прогрессе
                if processing_message_id:
                    await self.edit_message(chat_id, processing_message_id, f"🎵 Обрабатываю аудио: {file_name}\n\n🎤 Распознаю речь...")
                
                # Транскрибируем аудио в текст
                transcription_result = self.audio_processor.transcribe_audio(download_result["file_path"])
                
                # Очищаем временные файлы
                self.audio_processor.cleanup_temp_file(download_result["temp_dir"])
                
                if not transcription_result["success"]:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, f"❌ {transcription_result['error']}")
                    return
                
                transcribed_text = transcription_result["text"]
                
                # Проверяем длину транскрипции
                if len(transcribed_text) < 50:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, f"📝 Транскрипция слишком короткая!\n\nРаспознано {len(transcribed_text)} символов. Для качественной суммаризации нужно минимум 50 символов.\n\n📄 Транскрипция:\n{transcribed_text}")
                    return
                
                # Обновляем сообщение о прогрессе
                if processing_message_id:
                    await self.edit_message(chat_id, processing_message_id, f"🎵 Обрабатываю аудио: {file_name}\n\n🤖 Создаю резюме...")
                
                # Получаем уровень сжатия пользователя
                compression_ratio = self.get_user_compression_level(user_id)
                
                # Проверяем, включена ли умная суммаризация
                smart_mode = self.user_settings.get(user_id, {}).get("smart_mode", False)
                
                if smart_mode and self.smart_summarizer:
                    # Умная суммаризация аудио
                    target_ratio = compression_ratio / 100.0
                    smart_result = await self.smart_summarizer.smart_summarize(
                        transcribed_text, source_type="audio", 
                        source_name=file_name, 
                        compression_ratio=target_ratio
                    )
                    summary = self.smart_summarizer.format_smart_response(
                        smart_result, f"аудио: {file_name}", len(transcribed_text)
                    )
                else:
                    # Обычная суммаризация аудио
                    summary = await self.summarize_audio_content(transcribed_text, file_name, duration, compression_ratio)
                
                if summary:
                    # Формируем итоговый ответ
                    method_info = transcription_result.get('method', 'unknown')
                    audio_duration = transcription_result.get('duration', duration)
                    
                    response_text = f"""🎵 **Резюме аудио: {file_name}**

{summary}

📊 **Статистика:**
• Длительность: {audio_duration:.1f} сек ({audio_duration/60:.1f} мин)
• Транскрипция: {len(transcribed_text):,} символов
• Резюме: {len(summary):,} символов  
• Сжатие: {compression_ratio:.0%}
• Метод распознавания: {method_info}

📄 **Полная транскрипция:**
{transcribed_text}"""
                    
                    # Удаляем сообщение о обработке
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    
                    await self.send_message(chat_id, response_text)
                    
                    # Сохраняем в базу данных
                    try:
                        self.db.save_user_request(user_id, f"audio:{file_name}", len(transcribed_text), len(summary), audio_duration, f'groq_audio_{method_info}')
                    except Exception as save_error:
                        logger.error(f"Ошибка сохранения аудио запроса в БД: {save_error}")
                    
                    logger.info(f"🎵 Успешно обработан аудио {file_name} пользователя {user_id}")
                    
                else:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, f"❌ Не удалось создать резюме аудио\n\n📄 Транскрипция доступна:\n{transcribed_text}")
                    
            except Exception as e:
                logger.error(f"Критическая ошибка при обработке аудио: {str(e)}")
                if processing_message_id:
                    await self.edit_message(
                        chat_id, processing_message_id,
                        f"❌ Произошла критическая ошибка!\n\nПожалуйста, попробуйте позже или обратитесь к администратору."
                    )
        
        finally:
            # Удаляем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)
    
    async def summarize_audio_content(self, text: str, file_name: str = "", duration: float = 0, compression_ratio: float = 0.3) -> str:
        """Создает резюме аудио контента через Groq API"""
        try:
            if not self.groq_client:
                return "❌ Groq API недоступен"
            
            # Ограничиваем длину текста
            max_chars = 12000  # Лимит для аудио транскрипций
            original_length = len(text)
            
            if len(text) > max_chars:
                text = text[:max_chars] + "...\n[Транскрипция обрезана для обработки]"
            
            # Определяем длину резюме в зависимости от длительности аудио и уровня сжатия
            if duration < 300:  # Менее 5 минут
                summary_length = "100-200 слов"
                max_tokens = 250
            elif duration < 1200:  # Менее 20 минут
                summary_length = "200-400 слов"
                max_tokens = 450
            else:  # Длинное аудио
                summary_length = "300-600 слов"
                max_tokens = 650
            
            prompt = f"""Ты - эксперт по анализу аудио контента. Создай подробное резюме аудиозаписи на том же языке, что и исходная транскрипция.

Требования к резюме:
- Длина: {summary_length} (сжатие {compression_ratio:.0%})
- Структурированный формат с заголовками
- Сохрани все ключевые моменты и важную информацию
- Если речь на русском - отвечай на русском языке
- Учитывай особенности устной речи (повторы, паузы, неточности)

Формат резюме:
🎤 **Основные темы:**
• Главные обсуждаемые вопросы (2-3 пункта)

💬 **Ключевые моменты:**
• Важные высказывания и факты (3-5 пунктов)

🔑 **Выводы:**
• Основные заключения и результаты (1-2 пункта)

Начни ответ сразу с резюме, без вступлений.

ТРАНСКРИПЦИЯ АУДИО:
{text}"""

            completion = self.groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "Ты эксперт по созданию качественных резюме аудио контента. Создавай четкие, информативные и полезные саммари на языке исходной транскрипции."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=max_tokens,
                temperature=0.3
            )

            summary = completion.choices[0].message.content.strip()
            return summary

        except Exception as e:
            logger.error(f"Ошибка суммаризации аудио: {e}")
            return f"❌ Ошибка создания резюме: {str(e)}"
    
    async def edit_message(self, chat_id: int, message_id: int, text: str):
        """Редактирует существующее сообщение"""
        try:
            url = f"{self.base_url}/editMessageText"
            data = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "Markdown"
            }
            
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
            
            if "message" in update:
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
                
                if text:
                    # Определяем тип сообщения для логирования
                    if "forward_from" in message or "forward_from_chat" in message or "forward_origin" in message:
                        logger.info(f"Получено пересланное сообщение от пользователя {user_id}: '{text[:50]}...'")
                    else:
                        logger.info(f"Получено сообщение от пользователя {user_id}: '{text[:50]}...'")
                elif "forward_from" in message or "forward_from_chat" in message or "forward_origin" in message:
                    # Пересланное сообщение без текста - просто игнорируем без ошибки
                    logger.info(f"Получено пересланное медиа сообщение без текста от пользователя {user_id} - игнорируем")
                    return
                
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
                elif "audio" in message or "voice" in message:
                    # Обработка аудио файлов и голосовых сообщений
                    await self.handle_audio_message(update)
                    return
                elif "document" in message:
                    # Проверяем, не является ли документ аудио файлом
                    document = message["document"]
                    mime_type = document.get("mime_type", "")
                    file_name = document.get("file_name", "").lower()
                    
                    # Список аудио MIME-типов и расширений
                    audio_mime_types = [
                        "audio/mpeg", "audio/mp3", "audio/wav", "audio/m4a", 
                        "audio/ogg", "audio/flac", "audio/aac", "audio/opus"
                    ]
                    audio_extensions = [".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus"]
                    
                    is_audio = (
                        mime_type in audio_mime_types or 
                        any(file_name.endswith(ext) for ext in audio_extensions)
                    )
                    
                    if is_audio:
                        logger.info(f"Документ определен как аудио файл: {file_name}, MIME: {mime_type}")
                        # Создаем псевдо-аудио объект для совместимости с handle_audio_message
                        audio_message = update.copy()
                        audio_message["message"]["audio"] = document
                        await self.handle_audio_message(audio_message)
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
            "allowed_updates": ["message"]
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
                    
                    # Извлекаем контент
                    start_time = time.time()
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
                        response_text = f"""📄 Резюме статьи (Уровень сжатия: {user_compression_level}%)

🔗 Источник: {content_result['title'][:100]}
📎 Ссылка: {url}

📝 Основные моменты:
{summary}

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
                duration_str = f"{video_duration//60}:{video_duration%60:02d}"
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