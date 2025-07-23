#!/usr/bin/env python3
"""
Simple run entry point for deployment
This is the most basic entry point for Cloud Run deployment
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Add current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def main():
    """Simple main entry point"""
    logger.info("🚀 Starting Telegram Bot - Simple Entry Point")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Working Directory: {os.getcwd()}")
    logger.info(f"Port: {os.getenv('PORT', '5000')}")
    
    # Import and run the main server
    try:
        from main_server import main as server_main
        asyncio.run(server_main())
    except ImportError:
        logger.info("main_server not found, trying cloudrun_optimized")
        from cloudrun_optimized import main as cloudrun_main
        asyncio.run(cloudrun_main())

if __name__ == "__main__":
    main()