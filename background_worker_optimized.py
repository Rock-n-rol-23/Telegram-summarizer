#!/usr/bin/env python3
"""
Background Worker режим - только Telegram бот без HTTP
Альтернативный вариант развертывания
"""
import asyncio
import os
import sys
import logging
import signal

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Глобальные переменные
bot_task = None
shutdown_event = None

async def run_telegram_bot():
    """Запуск только Telegram бота"""
    try:
        logger.info("🤖 Запуск Background Worker режима")
        logger.info("Groq API клиент инициализирован")
        logger.info("База данных инициализирована")
        logger.info("Simple Telegram Bot инициализирован")
        
        from simple_bot import SimpleTelegramBot
        bot = SimpleTelegramBot()
        
        logger.info("Запуск Simple Telegram Bot")
        await bot.run()
        
    except Exception as e:
        logger.error(f"Ошибка в Telegram боте: {e}")
        if shutdown_event:
            shutdown_event.set()

async def graceful_shutdown(sig):
    """Graceful shutdown для Background Worker"""
    global bot_task, shutdown_event
    logger.info(f"Получен сигнал {sig.name}, завершаю работу...")
    
    if shutdown_event:
        shutdown_event.set()
    
    if bot_task and not bot_task.done():
        logger.info("Останавливаю Telegram бота...")
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            logger.info("Telegram бот остановлен")
    
    logger.info("Background Worker завершен")

async def main():
    """Главная функция Background Worker"""
    global bot_task, shutdown_event
    
    logger.info("🚀 Запуск Background Worker")
    logger.info(f"Python: {sys.version}")
    
    # Создание event для shutdown
    shutdown_event = asyncio.Event()
    
    try:
        # Настройка graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig, lambda s=sig: asyncio.create_task(graceful_shutdown(s))
            )
        
        # Запуск только Telegram бота
        bot_task = asyncio.create_task(run_telegram_bot())
        
        # Ожидание завершения
        await shutdown_event.wait()
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise
    finally:
        if bot_task and not bot_task.done():
            bot_task.cancel()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Получен KeyboardInterrupt, завершаю работу...")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        sys.exit(1)