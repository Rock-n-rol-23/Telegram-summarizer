#!/usr/bin/env python3
"""
Готовый к деплою файл для Telegram бота
Этот файл специально создан для быстрого и успешного деплоя
"""

import os
import sys
import asyncio
import logging
from aiohttp import web
from simple_bot import SimpleTelegramBot

# Настройка логирования для деплоя
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class ReadyToDeploy:
    """Готовый к деплою сервер"""
    
    def __init__(self):
        self.bot = None
        self.app = None
        self.runner = None
        self.site = None
        self.bot_task = None
        self.shutdown_event = asyncio.Event()
        
    async def health_endpoint(self, request):
        """Основной health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "service": "telegram-bot",
            "ready": True,
            "message": "Готов к работе"
        }, status=200)
    
    async def root_endpoint(self, request):
        """Корневой endpoint"""
        return web.Response(
            text="Telegram Bot - Готов к работе",
            status=200,
            headers={'Content-Type': 'text/plain; charset=utf-8'}
        )
        
    async def setup_server(self):
        """Настройка HTTP сервера"""
        self.app = web.Application()
        
        # Все необходимые endpoints для деплоя
        self.app.router.add_get('/', self.root_endpoint)
        self.app.router.add_get('/health', self.health_endpoint)
        self.app.router.add_get('/ready', self.health_endpoint)
        self.app.router.add_get('/healthz', self.health_endpoint)
        self.app.router.add_get('/readiness', self.health_endpoint)
        
        return self.app
    
    async def start_server(self, port=5000):
        """Запуск HTTP сервера"""
        try:
            app = await self.setup_server()
            self.runner = web.AppRunner(app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, '0.0.0.0', port)
            await self.site.start()
            
            logger.info(f"✅ HTTP сервер запущен на порту {port}")
            logger.info(f"✅ Доступен по адресу: http://0.0.0.0:{port}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска сервера: {e}")
            return False
    
    async def start_bot(self):
        """Запуск Telegram бота"""
        try:
            self.bot = SimpleTelegramBot()
            logger.info("✅ Запускаю Telegram бота...")
            await self.bot.run()
        except Exception as e:
            logger.error(f"❌ Ошибка бота: {e}")
            self.shutdown_event.set()
    
    async def run(self):
        """Главная функция запуска"""
        try:
            port = int(os.getenv('PORT', 5000))
            logger.info("🚀 Запуск приложения для деплоя...")
            
            # Запускаем HTTP сервер
            if not await self.start_server(port):
                logger.error("❌ Не удалось запустить HTTP сервер")
                return
            
            # Запускаем бота
            self.bot_task = asyncio.create_task(self.start_bot())
            
            logger.info("✅ Приложение готово к деплою!")
            logger.info(f"✅ HTTP сервер работает на порту {port}")
            logger.info("✅ Telegram бот активен")
            
            # Ожидаем завершения
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Очистка ресурсов"""
        logger.info("🔄 Завершение работы...")
        
        if self.bot_task and not self.bot_task.done():
            self.bot_task.cancel()
            try:
                await self.bot_task
            except asyncio.CancelledError:
                pass
        
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        
        logger.info("✅ Завершение завершено")

async def main():
    """Главная точка входа для деплоя"""
    # Устанавливаем режим деплоя
    os.environ['DEPLOYMENT_TYPE'] = 'cloudrun'
    
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК ПРИЛОЖЕНИЯ ДЛЯ ДЕПЛОЯ")
    logger.info("=" * 50)
    
    # Проверяем обязательные переменные
    if not os.getenv('TELEGRAM_BOT_TOKEN'):
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден!")
        logger.error("Добавьте токен в переменные окружения")
        sys.exit(1)
    
    logger.info("✅ TELEGRAM_BOT_TOKEN найден")
    
    if os.getenv('GROQ_API_KEY'):
        logger.info("✅ GROQ_API_KEY найден")
    else:
        logger.info("ℹ️  GROQ_API_KEY не найден (необязательно)")
    
    # Создаем и запускаем сервер
    server = ReadyToDeploy()
    
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("⚠️  Прервано пользователем")
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())