#!/usr/bin/env python3
"""
Deployment entry point - максимально простой для Cloud Run
"""
import os
import sys
import asyncio
import logging
import signal
from aiohttp import web
import json

# Настройка логирования
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

async def health_handler(request):
    """Обработчик health check"""
    return web.json_response({
        'status': 'healthy',
        'service': 'telegram-bot',
        'ready': True
    })

async def root_handler(request):
    """Корневой обработчик"""
    return web.Response(text='Telegram Bot - Ready for Cloud Run', status=200)

async def start_telegram_bot():
    """Запуск Telegram бота"""
    try:
        from simple_bot import SimpleTelegramBot
        bot = SimpleTelegramBot()
        await bot.run()
    except Exception as e:
        logger.error(f"Ошибка запуска Telegram бота: {e}")

async def create_app():
    """Создание aiohttp приложения"""
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/health', health_handler)
    app.router.add_get('/ready', health_handler)
    return app

async def init_server():
    """Инициализация сервера"""
    global app, site, bot_task
    
    port = int(os.getenv('PORT', 5000))
    
    # Создание приложения
    app = await create_app()
    
    # Создание и запуск HTTP сервера
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"HTTP сервер запущен на порту {port}")
    
    # Запуск Telegram бота в фоне
    bot_task = asyncio.create_task(start_telegram_bot())
    
    logger.info("Сервер готов к работе")
    
    return runner, site

def signal_handler(signum, frame):
    """Обработчик сигналов завершения"""
    logger.info(f"Получен сигнал {signum}, завершение работы...")
    asyncio.create_task(shutdown())

async def shutdown():
    """Graceful shutdown"""
    global app, site, bot_task
    
    logger.info("Завершение работы сервера...")
    
    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
    
    if site:
        await site.stop()
    
    logger.info("Сервер завершен")

async def main():
    """Главная функция"""
    # Установка обработчиков сигналов
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("🚀 Запуск Telegram Bot для Cloud Run")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Порт: {os.getenv('PORT', '5000')}")
    
    # Инициализация сервера
    runner, site = await init_server()
    
    try:
        # Ожидание завершения
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await shutdown()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())