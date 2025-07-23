#!/usr/bin/env python3
"""
Deployment script for Telegram bot with HTTP health check endpoint
This is the main entry point for Cloud Run deployment
"""

from main_server import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())