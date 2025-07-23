#!/usr/bin/env python3
"""
Flask-style app entry point for deployment compatibility
"""

import os
import sys
import asyncio
import threading
from pathlib import Path

# Add current directory to Python path  
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Import Flask for compatibility
try:
    from flask import Flask
    flask_app = Flask(__name__)
    
    @flask_app.route('/')
    def health_check():
        return "Telegram Summarization Bot - Running", 200
        
    @flask_app.route('/health')
    def health():
        return {"status": "healthy", "service": "telegram-bot"}, 200
        
except ImportError:
    flask_app = None

def run_telegram_bot():
    """Run the Telegram bot in background"""
    try:
        from cloudrun_optimized import main as cloudrun_main
        asyncio.run(cloudrun_main())
    except ImportError:
        from simple_bot import SimpleTelegramBot
        bot = SimpleTelegramBot()
        asyncio.run(bot.run())

def main():
    """Main entry point with Flask compatibility"""
    port = int(os.getenv('PORT', 5000))
    
    if flask_app:
        # Start Telegram bot in background thread
        bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
        bot_thread.start()
        
        # Run Flask app
        flask_app.run(host='0.0.0.0', port=port)
    else:
        # Run Telegram bot directly
        run_telegram_bot()

if __name__ == "__main__":
    main()