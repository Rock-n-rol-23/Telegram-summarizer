#!/usr/bin/env python3
"""
Background Worker deployment entry point
This file is optimized for Reserved VM Background Worker deployment (no HTTP server needed)
"""

import os
import sys
import asyncio
import logging
from simple_bot import SimpleTelegramBot

# Force background worker deployment mode
os.environ['DEPLOYMENT_TYPE'] = 'background'

# Setup logging for background worker
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def main():
    """Main entry point for Background Worker deployment"""
    logger.info("=== Background Worker Deployment Starting ===")
    
    # Validate required environment variables
    if not os.getenv('TELEGRAM_BOT_TOKEN'):
        logger.error("TELEGRAM_BOT_TOKEN environment variable required")
        sys.exit(1)
    
    # Create and run bot
    try:
        bot = SimpleTelegramBot()
        logger.info("Starting Telegram bot in Background Worker mode...")
        logger.info("No HTTP server needed for Background Worker deployment")
        
        # Run bot with polling (no webhook needed)
        await bot.run()
        
    except KeyboardInterrupt:
        logger.info("Background Worker deployment interrupted by user")
    except Exception as e:
        logger.error(f"Background Worker deployment fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())