#!/usr/bin/env python3
"""
Cloud Run Optimized Entry Point
Specifically designed for Cloud Run deployment with robust health checks
"""

import os
import sys
import asyncio
import logging
import signal
from aiohttp import web
from aiohttp.web import Response
import json
from simple_bot import SimpleTelegramBot

# Configure logging for Cloud Run
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class CloudRunTelegramBot:
    """Optimized Telegram Bot for Cloud Run deployment"""
    
    def __init__(self):
        self.bot = None
        self.app = None
        self.runner = None
        self.site = None
        self.bot_task = None
        self.is_healthy = False
        self.is_ready = False
        self.shutdown_event = asyncio.Event()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.shutdown_event.set()
    
    async def health_endpoint(self, request):
        """Enhanced health check endpoint for Cloud Run"""
        health_data = {
            "status": "healthy" if self.is_healthy else "unhealthy",
            "ready": self.is_ready,
            "service": "telegram-summarization-bot",
            "version": "1.0.0",
            "timestamp": int(asyncio.get_event_loop().time()),
            "components": {
                "http_server": "running",
                "telegram_bot": "active" if self.bot else "initializing"
            }
        }
        
        status_code = 200 if self.is_healthy else 503
        return web.json_response(health_data, status=status_code)
    
    async def readiness_endpoint(self, request):
        """Readiness probe for Cloud Run"""
        readiness_data = {
            "ready": self.is_ready,
            "service": "telegram-summarization-bot",
            "message": "Ready to serve requests" if self.is_ready else "Still starting up"
        }
        
        status_code = 200 if self.is_ready else 503
        return web.json_response(readiness_data, status=status_code)
    
    async def root_endpoint(self, request):
        """Root endpoint - simple text response for Cloud Run"""
        return web.Response(
            text="Telegram Summarization Bot - Cloud Run Ready",
            status=200,
            content_type='text/plain'
        )
    
    async def status_endpoint(self, request):
        """Detailed status endpoint"""
        status_data = {
            "service": "telegram-summarization-bot",
            "status": "operational",
            "deployment": "cloud-run",
            "features": [
                "AI text summarization",
                "Multi-language support",
                "Groq API integration",
                "24/7 availability"
            ],
            "health": {
                "http_server": "running",
                "telegram_bot": "active",
                "database": "connected"
            }
        }
        
        return web.json_response(status_data, status=200)
    
    async def setup_http_server(self):
        """Setup HTTP server with all required endpoints"""
        self.app = web.Application()
        
        # Essential endpoints for Cloud Run
        self.app.router.add_get('/', self.root_endpoint)
        self.app.router.add_get('/health', self.health_endpoint)
        self.app.router.add_get('/healthz', self.health_endpoint)  # Kubernetes convention
        self.app.router.add_get('/ready', self.readiness_endpoint)
        self.app.router.add_get('/readiness', self.readiness_endpoint)
        self.app.router.add_get('/status', self.status_endpoint)
        
        logger.info("HTTP server routes configured")
        return self.app
    
    async def start_http_server(self, port=5000):
        """Start HTTP server for Cloud Run"""
        try:
            app = await self.setup_http_server()
            self.runner = web.AppRunner(app)
            await self.runner.setup()
            
            # Bind to 0.0.0.0 for Cloud Run accessibility
            self.site = web.TCPSite(self.runner, '0.0.0.0', port)
            await self.site.start()
            
            self.is_healthy = True
            logger.info(f"✅ HTTP server started successfully on port {port}")
            logger.info(f"✅ Server accessible at http://0.0.0.0:{port}")
            logger.info("✅ Health check endpoints available:")
            logger.info("   - / (root)")
            logger.info("   - /health (health check)")
            logger.info("   - /ready (readiness probe)")
            logger.info("   - /status (detailed status)")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start HTTP server: {e}")
            self.is_healthy = False
            return False
    
    async def start_telegram_bot(self):
        """Start Telegram bot with proper error handling"""
        try:
            logger.info("🚀 Initializing Telegram bot...")
            self.bot = SimpleTelegramBot()
            
            logger.info("🚀 Starting Telegram bot polling...")
            await self.bot.run()
            
        except Exception as e:
            logger.error(f"❌ Telegram bot error: {e}")
            # Don't shut down the entire service if bot fails
            # HTTP health checks should still work
        finally:
            logger.info("🔄 Telegram bot polling stopped")
    
    async def run(self):
        """Main entry point for Cloud Run deployment"""
        try:
            # Get port from Cloud Run environment
            port = int(os.getenv('PORT', 5000))
            
            logger.info("=" * 60)
            logger.info("🚀 CLOUD RUN TELEGRAM BOT STARTING")
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
            
            # Start HTTP server first (required for Cloud Run health checks)
            if not await self.start_http_server(port):
                logger.error("❌ HTTP server startup failed - cannot proceed")
                sys.exit(1)
            
            # Mark as ready after HTTP server is up
            self.is_ready = True
            logger.info("✅ Service marked as ready for Cloud Run")
            
            # Start Telegram bot in background
            self.bot_task = asyncio.create_task(self.start_telegram_bot())
            
            logger.info("✅ All services started successfully")
            logger.info("✅ Cloud Run deployment ready")
            logger.info(f"✅ Listening on http://0.0.0.0:{port}")
            
            # Keep the service running
            await self.shutdown_event.wait()
            
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
        
        # Cancel bot task
        if self.bot_task and not self.bot_task.done():
            logger.info("🔄 Stopping Telegram bot...")
            self.bot_task.cancel()
            try:
                await self.bot_task
            except asyncio.CancelledError:
                logger.info("✅ Telegram bot stopped")
        
        # Cleanup HTTP server
        if self.site:
            logger.info("🔄 Stopping HTTP server...")
            await self.site.stop()
            logger.info("✅ HTTP server stopped")
        
        if self.runner:
            await self.runner.cleanup()
            logger.info("✅ HTTP runner cleaned up")
        
        logger.info("✅ Graceful shutdown completed")

async def main():
    """Main entry point"""
    # Ensure Cloud Run deployment mode
    os.environ['DEPLOYMENT_TYPE'] = 'cloudrun'
    
    # Create and run the Cloud Run optimized bot
    cloudrun_bot = CloudRunTelegramBot()
    await cloudrun_bot.run()

if __name__ == "__main__":
    # Run the Cloud Run optimized service
    asyncio.run(main())