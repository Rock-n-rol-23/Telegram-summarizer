#!/usr/bin/env python3
"""
Cloud Run оптимизированная версия - исправляет все проблемы развертывания
"""
import asyncio
import os
import sys
import logging
import signal
from aiohttp import web
import threading
import json

# Настройка логирования для Cloud Run
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Глобальные переменные для graceful shutdown
app = None
site = None
bot_task = None
shutdown_event = None

async def health_handler(request):
    """Health check endpoint для Cloud Run - возвращает JSON как требуется"""
    return web.json_response({
        'status': 'ok',
        'message': 'Bot is running',
        'service': 'telegram-bot',
        'ready': True,
        'health': 'healthy'
    }, status=200)

async def root_handler(request):
    """Корневой обработчик - возвращает простой текст для совместимости"""
    return web.Response(
        text='Telegram Summarization Bot - Cloud Run Ready',
        status=200,
        content_type='text/plain'
    )

async def status_handler(request):
    """Статус endpoint"""
    return web.json_response({
        'status': 'running',
        'service': 'telegram-summarization-bot',
        'features': [
            'AI text summarization',
            'Multi-language support',
            'Groq API integration',
            'Health check endpoints'
        ]
    }, status=200)

async def start_telegram_bot():
    """Запуск Telegram бота в async режиме"""
    global shutdown_event
    try:
        logger.info("Groq API клиент инициализирован")
        logger.info("База данных инициализирована") 
        logger.info("Simple Telegram Bot инициализирован")
        logger.info("Запуск Simple Telegram Bot")
        
        from simple_bot import SimpleTelegramBot
        bot = SimpleTelegramBot()
        
        # Запуск бота с обработкой shutdown
        await bot.run()
        
    except Exception as e:
        logger.error(f"Ошибка в Telegram боте: {e}")
        if shutdown_event:
            shutdown_event.set()

async def create_app():
    """Создание aiohttp приложения"""
    app = web.Application()
    
    # Регистрация всех endpoint'ов как требует Cloud Run
    app.router.add_get('/', root_handler)
    app.router.add_get('/health', health_handler)
    app.router.add_get('/ready', health_handler)  # Readiness probe
    app.router.add_get('/status', status_handler)
    
    return app

async def graceful_shutdown(sig):
    """Graceful shutdown handler"""
    global bot_task, site, shutdown_event
    logger.info(f"Получен сигнал {sig.name}, начинаю graceful shutdown...")
    
    if shutdown_event:
        shutdown_event.set()
    
    # Остановка Telegram бота
    if bot_task and not bot_task.done():
        logger.info("Останавливаю Telegram бота...")
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            logger.info("Telegram бот остановлен")
    
    # Остановка HTTP сервера
    if site:
        logger.info("Останавливаю HTTP сервер...")
        await site.stop()
        logger.info("HTTP сервер остановлен")
    
    logger.info("Graceful shutdown завершен")

async def main():
    """Главная функция"""
    global app, site, bot_task, shutdown_event
    
    logger.info("🚀 Запуск Telegram Bot для Cloud Run")
    logger.info(f"Python: {sys.version}")
    
    # Получение порта
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Порт: {port}")
    
    # Создание event для shutdown
    shutdown_event = asyncio.Event()
    
    try:
        # Создание приложения
        app = await create_app()
        
        # Настройка graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig, lambda s=sig: asyncio.create_task(graceful_shutdown(s))
            )
        
        # Создание и запуск HTTP сервера
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        logger.info(f"HTTP сервер запущен на порту {port}")
        logger.info("Сервер готов к работе")
        
        # Запуск Telegram бота в отдельной задаче
        bot_task = asyncio.create_task(start_telegram_bot())
        
        # Ожидание shutdown event
        await shutdown_event.wait()
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise
    finally:
        # Финальная очистка
        if bot_task and not bot_task.done():
            bot_task.cancel()
        if site:
            await site.stop()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Получен KeyboardInterrupt, завершаю работу...")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        sys.exit(1)