#!/usr/bin/env python3
"""
Auto-detection deployment script
Automatically chooses deployment mode based on environment
"""

import os
import sys
import asyncio

def detect_deployment_mode():
    """Detect the deployment environment and choose appropriate mode"""
    # Check if we're running on Cloud Run
    if os.getenv('K_SERVICE'):
        return 'cloudrun'
    
    # Check if we're running on Replit
    if os.getenv('REPLIT_DEPLOYMENT'):
        return 'cloudrun'  # Use cloudrun mode for Replit deployment
    
    # Check for explicit deployment type
    deployment_type = os.getenv('DEPLOYMENT_TYPE', '').lower()
    if deployment_type in ['background', 'worker']:
        return 'background'
    elif deployment_type in ['cloudrun', 'http', 'server']:
        return 'cloudrun'
    
    # Default to cloudrun for production deployment
    return 'cloudrun'

async def main():
    """Main deployment function"""
    deployment_mode = detect_deployment_mode()
    print(f"Detected deployment mode: {deployment_mode}")
    
    if deployment_mode == 'background':
        print("Starting in Background Worker mode (bot only)...")
        from simple_bot import SimpleTelegramBot
        bot = SimpleTelegramBot()
        await bot.run()
    else:
        print("Starting in Cloud Run mode (HTTP server + bot)...")
        from main_server import main
        await main()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Deployment interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Deployment failed: {e}")
        sys.exit(1)