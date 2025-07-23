#!/usr/bin/env python3
"""
Enhanced deployment script for Telegram bot with multiple deployment modes
This is the main entry point for deployment on various platforms
"""

import os
import sys
import asyncio
from main_server import main
from simple_bot import SimpleTelegramBot

def get_deployment_mode():
    """Determine deployment mode based on environment variables"""
    deployment_type = os.getenv('DEPLOYMENT_TYPE', 'cloudrun')
    replit_env = os.getenv('REPLIT_ENV')
    
    # If on Replit and no specific deployment type, use background mode
    if replit_env and deployment_type == 'cloudrun':
        return 'background'
    return deployment_type.lower()

async def run_background_worker():
    """Run as background worker without HTTP server"""
    print("Starting in Background Worker mode...")
    bot = SimpleTelegramBot()
    await bot.run()

async def run_cloud_run():
    """Run with HTTP server for Cloud Run"""
    print("Starting in Cloud Run mode with HTTP server...")
    await main()

if __name__ == "__main__":
    deployment_mode = get_deployment_mode()
    print(f"Deployment mode: {deployment_mode}")
    
    try:
        if deployment_mode == 'background':
            asyncio.run(run_background_worker())
        else:
            asyncio.run(run_cloud_run())
    except KeyboardInterrupt:
        print("Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)