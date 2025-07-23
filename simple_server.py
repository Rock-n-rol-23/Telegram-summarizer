#!/usr/bin/env python3
"""
Simplified server for Cloud Run deployment
This file provides a minimal HTTP server with health checks for Cloud Run deployment
"""

import asyncio
import logging
import sys
import os
from aiohttp import web
from aiohttp.web import Response
import signal
from simple_bot import SimpleTelegramBot

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class SimpleTelegramServer:
    """Simplified server for Cloud Run deployment"""
    
    def __init__(self):
        self.bot = None
        self.app = None
        self.runner = None
        self.site = None
        self.bot_task = None
        self.shutdown_event = asyncio.Event()
        
    async def root_handler(self, request):
        """Root endpoint that returns simple OK response"""
        return web.Response(
            text="Telegram Bot Server - OK",
            status=200,
            content_type='text/plain'
        )
    
    async def health_check(self, request):
        """Health check endpoint for Cloud Run"""
        return web.json_response({
            "status": "healthy",
            "service": "telegram-bot",
            "ready": True
        })
    
    async def setup_app(self):
        """Setup web application with minimal routes"""
        self.app = web.Application()
        
        # Add essential routes for Cloud Run
        self.app.router.add_get('/', self.root_handler)
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/ready', self.health_check)
        
        return self.app
    
    async def start_server(self, port=5000):
        """Start HTTP server"""
        try:
            app = await self.setup_app()
            self.runner = web.AppRunner(app)
            await self.runner.setup()
            
            # Use 0.0.0.0 for external access
            self.site = web.TCPSite(self.runner, '0.0.0.0', port)
            await self.site.start()
            
            logger.info(f"HTTP server started on port {port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start HTTP server: {e}")
            return False
    
    async def start_bot(self):
        """Start Telegram bot"""
        try:
            self.bot = SimpleTelegramBot()
            logger.info("Starting Telegram bot...")
            await self.bot.run()
        except Exception as e:
            logger.error(f"Bot error: {e}")
            self.shutdown_event.set()
    
    async def run(self):
        """Main run method"""
        try:
            # Get port from environment
            port = int(os.getenv('PORT', 5000))
            
            # Start HTTP server first
            if not await self.start_server(port):
                logger.error("Failed to start HTTP server")
                return
            
            logger.info("Server started successfully")
            logger.info(f"Listening on http://0.0.0.0:{port}")
            
            # Start bot in background
            self.bot_task = asyncio.create_task(self.start_bot())
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Shutting down...")
        
        if self.bot_task and not self.bot_task.done():
            self.bot_task.cancel()
            try:
                await self.bot_task
            except asyncio.CancelledError:
                pass
        
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        
        logger.info("Shutdown complete")

# Global server instance
_server = None

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    if _server:
        _server.shutdown_event.set()

async def main():
    """Main entry point"""
    global _server
    
    # Set deployment mode
    os.environ['DEPLOYMENT_TYPE'] = 'cloudrun'
    
    _server = SimpleTelegramServer()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await _server.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())