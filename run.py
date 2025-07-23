#!/usr/bin/env python3
"""
Main entry point for deployment
This script ensures the correct startup sequence for the Telegram bot application
"""

import os
import sys
import asyncio
from main_server import main

if __name__ == "__main__":
    # Ensure the correct Python environment
    print("Starting Telegram Bot Application...")
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    
    # Run the main function
    asyncio.run(main())