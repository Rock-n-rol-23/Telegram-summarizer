#!/usr/bin/env python3
"""
Background Worker Optimized Entry Point
For Reserved VM Background Worker deployment (no HTTP server required)
"""

import os
import sys
import asyncio
import logging
import signal
from simple_bot import SimpleTelegramBot

# Configure logging for Background Worker
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class BackgroundTelegramBot:
    """Optimized Telegram Bot for Background Worker deployment"""
    
    def __init__(self):
        self.bot = None
        self.shutdown_event = asyncio.Event()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.shutdown_event.set()
    
    async def run(self):
        """Main entry point for Background Worker deployment"""
        try:
            logger.info("=" * 60)
            logger.info("🚀 BACKGROUND WORKER TELEGRAM BOT STARTING")
            logger.info("=" * 60)
            
            # Validate required environment variables
            if not os.getenv('TELEGRAM_BOT_TOKEN'):
                logger.error("❌ TELEGRAM_BOT_TOKEN environment variable is required")
                sys.exit(1)
            
            logger.info("✅ TELEGRAM_BOT_TOKEN found")
            
            if os.getenv('GROQ_API_KEY'):
                logger.info("✅ GROQ_API_KEY found - AI summarization enabled")
            else:
                logger.warning("⚠️  GROQ_API_KEY not found - using fallback summarization")
            
            # Initialize and start Telegram bot
            logger.info("🚀 Initializing Telegram bot...")
            self.bot = SimpleTelegramBot()
            
            logger.info("🚀 Starting Telegram bot polling loop...")
            logger.info("✅ Background Worker deployment ready")
            logger.info("✅ Bot is now listening for messages...")
            
            # Start the bot and wait for shutdown
            bot_task = asyncio.create_task(self.bot.run())
            shutdown_task = asyncio.create_task(self.shutdown_event.wait())
            
            # Wait for either bot completion or shutdown signal
            done, pending = await asyncio.wait(
                [bot_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
        except KeyboardInterrupt:
            logger.info("⚠️  Service interrupted by user")
        except Exception as e:
            logger.error(f"❌ Critical error: {e}")
            sys.exit(1)
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup resources gracefully"""
        logger.info("🔄 Starting graceful shutdown...")
        
        if self.bot:
            logger.info("🔄 Stopping Telegram bot...")
            # The bot cleanup will be handled by the SimpleTelegramBot class
            logger.info("✅ Telegram bot stopped")
        
        logger.info("✅ Graceful shutdown completed")

async def main():
    """Main entry point"""
    # Ensure Background Worker deployment mode
    os.environ['DEPLOYMENT_TYPE'] = 'background'
    
    # Create and run the Background Worker optimized bot
    background_bot = BackgroundTelegramBot()
    await background_bot.run()

if __name__ == "__main__":
    # Run the Background Worker optimized service
    asyncio.run(main())