#!/usr/bin/env python3
"""
Главный entry point для развертывания - исправляет проблему $file variable
"""
import threading
import os
import sys
import logging
from flask import Flask, jsonify

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# HTTP сервер для health check
app = Flask(__name__)

@app.route('/')
@app.route('/health')
@app.route('/ready')
@app.route('/healthz')
def health_check():
    """Health check endpoint для Cloud Run"""
    return jsonify({
        "status": "ok", 
        "message": "Telegram Summarization Bot - Cloud Run Ready",
        "service": "telegram-bot",
        "ready": True,
        "health": "healthy"
    }), 200

@app.route('/status')
def status():
    """Статус сервиса"""
    return jsonify({
        "status": "running",
        "service": "telegram-summarization-bot",
        "features": [
            "AI text summarization",
            "Multi-language support", 
            "Groq API integration",
            "Fallback summarization"
        ]
    }), 200

def run_telegram_bot():
    """Функция для запуска бота в отдельном потоке"""
    try:
        logger.info("Запуск Telegram бота...")
        from simple_bot import SimpleTelegramBot
        bot = SimpleTelegramBot()
        
        # Запуск бота в блокирующем режиме
        import asyncio
        asyncio.run(bot.run())
        
    except Exception as e:
        logger.error(f"Ошибка запуска Telegram бота: {e}")
        sys.exit(1)

if __name__ == '__main__':
    logger.info("🚀 Запуск главного entry point")
    logger.info(f"Python: {sys.version}")
    
    # Получение порта
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Порт: {port}")
    
    try:
        # Запуск бота в отдельном потоке
        logger.info("Создание потока для Telegram бота...")
        bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
        bot_thread.start()
        logger.info("Поток Telegram бота запущен")
        
        # Запуск HTTP сервера в главном потоке
        logger.info(f"HTTP сервер запускается на 0.0.0.0:{port}")
        app.run(host='0.0.0.0', port=port, debug=False)
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)