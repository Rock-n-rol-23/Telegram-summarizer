#!/usr/bin/env python3
"""
Main Entry Point for Replit Deployment
This file explicitly defines the main application entry point without using $file variable
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
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def main():
    """Main entry point for Replit deployment"""
    logger.info("🚀 Starting Telegram Summarization Bot - Main Entry Point")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Working Directory: {os.getcwd()}")
    logger.info(f"Port: {os.getenv('PORT', '5000')}")
    
    # Determine deployment mode
    deployment_type = os.getenv('DEPLOYMENT_TYPE', 'cloudrun').lower()
    logger.info(f"Deployment Type: {deployment_type}")
    
    if deployment_type == 'background':
        # Background Worker mode - bot only
        logger.info("Starting in Background Worker mode...")
        from background_worker_optimized import main as worker_main
        asyncio.run(worker_main())
    else:
        # Cloud Run mode - HTTP server + bot (default)
        logger.info("Starting in Cloud Run mode...")
        from cloudrun_optimized import main as cloudrun_main
        asyncio.run(cloudrun_main())

if __name__ == "__main__":
    main()