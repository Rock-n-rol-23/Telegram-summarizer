#!/usr/bin/env python3
"""
Flask-style compatibility entry point
Простой Flask сервер с threading как в инструкции
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
def health_check():
    """Health check endpoint точно как в инструкции"""
    return jsonify({"status": "ok", "message": "Bot is running"}), 200

@app.route('/ready')
def ready_check():
    """Readiness probe"""
    return jsonify({"status": "ready", "service": "telegram-bot"}), 200

# Функция для запуска бота
def run_telegram_bot():
    """Запуск бота в отдельном потоке как в инструкции"""
    try:
        logger.info("Запуск Telegram бота в потоке...")
        
        # Импорт и создание бота
        from simple_bot import SimpleTelegramBot
        bot = SimpleTelegramBot()
        
        # Запуск в async режиме
        import asyncio
        asyncio.run(bot.run())
        
    except Exception as e:
        logger.error(f"Ошибка в потоке Telegram бота: {e}")

if __name__ == '__main__':
    logger.info("🚀 Запуск Flask приложения")
    logger.info(f"Python: {sys.version}")
    
    # Запуск бота в отдельном потоке
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    logger.info("Поток Telegram бота запущен")
    
    # Запуск HTTP сервера
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"HTTP сервер запускается на 0.0.0.0:{port}")
    
    app.run(host='0.0.0.0', port=port, debug=False)