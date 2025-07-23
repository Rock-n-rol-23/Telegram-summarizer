#!/usr/bin/env python3
"""
Main server file for Telegram bot with HTTP health check endpoint
This file combines the Telegram bot functionality with an HTTP server for Cloud Run deployment
"""

import asyncio
import logging
import sys
import os
import threading
from aiohttp import web
from aiohttp.web import Response
import signal
from simple_bot import SimpleTelegramBot

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TelegramBotServer:
    """Сервер, который запускает Telegram бота и HTTP сервер для health checks"""
    
    def __init__(self):
        self.bot = None
        self.app = None
        self.runner = None
        self.site = None
        self.bot_task = None
        self.shutdown_event = asyncio.Event()
        
    async def health_check(self, request):
        """Health check endpoint для Cloud Run"""
        try:
            # Проверяем, что бот активен
            if self.bot and self.bot_task and not self.bot_task.done():
                return web.json_response({
                    "status": "healthy", 
                    "service": "telegram-bot",
                    "timestamp": asyncio.get_event_loop().time(),
                    "ready": True
                })
            else:
                return web.json_response({
                    "status": "unhealthy", 
                    "service": "telegram-bot", 
                    "reason": "bot not running",
                    "ready": False
                }, status=503)
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return web.json_response({
                "status": "unhealthy", 
                "service": "telegram-bot", 
                "error": str(e),
                "ready": False
            }, status=503)
    
    async def status_endpoint(self, request):
        """Status endpoint с дополнительной информацией"""
        try:
            status_info = {
                "service": "telegram-bot",
                "version": "1.0.0",
                "status": "running" if self.bot else "stopped"
            }
            
            if self.bot:
                status_info["bot_id"] = getattr(self.bot, 'bot_id', 'unknown')
                status_info["uptime"] = "running"
            
            return web.json_response(status_info)
        except Exception as e:
            logger.error(f"Status endpoint error: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def ping_endpoint(self, request):
        """Simple ping endpoint for deployment verification"""
        return web.json_response({"message": "pong", "service": "telegram-bot"})
    
    async def setup_http_server(self):
        """Настройка HTTP сервера для health checks"""
        self.app = web.Application()
        
        # Добавляем маршруты
        self.app.router.add_get('/', self.health_check)
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/ready', self.health_check)
        self.app.router.add_get('/status', self.status_endpoint)
        self.app.router.add_get('/ping', self.ping_endpoint)
        
        # Настройка CORS для всех маршрутов
        self.app.router.add_options('/{path:.*}', self.handle_options)
        
        return self.app
    
    async def handle_options(self, request):
        """Обработка OPTIONS запросов для CORS"""
        return web.Response(
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
        )
    
    async def start_http_server(self, port=5000):
        """Запуск HTTP сервера"""
        try:
            app = await self.setup_http_server()
            self.runner = web.AppRunner(app)
            await self.runner.setup()
            
            # Используем 0.0.0.0 для доступности извне
            self.site = web.TCPSite(self.runner, '0.0.0.0', port)
            await self.site.start()
            
            logger.info(f"HTTP сервер запущен на порту {port}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска HTTP сервера: {e}")
            return False
    
    async def start_telegram_bot(self):
        """Запуск Telegram бота"""
        try:
            self.bot = SimpleTelegramBot()
            logger.info("Запуск Telegram бота...")
            await self.bot.run()
        except Exception as e:
            logger.error(f"Ошибка запуска Telegram бота: {e}")
            self.shutdown_event.set()
    
    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("Начинается завершение работы...")
        
        # Останавливаем бота
        if self.bot_task and not self.bot_task.done():
            self.bot_task.cancel()
            try:
                await self.bot_task
            except asyncio.CancelledError:
                pass
        
        # Останавливаем HTTP сервер
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        
        logger.info("Завершение работы завершено")
    
    async def run(self):
        """Главный метод запуска сервера"""
        try:
            # Определяем порт из переменной окружения
            port = int(os.getenv('PORT', 5000))
            
            # Запускаем HTTP сервер
            if not await self.start_http_server(port):
                logger.error("Не удалось запустить HTTP сервер")
                return
            
            # Запускаем Telegram бота в отдельной задаче
            self.bot_task = asyncio.create_task(self.start_telegram_bot())
            
            logger.info("Сервер успешно запущен")
            logger.info(f"HTTP сервер доступен на порту {port}")
            logger.info("Telegram бот активен")
            
            # Ожидаем сигнала завершения
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Критическая ошибка сервера: {e}")
            self.shutdown_event.set()
        finally:
            await self.shutdown()

# Глобальная переменная для сервера
_server_instance = None

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    logger.info(f"Получен сигнал {signum}, начинается завершение...")
    # Установим event для завершения
    if _server_instance:
        _server_instance.shutdown_event.set()

async def main():
    """Главная функция"""
    global _server_instance
    server = TelegramBotServer()
    _server_instance = server  # Для доступа из signal_handler
    
    # Настройка обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания")
        server.shutdown_event.set()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())