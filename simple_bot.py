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
        
        # Состояния пользователей для настраиваемой суммаризации
        self.user_states: Dict[int, dict] = {}
        self.user_settings: Dict[int, dict] = {}
        
        # Временное хранение сообщений для объединения
        self.user_messages_buffer: Dict[int, list] = {}
        
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
    
    async def send_message(self, chat_id: int, text: str, parse_mode: Optional[str] = None, reply_markup: dict = None):
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
        
        welcome_text = """🤖 Привет! Я бот для создания кратких саммари текста.

Просто отправь мне любой текст или перешли сообщение из любого канала, и я создам его краткое содержание.

Доступные команды:
/help - помощь
/stats - статистика
/summarize - настраиваемая суммаризация

Начни прямо сейчас - отправь текст или перешли сообщение!

🔥 Powered by Llama 3.3 70B - лучшая модель для русского языка!"""
        
        await self.send_message(chat_id, welcome_text)
    
    async def handle_help_command(self, update: dict):
        """Обработка команды /help"""
        chat_id = update["message"]["chat"]["id"]
        
        help_text = """📖 Как использовать бота:

🔥 БЫСТРАЯ СУММАРИЗАЦИЯ:
1. Отправь любой текст (минимум 50 символов)
2. Или перешли любое сообщение из канала/чата
3. Получи краткое саммари (20-70% от исходного размера)

⚙️ НАСТРАИВАЕМАЯ СУММАРИЗАЦИЯ:
1. Используй команду /summarize
2. Выбери уровень сжатия (10%, 30%, 50%)
3. Выбери формат результата
4. Отправь текст или пересланные сообщения

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
    
    async def handle_summarize_command(self, update: dict):
        """Обработка команды /summarize для настраиваемой суммаризации"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]
        
        logger.info(f"🚀 SUMMARIZE COMMAND: Обработка команды /summarize от пользователя {user_id} в чате {chat_id}")
        
        # Сбрасываем состояние пользователя
        self.user_states[user_id] = {"step": "compression_level"}
        self.user_settings[user_id] = {}
        self.user_messages_buffer[user_id] = []
        
        logger.info(f"🔧 SUMMARIZE COMMAND: Инициализированы словари для пользователя {user_id}")
        logger.info(f"🔧 SUMMARIZE COMMAND: user_states[{user_id}] = {self.user_states[user_id]}")
        logger.info(f"🔧 SUMMARIZE COMMAND: user_settings[{user_id}] = {self.user_settings[user_id]}")
        logger.info(f"🔧 SUMMARIZE COMMAND: user_messages_buffer[{user_id}] = {self.user_messages_buffer[user_id]}")
        
        logger.info(f"📋 SUMMARIZE COMMAND: Отправка меню выбора уровня сжатия в чат {chat_id}")
        menu_result = await self.send_compression_level_menu(chat_id)
        logger.info(f"📤 SUMMARIZE COMMAND: Результат отправки меню: {menu_result}")
        
        # Добавляем резервные инструкции
        backup_text = """💡 Если кнопки не работают, отправьте текстом:
• "10%" - для максимального сжатия
• "30%" - для сбалансированного сжатия  
• "50%" - для умеренного сжатия"""
        
        backup_result = await self.send_message(chat_id, backup_text)
        logger.info(f"🔄 SUMMARIZE COMMAND: Резервные инструкции отправлены: {backup_result}")
    
    async def send_compression_level_menu(self, chat_id: int):
        """Отправка меню выбора уровня сжатия"""
        logger.info(f"📋 COMPRESSION MENU: Подготовка меню выбора уровня сжатия для чата {chat_id}")
        
        text = """⚙️ Настройка суммаризации

Выберите уровень сжатия текста:

🔥 10% - Максимальное сжатие (только самое важное)
📝 30% - Сбалансированное сжатие (основные моменты)
📄 50% - Умеренное сжатие (подробное изложение)"""
        
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🔥 10%", "callback_data": "compression_10"},
                    {"text": "📝 30%", "callback_data": "compression_30"},
                    {"text": "📄 50%", "callback_data": "compression_50"}
                ]
            ]
        }
        
        logger.info(f"📋 COMPRESSION MENU: Keyboard data: {json.dumps(keyboard, ensure_ascii=False)}")
        logger.info(f"📋 COMPRESSION MENU: Отправка сообщения с inline-клавиатурой в чат {chat_id}")
        
        result = await self.send_message(chat_id, text, reply_markup=keyboard)
        logger.info(f"📤 COMPRESSION MENU: Результат отправки: {result}")
        

        
        return result
    
    async def send_format_menu(self, chat_id: int):
        """Отправка меню выбора формата результата"""
        text = """📋 Выберите формат результата:

• Маркированный список - ключевые пункты с bullet points
📄 Связный абзац - краткое изложение в виде текста
🏷️ Ключевые слова - список важных терминов"""
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "• Маркированный список", "callback_data": "format_bullets"}],
                [{"text": "📄 Связный абзац", "callback_data": "format_paragraph"}],
                [{"text": "🏷️ Ключевые слова", "callback_data": "format_keywords"}]
            ]
        }
        
        await self.send_message(chat_id, text, reply_markup=keyboard)
    
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
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "❌ Отменить", "callback_data": "cancel_summarize"}]
            ]
        }
        
        await self.send_message(chat_id, text, reply_markup=keyboard)
        
        # Устанавливаем состояние ожидания текста
        self.user_states[user_id]["step"] = "waiting_text"
    
    async def handle_callback_query(self, callback_query: dict):
        """Обработка нажатий на inline-клавиатуру"""
        try:
            logger.info(f"🔍 DEBUG: Получен callback_query целиком: {json.dumps(callback_query, ensure_ascii=False, indent=2)}")
            
            chat_id = callback_query["message"]["chat"]["id"]
            user_id = callback_query["from"]["id"]
            data = callback_query["data"]
            message_id = callback_query["message"]["message_id"]
            callback_id = callback_query["id"]
            
            logger.info(f"🎯 CALLBACK PROCESSING: user_id={user_id}, chat_id={chat_id}, data='{data}', message_id={message_id}, callback_id={callback_id}")
            
            # Проверяем состояния пользователя перед обработкой
            logger.info(f"📊 CALLBACK STATE CHECK: Текущие состояния пользователя {user_id}:")
            logger.info(f"📊 user_states.get({user_id}): {self.user_states.get(user_id, 'NOT_FOUND')}")
            logger.info(f"📊 user_settings.get({user_id}): {self.user_settings.get(user_id, 'NOT_FOUND')}")
            logger.info(f"📊 user_messages_buffer.get({user_id}): {self.user_messages_buffer.get(user_id, 'NOT_FOUND')}")
            
            # Подтверждаем получение callback
            logger.info(f"📞 Отправка answer_callback_query для {callback_id}")
            answer_result = await self.answer_callback_query(callback_id)
            logger.info(f"✅ Результат answer_callback_query: {answer_result}")
            
            if data.startswith("compression_"):
                logger.info(f"🔧 COMPRESSION: Обработка выбора уровня сжатия")
                # Выбор уровня сжатия
                compression_level = data.split("_")[1]
                logger.info(f"📊 Выбран уровень сжатия: {compression_level}%")
                
                self.user_settings[user_id] = {"compression": compression_level}
                self.user_states[user_id]["step"] = "format_selection"
                logger.info(f"💾 Сохранены настройки пользователя {user_id}: {self.user_settings[user_id]}")
                logger.info(f"🔄 Установлен статус пользователя {user_id}: {self.user_states[user_id]}")
                
                # Обновляем сообщение с новым меню
                logger.info(f"✏️ Обновление сообщения {message_id} в чате {chat_id}")
                edit_result = await self.edit_message(chat_id, message_id, "✅ Уровень сжатия выбран")
                logger.info(f"📝 Результат edit_message: {edit_result}")
                
                logger.info(f"📋 Отправка меню выбора формата в чат {chat_id}")
                format_result = await self.send_format_menu(chat_id)
                logger.info(f"📤 Результат send_format_menu: {format_result}")
                
            elif data.startswith("format_"):
                logger.info(f"📄 FORMAT: Обработка выбора формата результата")
                # Выбор формата результата
                format_type = data.split("_")[1]
                logger.info(f"🎨 Выбран формат: {format_type}")
                
                self.user_settings[user_id]["format"] = format_type
                logger.info(f"💾 Обновлены настройки пользователя {user_id}: {self.user_settings[user_id]}")
                
                # Обновляем сообщение и переходим к запросу текста
                logger.info(f"✏️ Обновление сообщения {message_id} с подтверждением выбора формата")
                edit_result = await self.edit_message(chat_id, message_id, "✅ Формат результата выбран")
                logger.info(f"📝 Результат edit_message: {edit_result}")
                
                logger.info(f"📝 Отправка запроса текста пользователю {user_id}")
                text_request_result = await self.send_text_request(chat_id, user_id)
                logger.info(f"📤 Результат send_text_request: {text_request_result}")
                
            elif data == "process_now":
                # Обработка собранных сообщений
                await self.edit_message(chat_id, message_id, "🚀 Начинаю обработку...")
                await self.process_custom_summarization(chat_id, user_id)
                
            elif data == "cancel_summarize":
                # Отмена настраиваемой суммаризации
                if user_id in self.user_states:
                    del self.user_states[user_id]
                if user_id in self.user_settings:
                    del self.user_settings[user_id]
                if user_id in self.user_messages_buffer:
                    del self.user_messages_buffer[user_id]
                    
                await self.edit_message(chat_id, message_id, "❌ Настраиваемая суммаризация отменена")
                await self.send_message(chat_id, "Используйте /start для возврата в главное меню или просто отправьте текст для быстрой суммаризации.")
                
        except Exception as e:
            logger.error(f"❌ CALLBACK ERROR: Критическая ошибка обработки callback query: {e}")
            import traceback
            logger.error(f"🔍 CALLBACK TRACEBACK: {traceback.format_exc()}")
            # Пытаемся отправить ошибку пользователю
            try:
                await self.answer_callback_query(callback_query.get("id", ""), "Произошла ошибка при обработке")
            except:
                logger.error("❌ Не удалось отправить error callback response")
    
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
                    f"Отправьте еще текст или нажмите кнопку для обработки:",
                    reply_markup={
                        "inline_keyboard": [[
                            {"text": "🚀 Обработать сейчас", "callback_data": "process_now"},
                            {"text": "❌ Отменить", "callback_data": "cancel_summarize"}
                        ]]
                    })
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
            self.save_user_request(user_id, total_chars, len(summary))
            
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
        
        # Проверяем резервные команды для настраиваемой суммаризации
        if message_text and user_id in self.user_states and self.user_states[user_id].get("step") == "compression_level":
            if message_text.strip() in ["10%", "30%", "50%"]:
                logger.info(f"🔄 BACKUP COMMAND: Пользователь {user_id} выбрал уровень сжатия текстом: {message_text.strip()}")
                # Имитируем callback для обработки
                import time
                fake_callback = {
                    "id": f"manual_{int(time.time() * 1000)}",
                    "from": {"id": user_id},
                    "message": {"chat": {"id": chat_id}, "message_id": 1},
                    "data": f"compression_{message_text.strip().replace('%', '')}"
                }
                await self.handle_callback_query(fake_callback)
                return
        
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
                            clean_text = text.replace(' ', '').replace('\n', '').replace('\t', '')
                            if len(clean_text) < 10:
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
                    # Пересланное сообщение без текста
                    logger.warning(f"Пересланное сообщение не содержит текста")
                    await self.send_message(chat_id, "❌ Пересланное сообщение не содержит текста для суммаризации.\n\nПожалуйста, пересылайте только текстовые сообщения или сообщения с подписями к изображениям.")
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
                        elif text == "/summarize":
                            await self.handle_summarize_command(update)
                        else:
                            logger.warning(f"Неизвестная команда: {text}")
                            await self.send_message(
                                chat_id,
                                "❓ Неизвестная команда. Используйте /help для получения справки."
                            )
                    else:
                        # Проверяем, находится ли пользователь в режиме настраиваемой суммаризации
                        if user_id in self.user_states and self.user_states[user_id].get("step") == "waiting_text":
                            await self.handle_custom_summarize_text(update, text)
                        else:
                            # Обработка текстовых сообщений (обычных и пересланных)
                            logger.info(f"Обработка текстового сообщения от пользователя {user_id}")
                            await self.handle_text_message(update, message_text=text)
                else:
                    logger.warning(f"DEBUG: Сообщение не содержит текста после extract_text_from_message: {message}")
                    # Проверяем, есть ли другие типы контента
                    if any(key in message for key in ['photo', 'video', 'document', 'audio', 'voice', 'sticker']):
                        await self.send_message(chat_id, "❌ Данный тип сообщения не поддерживается.\n\nБот работает только с текстовыми сообщениями. Пожалуйста, отправьте или перешлите текстовое сообщение для суммаризации.")
                    else:
                        await self.send_message(chat_id, "❌ Сообщение не содержит текста.\n\nПожалуйста, отправьте текстовое сообщение для суммаризации.")
            elif "callback_query" in update:
                logger.info(f"🎯 MAIN HANDLER: Обнаружен callback_query в update")
                logger.info(f"🎯 MAIN HANDLER: callback_query data: {update['callback_query'].get('data', 'NO_DATA')}")
                # Обработка нажатий на inline-клавиатуру
                await self.handle_callback_query(update["callback_query"])
                logger.info(f"✅ MAIN HANDLER: Завершена обработка callback_query")
                return
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
                    
                    # Проверяем наличие callback_query в полученных обновлениях
                    if result and result.get("ok"):
                        update_list = result.get("result", [])
                        logger.info(f"🔄 GET_UPDATES: Получено {len(update_list)} обновлений")
                        for update in update_list:
                            if "callback_query" in update:
                                logger.info(f"🎯 GET_UPDATES: ПОЛУЧЕН CALLBACK_QUERY: {json.dumps(update['callback_query'], ensure_ascii=False)}")
                            elif "message" in update:
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
                    "command": "summarize",
                    "description": "⚙️ Настраиваемая суммаризация"
                }
            ]
            
            url = f"{self.base_url}/setMyCommands"
            data = {"commands": json.dumps(commands)}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info("Команды бота установлены: /help, /stats, /summarize")
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
    
    async def answer_callback_query(self, callback_query_id: str, text: str = None):
        """Подтверждение получения callback query"""
        try:
            url = f"{self.base_url}/answerCallbackQuery"
            data = {"callback_query_id": callback_query_id}
            if text:
                data["text"] = text
            
            logger.info(f"📞 ANSWER_CALLBACK: Отправка answerCallbackQuery для {callback_query_id}")
            logger.info(f"📞 ANSWER_CALLBACK: URL: {url}")
            logger.info(f"📞 ANSWER_CALLBACK: Data: {json.dumps(data, ensure_ascii=False)}")
                
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    logger.info(f"📞 ANSWER_CALLBACK: HTTP status: {response.status}")
                    result = await response.json()
                    logger.info(f"📞 ANSWER_CALLBACK: Response: {json.dumps(result, ensure_ascii=False)}")
                    success = result.get("ok", False)
                    logger.info(f"📞 ANSWER_CALLBACK: Success: {success}")
                    return success
        except Exception as e:
            logger.error(f"❌ ANSWER_CALLBACK ERROR: Ошибка подтверждения callback query: {e}")
            import traceback
            logger.error(f"🔍 ANSWER_CALLBACK TRACEBACK: {traceback.format_exc()}")
            return False
    
    async def edit_message(self, chat_id: int, message_id: int, text: str, reply_markup: dict = None):
        """Редактирование существующего сообщения"""
        try:
            url = f"{self.base_url}/editMessageText"
            data = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text
            }
            if reply_markup:
                data["reply_markup"] = reply_markup  # Убираем json.dumps()
            
            async with aiohttp.ClientSession() as session:
                # Используем json=data когда есть reply_markup, иначе data=data
                if reply_markup:
                    async with session.post(url, json=data) as response:
                        result = await response.json()
                else:
                    async with session.post(url, data=data) as response:
                        result = await response.json()
                        
                return result.get("result") if result.get("ok") else None
        except Exception as e:
            logger.error(f"❌ EDIT_MESSAGE ERROR: Ошибка редактирования сообщения: {e}")
            import traceback
            logger.error(f"🔍 EDIT_MESSAGE TRACEBACK: {traceback.format_exc()}")
            return None
    
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