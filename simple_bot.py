#!/usr/bin/env python3
"""
Simple Telegram Bot для суммаризации текста
Минимальная версия с прямым использованием Telegram Bot API
"""

import logging
import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Set, Optional
import os
import sys
import aiohttp
import sqlite3
from groq import Groq
from dotenv import load_dotenv

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
        
        # Инициализация базы данных
        self.init_database()
        
        logger.info("Simple Telegram Bot инициализирован")
    
    def init_database(self):
        """Инициализация базы данных"""
        try:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            
            # Таблица запросов пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    original_text_length INTEGER NOT NULL,
                    summary_length INTEGER NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица настроек пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    summary_ratio REAL DEFAULT 0.3,
                    language_preference TEXT DEFAULT 'auto'
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info("База данных инициализирована")
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")
    
    def save_user_request(self, user_id: int, username: str, original_length: int, summary_length: int):
        """Сохранение запроса пользователя"""
        try:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO user_requests (user_id, username, original_text_length, summary_length)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, original_length, summary_length))
            
            # Создаем настройки пользователя если их нет
            cursor.execute("""
                INSERT OR IGNORE INTO user_settings (user_id, summary_ratio, language_preference)
                VALUES (?, 0.3, 'auto')
            """, (user_id,))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Ошибка сохранения запроса: {e}")
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Получение статистики пользователя"""
        try:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_requests,
                    SUM(original_text_length) as total_chars,
                    SUM(summary_length) as total_summary_chars,
                    MIN(timestamp) as first_request
                FROM user_requests 
                WHERE user_id = ?
            """, (user_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row and row[0] > 0:
                total_chars = row[1] or 0
                total_summary_chars = row[2] or 0
                avg_compression = (total_summary_chars / total_chars) if total_chars > 0 else 0
                
                return {
                    'total_requests': row[0],
                    'total_chars': total_chars,
                    'total_summary_chars': total_summary_chars,
                    'avg_compression': avg_compression,
                    'first_request': row[3]
                }
            else:
                return {
                    'total_requests': 0,
                    'total_chars': 0,
                    'total_summary_chars': 0,
                    'avg_compression': 0,
                    'first_request': None
                }
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {'total_requests': 0, 'total_chars': 0, 'total_summary_chars': 0, 'avg_compression': 0, 'first_request': None}
    
    async def send_message(self, chat_id: int, text: str, parse_mode: Optional[str] = None):
        """Отправка сообщения"""
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text
        }
        if parse_mode:
            data["parse_mode"] = parse_mode
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info(f"Сообщение успешно отправлено в чат {chat_id}")
                    else:
                        logger.error(f"Ошибка отправки сообщения в чат {chat_id}: {result}")
                    return result
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в чат {chat_id}: {e}")
            return None
    
    async def delete_message(self, chat_id: int, message_id: int):
        """Удаление сообщения"""
        url = f"{self.base_url}/deleteMessage"
        data = {
            "chat_id": chat_id,
            "message_id": message_id
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    return await response.json()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
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
            return f"❌ Ошибка при обработке текста: {str(e)[:100]}"
    
    async def handle_start_command(self, update: dict):
        """Обработка команды /start"""
        chat_id = update["message"]["chat"]["id"]
        user = update["message"]["from"]
        
        logger.info(f"Обработка команды /start от пользователя {user.get('id')} в чате {chat_id}")
        
        # Очищаем любые пользовательские клавиатуры
        await self.clear_custom_keyboards(chat_id)
        
        welcome_text = """🤖 Привет! Я бот для создания кратких саммари текста.

Просто отправь мне любой текст или перешли сообщение из любого канала, и я создам его краткое содержание.

Доступные команды:
/help - помощь
/stats - статистика

Начни прямо сейчас - отправь текст или перешли сообщение!

🔥 Powered by Llama 3.3 70B - лучшая модель для русского языка!"""
        
        await self.send_message(chat_id, welcome_text)
    
    async def handle_help_command(self, update: dict):
        """Обработка команды /help"""
        chat_id = update["message"]["chat"]["id"]
        
        help_text = """📖 Как использовать бота:

1. Отправь любой текст (минимум 50 символов)
2. Или перешли любое сообщение из канала/чата
3. Получи краткое саммари (20-70% от исходного размера)

Особенности:
• Работаю с текстами любой длины
• Поддерживаю пересланные сообщения из любых каналов
• Превосходно понимаю русский язык (используется Llama 3.3 70B)
• Сохраняю ключевые моменты исходного текста
• Структурирую саммари для лучшей читаемости
• Полностью бесплатный - использую Groq API

Поддерживаемые языки: Русский, Английский

Лимиты: До 10 запросов в минуту на пользователя"""
        
        await self.send_message(chat_id, help_text)
    
    async def handle_stats_command(self, update: dict):
        """Обработка команды /stats"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        user_stats = self.get_user_stats(user_id)
        
        stats_text = f"""📊 Ваша статистика:

• Обработано текстов: {user_stats['total_requests']}
• Символов обработано: {user_stats['total_chars']:,}
• Символов в саммари: {user_stats['total_summary_chars']:,}
• Среднее сжатие: {user_stats['avg_compression']:.1%}
• Первый запрос: {user_stats['first_request'] or 'Нет данных'}

📈 Используйте бота для обработки длинных текстов и статей!"""
        
        await self.send_message(chat_id, stats_text)
    
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
            # Функция для извлечения текста из сообщения
            def extract_text_from_message(msg):
                if "text" in msg:
                    return msg["text"]
                elif "caption" in msg:
                    return msg["caption"]
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
            
            # Выполняем суммаризацию
            summary = await self.summarize_text(text, target_ratio=0.3)
            
            processing_time = time.time() - start_time
            
            if summary and not summary.startswith("❌"):
                # Сохраняем запрос в базу данных
                self.save_user_request(user_id, username, len(text), len(summary))
                
                # Вычисляем статистику
                compression_ratio = len(summary) / len(text)
                
                # Формируем ответ
                response_text = f"""📋 Саммари готово!

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
                
                # Функция для извлечения текста из сообщения
                def extract_text_from_message(msg):
                    if "text" in msg:
                        return msg["text"]
                    elif "caption" in msg:
                        return msg["caption"]
                    return None
                
                # Извлекаем текст из сообщения (работает для обычных и пересланных)
                text = extract_text_from_message(message)
                
                if text:
                    # Определяем тип сообщения для логирования
                    if "forward_from" in message or "forward_from_chat" in message or "forward_origin" in message:
                        logger.info(f"Получено пересланное сообщение от пользователя {user_id}: '{text[:50]}...'")
                    else:
                        logger.info(f"Получено сообщение от пользователя {user_id}: '{text[:50]}...'")
                elif "forward_from" in message or "forward_from_chat" in message or "forward_origin" in message:
                    # Пересланное сообщение без текста
                    logger.warning(f"Пересланное сообщение не содержит текста")
                    await self.send_message(chat_id, "❌ Пересланное сообщение не содержит текста для суммаризации.\n\nПожалуйста, пересылайте только текстовые сообщения или сообщения с подписями к изображениям.")
                    return
                
                if text:
                    if text.startswith("/"):
                        # Обработка команд
                        logger.info(f"Обработка команды: {text}")
                        if text == "/start":
                            await self.handle_start_command(update)
                        elif text == "/help":
                            await self.handle_help_command(update)
                        elif text == "/stats":
                            await self.handle_stats_command(update)
                        else:
                            logger.warning(f"Неизвестная команда: {text}")
                            await self.send_message(
                                chat_id,
                                "❓ Неизвестная команда. Используйте /help для получения справки."
                            )
                    else:
                        # Обработка текстовых сообщений (обычных и пересланных)
                        logger.info(f"Обработка текстового сообщения от пользователя {user_id}")
                        await self.handle_text_message(update, message_text=text)
                else:
                    logger.warning(f"Сообщение не содержит текста: {message}")
                    # Проверяем, есть ли другие типы контента
                    if any(key in message for key in ['photo', 'video', 'document', 'audio', 'voice', 'sticker']):
                        await self.send_message(chat_id, "❌ Данный тип сообщения не поддерживается.\n\nБот работает только с текстовыми сообщениями. Пожалуйста, отправьте или перешлите текстовое сообщение для суммаризации.")
                    else:
                        await self.send_message(chat_id, "❌ Сообщение не содержит текста.\n\nПожалуйста, отправьте текстовое сообщение для суммаризации.")
            else:
                logger.warning(f"Обновление не содержит сообщения: {update}")
                        
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
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    result = await response.json()
                    return result
        except Exception as e:
            logger.error(f"Ошибка получения обновлений: {e}")
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
                }
            ]
            
            url = f"{self.base_url}/setMyCommands"
            data = {"commands": json.dumps(commands)}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info("Команды бота установлены: только /help и /stats")
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