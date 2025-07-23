#!/usr/bin/env python3
"""
Explicit Cloud Run deployment entry point
This file is specifically designed for Cloud Run deployment with comprehensive health checks
"""

import os
import sys
import asyncio
import logging
from aiohttp import web
from simple_bot import SimpleTelegramBot

# Force Cloud Run deployment mode
os.environ['DEPLOYMENT_TYPE'] = 'cloudrun'

# Setup logging for Cloud Run
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class CloudRunDeploymentServer:
    """Optimized server for Cloud Run deployment"""
    
    def __init__(self):
        self.bot = None
        self.app = None 
        self.runner = None
        self.site = None
        self.bot_task = None
        self.shutdown_event = asyncio.Event()
        
    async def root_handler(self, request):
        """Root endpoint - required for Cloud Run health checks"""
        return web.Response(
            text="Telegram Bot - Healthy", 
            status=200,
            headers={'Content-Type': 'text/plain'}
        )
    
    async def health_handler(self, request):
        """Health check endpoint for Cloud Run"""
        return web.json_response({
            "status": "healthy",
            "service": "telegram-bot",
            "deployment": "cloudrun",
            "ready": True
        }, status=200)
    
    async def ready_handler(self, request):
        """Readiness check endpoint"""
        return web.json_response({
            "status": "ready", 
            "service": "telegram-bot",
            "deployment": "cloudrun",
            "ready": True
        }, status=200)
    
    async def healthz_handler(self, request):
        """Kubernetes-style health check"""
        return web.json_response({
            "status": "healthy",
            "service": "telegram-bot"
        }, status=200)
        
    async def readiness_handler(self, request):
        """Kubernetes-style readiness check"""
        return web.json_response({
            "status": "ready",
            "service": "telegram-bot"
        }, status=200)
        
    async def setup_app(self):
        """Setup web application for Cloud Run"""
        self.app = web.Application()
        
        # Essential routes for Cloud Run deployment
        self.app.router.add_get('/', self.root_handler)
        self.app.router.add_get('/health', self.health_handler)
        self.app.router.add_get('/ready', self.ready_handler)
        self.app.router.add_get('/healthz', self.healthz_handler)
        self.app.router.add_get('/readiness', self.readiness_handler)
        
        return self.app
        
    async def start_server(self, port=5000):
        """Start HTTP server for Cloud Run"""
        try:
            app = await self.setup_app()
            self.runner = web.AppRunner(app)
            await self.runner.setup()
            
            # Bind to 0.0.0.0 for Cloud Run accessibility
            self.site = web.TCPSite(self.runner, '0.0.0.0', port)
            await self.site.start()
            
            logger.info(f"Cloud Run HTTP server started on port {port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Cloud Run server: {e}")
            return False
    
    async def start_bot(self):
        """Start Telegram bot"""
        try:
            self.bot = SimpleTelegramBot()
            logger.info("Starting Telegram bot for Cloud Run deployment...")
            await self.bot.run()
        except Exception as e:
            logger.error(f"Bot error in Cloud Run deployment: {e}")
            self.shutdown_event.set()
    
    async def run(self):
        """Main deployment runner"""
        try:
            # Get port from Cloud Run environment
            port = int(os.getenv('PORT', 5000))
            logger.info(f"Cloud Run deployment starting on port {port}")
            
            # Start HTTP server first (critical for Cloud Run health checks)
            if not await self.start_server(port):
                logger.error("Cloud Run deployment failed - HTTP server start failed")
                return
            
            logger.info("Cloud Run HTTP server ready")
            logger.info(f"Health checks available at http://0.0.0.0:{port}/health")
            
            # Start Telegram bot in parallel
            self.bot_task = asyncio.create_task(self.start_bot())
            
            logger.info("Cloud Run deployment successful - both HTTP server and bot running")
            
            # Keep running until shutdown signal
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Cloud Run deployment error: {e}")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup resources for Cloud Run shutdown"""
        logger.info("Cloud Run deployment shutting down...")
        
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
        
        logger.info("Cloud Run deployment shutdown complete")

async def main():
    """Main entry point for Cloud Run deployment"""
    logger.info("=== Cloud Run Deployment Starting ===")
    
    # Validate required environment variables
    if not os.getenv('TELEGRAM_BOT_TOKEN'):
        logger.error("TELEGRAM_BOT_TOKEN environment variable required")
        sys.exit(1)
    
    server = CloudRunDeploymentServer()
    
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("Cloud Run deployment interrupted by user")
    except Exception as e:
        logger.error(f"Cloud Run deployment fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())