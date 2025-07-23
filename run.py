#!/usr/bin/env python3
"""
Simplified run entry point for Cloud Run deployment
This file explicitly starts the simplified server with HTTP endpoints
"""

import sys
import os
import asyncio

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run simple server
from simple_server import main

if __name__ == "__main__":
    # Force Cloud Run mode for deployment
    os.environ['DEPLOYMENT_TYPE'] = 'cloudrun'
    asyncio.run(main())