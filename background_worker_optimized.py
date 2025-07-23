#!/usr/bin/env python3
"""
Background Worker Entry Point for Reserved VM Deployment
This file runs only the Telegram bot without HTTP server (for Background Worker deployments)
"""

import os
import sys
import asyncio
import logging
import signal
from simple_bot import SimpleTelegramBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class BackgroundWorkerBot:
    """Background Worker Telegram Bot (no HTTP server)"""
    
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
        """Run the background worker bot"""
        try:
            logger.info("============================================================")
            logger.info("🤖 BACKGROUND WORKER TELEGRAM BOT STARTING")
            logger.info("============================================================")
            
            # Verify environment
            if not os.getenv('TELEGRAM_BOT_TOKEN'):
                logger.error("❌ TELEGRAM_BOT_TOKEN not found")
                sys.exit(1)
            
            logger.info("✅ TELEGRAM_BOT_TOKEN found")
            
            if os.getenv('GROQ_API_KEY'):
                logger.info("✅ GROQ_API_KEY found - AI summarization enabled")
            else:
                logger.info("⚠️ GROQ_API_KEY not found - using fallback summarization")
            
            # Set deployment type
            os.environ['DEPLOYMENT_TYPE'] = 'background'
            
            # Initialize and start bot
            self.bot = SimpleTelegramBot()
            logger.info("🚀 Initializing Telegram bot...")
            
            # Start bot
            logger.info("🚀 Starting Telegram bot polling...")
            bot_task = asyncio.create_task(self.bot.run())
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
            
            # Graceful shutdown
            logger.info("🛑 Shutdown signal received, stopping bot...")
            bot_task.cancel()
            
            try:
                await bot_task
            except asyncio.CancelledError:
                logger.info("✅ Bot task cancelled successfully")
            
        except Exception as e:
            logger.error(f"❌ Fatal error in background worker: {e}")
            sys.exit(1)
        finally:
            logger.info("🏁 Background worker shutdown complete")

async def main():
    """Main entry point for background worker"""
    worker = BackgroundWorkerBot()
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())