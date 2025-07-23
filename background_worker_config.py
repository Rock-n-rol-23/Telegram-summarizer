#!/usr/bin/env python3
"""
Background Worker Configuration for Reserved VM Deployment
Alternative deployment option for Telegram bot without HTTP server
"""

import os
import sys
import asyncio
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def configure_background_worker():
    """Configure environment for background worker deployment"""
    logger.info("🔧 Configuring Reserved VM Background Worker deployment")
    
    # Set deployment type to background worker
    os.environ['DEPLOYMENT_TYPE'] = 'background'
    
    # Log configuration
    logger.info("✅ DEPLOYMENT_TYPE set to 'background'")
    logger.info("✅ Background Worker mode: Telegram bot only (no HTTP server)")
    logger.info("✅ Suitable for Reserved VM deployment")
    
    return True

async def main():
    """Main entry point for background worker"""
    configure_background_worker()
    
    # Import and run background worker
    from background_worker_optimized import main as worker_main
    await worker_main()

if __name__ == "__main__":
    asyncio.run(main())