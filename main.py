#!/usr/bin/env python3
"""
Production-ready entry point with gunicorn support and webhook mode
"""

import os
import sys
import logging
import threading
import asyncio
from flask import Flask, request, jsonify
from config import config
from utils.database import get_database_manager, close_database
from utils.ocr import get_ocr_info

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

@app.route('/')
@app.route('/health')
@app.route('/ready')
@app.route('/healthz')
def health_check():
    """Comprehensive health check"""
    try:
        # Database health check
        db = get_database_manager()
        db_status = db.health_check()
        
        # Configuration validation
        config_errors = config.validate()
        
        # OCR status
        ocr_info = get_ocr_info()
        
        status = {
            "status": "ok" if not config_errors else "degraded",
            "service": "telegram-summarization-bot",
            "version": "2.0.0",
            "database": db_status,
            "ocr": ocr_info,
            "configuration": config.get_summary(),
            "errors": config_errors
        }
        
        return jsonify(status), 200 if status["status"] == "ok" else 503
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 503

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    if not config.USE_WEBHOOK:
        return jsonify({"error": "Webhook not enabled"}), 404
    
    try:
        from simple_bot import SimpleTelegramBot
        
        # Get bot instance
        bot = SimpleTelegramBot()
        
        # Process update
        update = request.get_json()
        asyncio.run(bot.handle_update(update))
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

def run_telegram_bot():
    """Run Telegram bot in polling mode"""
    try:
        logger.info("Starting Telegram bot...")
        from simple_bot import SimpleTelegramBot
        
        bot = SimpleTelegramBot()
        asyncio.run(bot.run())
        
    except Exception as e:
        logger.error(f"Telegram bot error: {e}")
        sys.exit(1)

def cleanup():
    """Cleanup resources on shutdown"""
    try:
        close_database()
        logger.info("Cleanup completed")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def main():
    """Main entry point"""
    logger.info("🚀 Starting Telegram Summarization Bot v2.0")
    logger.info(f"Configuration: {config.get_summary()}")
    
    # Validate configuration
    errors = config.validate()
    if errors:
        logger.error(f"Configuration errors: {errors}")
        sys.exit(1)
    
    # Initialize database
    try:
        db = get_database_manager()
        db.create_tables()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        sys.exit(1)
    
    try:
        if config.USE_WEBHOOK:
            logger.info("Running in webhook mode")
            # In webhook mode, just run Flask app
            app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG_MODE)
        else:
            logger.info("Running in polling mode")
            
            if config.USE_GUNICORN:
                # Gunicorn handles Flask, we just run the bot
                run_telegram_bot()
            else:
                # Development mode - run both
                bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
                bot_thread.start()
                app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG_MODE)
                
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        sys.exit(1)
    finally:
        cleanup()

if __name__ == '__main__':
    main()

# For gunicorn
application = app