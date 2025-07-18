#!/usr/bin/env python3
"""
Telegram Bot для суммаризации текста с использованием Groq API и Hugging Face fallback
Основной файл с логикой бота и обработчиками команд
"""

import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Set
import os
import sys

from telegram import Update, BotCommand
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes,
    CallbackQueryHandler
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config import Config
from summarizer import TextSummarizer
from database import DatabaseManager

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

class TelegramSummarizerBot:
    """Основной класс Telegram бота для суммаризации текста"""
    
    def __init__(self):
        self.config = Config()
        self.db = DatabaseManager(self.config.DATABASE_URL)
        self.summarizer = TextSummarizer(
            groq_api_key=self.config.GROQ_API_KEY,
            use_local_fallback=True
        )
        
        # Защита от спама - лимиты запросов
        self.user_requests: Dict[int, list] = {}
        self.processing_users: Set[int] = set()
        
        # Инициализация базы данных
        self.db.init_database()
        
        logger.info("Telegram Summarizer Bot инициализирован")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start"""
        user = update.effective_user
        logger.info(f"Пользователь {user.id} ({user.username}) выполнил команду /start")
        
        # Регистрируем пользователя в базе данных
        self.db.save_user_request(user.id, user.username, 0, 0)
        
        welcome_text = """🤖 *Привет! Я бот для создания кратких саммари текста\\.*

Просто отправь мне любой текст, и я создам его краткое содержание\\.

*Доступные команды:*
/help \\- помощь
/stats \\- статистика
/settings \\- настройки

*Начни прямо сейчас \\- отправь мне текст\\!*

🔥 *Powered by Llama 3\\.1 70B \\- лучшая модель для русского языка\\!*"""
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help"""
        user = update.effective_user
        logger.info(f"Пользователь {user.id} запросил помощь")
        
        help_text = """📖 *Как использовать бота:*

1\\. Отправь любой текст \\(минимум 50 символов\\)
2\\. Получи краткое саммари \\(20\\-70% от исходного размера\\)
3\\. Используй /settings для настройки длины саммари

*Особенности:*
• Работаю с текстами любой длины
• Превосходно понимаю русский язык \\(используется Llama 3\\.1 70B\\)
• Сохраняю ключевые моменты исходного текста
• Структурирую саммари для лучшей читаемости
• Полностью бесплатный \\- использую Groq API

*Поддерживаемые языки:* Русский, Английский

*Лимиты:* До 10 запросов в минуту на пользователя"""
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /stats"""
        user = update.effective_user
        logger.info(f"Пользователь {user.id} запросил статистику")
        
        user_stats = self.db.get_user_stats(user.id)
        total_stats = self.db.get_total_stats()
        
        stats_text = f"""📊 *Ваша статистика:*

• Обработано текстов: {user_stats['total_requests']}
• Символов обработано: {user_stats['total_chars']:,}
• Символов в саммари: {user_stats['total_summary_chars']:,}
• Среднее сжатие: {user_stats['avg_compression']:.1%}
• Первый запрос: {user_stats['first_request'] or 'Нет данных'}

