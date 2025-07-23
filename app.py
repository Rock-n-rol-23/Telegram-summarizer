#!/usr/bin/env python3
"""
Flask-style app entry point for compatibility with various deployment platforms
This file provides a Flask-compatible entry point that can be used with different deployment systems
"""

import os
import asyncio
import threading
from flask import Flask, jsonify
from simple_bot import SimpleTelegramBot
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Global bot instance
bot_instance = None
bot_thread = None

def run_bot_async():
    """Run the bot in async mode"""
    global bot_instance
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        bot_instance = SimpleTelegramBot()
        logger.info("Starting Telegram bot in background thread...")
        loop.run_until_complete(bot_instance.run())
    except Exception as e:
        logger.error(f"Bot error: {e}")

@app.route('/')
def root():
    """Root endpoint for health checks"""
    return jsonify({
        "status": "healthy",
        "service": "telegram-bot-flask",
        "message": "Telegram Bot Server - OK"
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "telegram-bot-flask",
        "bot_running": bot_instance is not None,
        "ready": True
    })

@app.route('/ready')
def ready():
    """Readiness probe endpoint"""
    return jsonify({
        "status": "ready",
        "service": "telegram-bot-flask",
        "ready": True
    })

@app.route('/healthz')
def healthz():
    """Kubernetes-style health check"""
    return jsonify({
        "status": "healthy",
        "service": "telegram-bot-flask"
    })

@app.route('/readiness')
def readiness():
    """Kubernetes-style readiness check"""
    return jsonify({
        "status": "ready",
        "service": "telegram-bot-flask"
    })

if __name__ == '__main__':
    # Set deployment environment
    os.environ['DEPLOYMENT_TYPE'] = 'cloudrun'
    
    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot_async, daemon=True)
    bot_thread.start()
    
    # Get port from environment
    port = int(os.environ.get('PORT', 5000))
    
    logger.info(f"Starting Flask server on port {port}")
    logger.info("Telegram bot running in background")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False)