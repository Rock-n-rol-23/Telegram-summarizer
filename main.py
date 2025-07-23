#!/usr/bin/env python3
"""
Main entry point for the Telegram Summarization Bot
This file serves as the primary entry point for all deployment scenarios.
It automatically detects the deployment environment and starts the appropriate service.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def detect_deployment_mode():
    """Detect deployment environment and return appropriate mode"""
    # Check for Cloud Run environment
    if os.getenv('K_SERVICE') or os.getenv('REPLIT_DEPLOYMENT'):
        return 'cloudrun'
    
    # Check for explicit deployment type
    deployment_type = os.getenv('DEPLOYMENT_TYPE', '').lower()
    if deployment_type in ['background', 'worker']:
        return 'background'
    elif deployment_type in ['cloudrun', 'http', 'server']:
        return 'cloudrun'
    
    # Default to cloudrun for production deployment
    return 'cloudrun'

async def main():
    """Main entry point"""
    try:
        # Log startup information
        logger.info("=== Telegram Summarization Bot Starting ===")
        logger.info(f"Python: {sys.version}")
        logger.info(f"Working Directory: {os.getcwd()}")
        logger.info(f"Port: {os.getenv('PORT', '5000')}")
        
        # Detect deployment mode
        mode = detect_deployment_mode()
        logger.info(f"Deployment Mode: {mode}")
        
        if mode == 'background':
            # Background worker mode - bot only
            logger.info("Starting in Background Worker mode...")
            from simple_bot import SimpleTelegramBot
            bot = SimpleTelegramBot()
            await bot.run()
        else:
            # Cloud Run mode - HTTP server + bot
            logger.info("Starting in Cloud Run mode with HTTP server...")
            from main_server import main as server_main
            await server_main()
            
    except ImportError as e:
        logger.error(f"Import error: {e}")
        logger.error("Please ensure all dependencies are installed")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Startup error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)