📈 *Общая статистика бота:*
• Всего запросов: {total_stats['total_requests']:,}
• Активных пользователей: {total_stats['total_users']:,}
• Символов обработано: {total_stats['total_chars']:,}"""
        
        await update.message.reply_text(
            stats_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /settings"""
        user = update.effective_user
        logger.info(f"Пользователь {user.id} открыл настройки")
        
        current_settings = self.db.get_user_settings(user.id)
        
        settings_text = f"""⚙️ *Настройки суммаризации:*

*Текущие настройки:*
• Длина саммари: {current_settings['summary_ratio']:.0%} от исходного текста
• Язык: {current_settings['language_preference']}

*Доступные команды для изменения:*
/set\\_ratio\\_20 \\- Короткие саммари \\(20%\\)
/set\\_ratio\\_30 \\- Средние саммари \\(30%\\) \\[По умолчанию\\]
/set\\_ratio\\_50 \\- Подробные саммари \\(50%\\)
/set\\_ratio\\_70 \\- Очень подробные \\(70%\\)

*Примечание:* Фактическая длина может варьироваться в зависимости от содержания текста\\."""
        
        await update.message.reply_text(
            settings_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    async def set_ratio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команд изменения соотношения длины саммари"""
        user = update.effective_user
        command = update.message.text.lower()
        
        ratio_map = {
            '/set_ratio_20': 0.2,
            '/set_ratio_30': 0.3,
            '/set_ratio_50': 0.5,
            '/set_ratio_70': 0.7
        }
        
        if command in ratio_map:
            new_ratio = ratio_map[command]
            self.db.update_user_settings(user.id, summary_ratio=new_ratio)
            
            logger.info(f"Пользователь {user.id} изменил соотношение на {new_ratio:.0%}")
            
            await update.message.reply_text(
                f"✅ *Настройки обновлены\\!*\n\nДлина саммари установлена на {new_ratio:.0%} от исходного текста\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await update.message.reply_text(
                "❌ Неизвестная команда\\. Используйте /settings для просмотра доступных опций\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    
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
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик текстовых сообщений для суммаризации"""
        user = update.effective_user
        text = update.message.text
        
        logger.info(f"Получен текст от пользователя {user.id} ({user.username}), длина: {len(text)} символов")
        
        # Проверка лимита запросов
        if not self.check_user_rate_limit(user.id):
            await update.message.reply_text(
                "⏰ *Превышен лимит запросов\\!*\n\nПожалуйста, подождите минуту перед отправкой нового текста\\. Лимит: 10 запросов в минуту\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Проверка на повторную обработку
        if user.id in self.processing_users:
            await update.message.reply_text(
                "⚠️ *Обработка в процессе\\!*\n\nПожалуйста, дождитесь завершения предыдущего запроса\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Проверка минимальной длины текста
        if len(text) < 50:
            await update.message.reply_text(
                f"📝 *Текст слишком короткий\\!*\n\nДля качественной суммаризации нужно минимум 50 символов\\.\nВаш текст: {len(text)} символов\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Добавляем пользователя в список обрабатываемых
        self.processing_users.add(user.id)
        
        try:
            # Отправляем сообщение о начале обработки
            processing_message = await update.message.reply_text(
                "🤖 *Обрабатываю ваш текст\\.\\.\\.*\n\nЭто может занять несколько секунд\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
            # Получаем настройки пользователя
            user_settings = self.db.get_user_settings(user.id)
            
            start_time = time.time()
            
            # Выполняем суммаризацию
            summary = await self.summarizer.summarize_text(
                text, 
                target_ratio=user_settings['summary_ratio'],
                language=user_settings['language_preference']
            )
            
            processing_time = time.time() - start_time
            
            if summary:
                # Сохраняем запрос в базу данных
                self.db.save_user_request(
                    user.id, 
                    user.username, 
                    len(text), 
                    len(summary)
                )
                
                # Вычисляем статистику
                compression_ratio = len(summary) / len(text)
                
                # Формируем ответ
                response_text = f"""📋 *Саммари готово\\!*

{summary}

📊 *Статистика:*
• Исходный текст: {len(text):,} символов
• Саммари: {len(summary):,} символов
• Сжатие: {compression_ratio:.1%}
• Время обработки: {processing_time:.1f}с"""
                
                # Удаляем сообщение о обработке
                try:
                    await processing_message.delete()
                except:
                    pass
                
                await update.message.reply_text(
                    response_text,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                
                logger.info(f"Успешно обработан текст пользователя {user.id}, сжатие: {compression_ratio:.1%}")
                
            else:
                # Удаляем сообщение о обработке
                try:
                    await processing_message.delete()
                except:
                    pass
                
                await update.message.reply_text(
                    "❌ *Ошибка при обработке текста\\!*\n\nПопробуйте позже или обратитесь к администратору\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                
                logger.error(f"Не удалось обработать текст пользователя {user.id}")
        
        except Exception as e:
            logger.error(f"Ошибка при обработке текста пользователя {user.id}: {str(e)}")
            
            # Удаляем сообщение о обработке
            try:
                await processing_message.delete()
            except:
                pass
            
            await update.message.reply_text(
                f"❌ *Произошла ошибка\\!*\n\nПожалуйста, попробуйте позже\\.\n\nОшибка: {str(e)[:100]}",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        
        finally:
            # Удаляем пользователя из списка обрабатываемых
            self.processing_users.discard(user.id)
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик ошибок"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ *Произошла непредвиденная ошибка\\!*\n\nПожалуйста, попробуйте позже\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except:
                pass
    
    async def setup_bot_commands(self, application: Application) -> None:
        """Настройка команд бота в меню Telegram"""
        commands = [
            BotCommand("start", "🤖 Запуск бота и приветствие"),
            BotCommand("help", "📖 Помощь по использованию"),
            BotCommand("stats", "📊 Статистика использования"),
            BotCommand("settings", "⚙️ Настройки суммаризации"),
        ]
        
        await application.bot.set_my_commands(commands)
        logger.info("Команды бота установлены")
    
    def run(self):
        """Запуск бота"""
        logger.info("Запуск Telegram Summarizer Bot")
        
        # Создаем приложение
        application = Application.builder().token(self.config.TELEGRAM_BOT_TOKEN).build()
        
        # Добавляем обработчики команд
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("stats", self.stats_command))
        application.add_handler(CommandHandler("settings", self.settings_command))
        
        # Обработчики настроек
        application.add_handler(CommandHandler("set_ratio_20", self.set_ratio_command))
        application.add_handler(CommandHandler("set_ratio_30", self.set_ratio_command))
        application.add_handler(CommandHandler("set_ratio_50", self.set_ratio_command))
        application.add_handler(CommandHandler("set_ratio_70", self.set_ratio_command))
        
        # Обработчик текстовых сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        
        # Обработчик ошибок
        application.add_error_handler(self.error_handler)
        
        # Настройка команд бота
        application.job_queue.run_once(
            lambda context: asyncio.create_task(self.setup_bot_commands(application)),
            when=1
        )
        
        # Запуск бота
        logger.info("Бот запущен и готов к работе!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Главная функция"""
    try:
        bot = TelegramSummarizerBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
