#!/usr/bin/env python3
"""
Flask-style entry point for maximum deployment compatibility
This ensures compatibility with various deployment platforms expecting app.py
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def create_flask_app():
    """Create a Flask app for compatibility (if needed)"""
    try:
        from flask import Flask, jsonify
        
        app = Flask(__name__)
        
        @app.route('/')
        def root():
            return "Telegram Summarization Bot - Flask Ready"
        
        @app.route('/health')
        def health():
            return jsonify({
                "status": "healthy",
                "service": "telegram-bot-flask",
                "ready": True
            })
        
        return app
    except ImportError:
        logger.warning("Flask not available, using aiohttp server")
        return None

async def main():
    """Main entry point - delegates to appropriate deployment mode"""
    logger.info("🚀 Starting via app.py entry point")
    
    # Force Cloud Run mode for app.py
    os.environ['DEPLOYMENT_TYPE'] = 'cloudrun'
    
    # Use the main entry point logic
    from main_entrypoint import main as main_entry
    main_entry()

# Flask app instance (for compatibility)
app = create_flask_app()

if __name__ == "__main__":
    # If run directly, use async mode
    asyncio.run(main())