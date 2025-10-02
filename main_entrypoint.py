#!/usr/bin/env python3
"""
Главный entry point для развертывания - исправляет проблему $file variable
"""
import threading
import os
import sys
import logging
import signal
import asyncio
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

# Глобальная переменная для хранения инстанса бота
bot_instance = None
bot_loop = None

def handle_shutdown_signal(signum, frame):
    """Обработчик сигналов завершения (SIGINT, SIGTERM)"""
    logger.info(f"Получен сигнал {signum}, инициируем graceful shutdown...")
    if bot_instance and bot_loop:
        # Останавливаем event loop бота
        bot_loop.stop()
    sys.exit(0)

def run_telegram_bot():
    """Функция для запуска бота в отдельном потоке"""
    global bot_instance, bot_loop
    try:
        logger.info("Запуск Telegram бота...")

        # Сначала настраиваем логирование для simple_bot
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )

        from simple_bot import SimpleTelegramBot
        bot_instance = SimpleTelegramBot()

        # Создаем новый event loop для потока
        bot_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(bot_loop)

        # Запуск бота в блокирующем режиме
        bot_loop.run_until_complete(bot_instance.run())

    except KeyboardInterrupt:
        logger.info("Получен KeyboardInterrupt в потоке бота")
    except Exception as e:
        logger.error(f"Ошибка запуска Telegram бота: {e}")
        import traceback
        logger.error(f"Детали ошибки: {traceback.format_exc()}")

if __name__ == '__main__':
    logger.info("🚀 Запуск главного entry point")
    logger.info(f"Python: {sys.version}")

    # Регистрация обработчиков сигналов для graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    logger.info("Обработчики сигналов (SIGINT, SIGTERM) зарегистрированы")

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

    except KeyboardInterrupt:
        logger.info("Получен KeyboardInterrupt, завершение работы...")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)
    finally:
        logger.info("Главный процесс завершен")