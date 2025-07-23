#!/usr/bin/env python3
"""
Alternative entry point for Flask-style deployment compatibility
This ensures compatibility with various deployment platforms that expect app.py
"""

import os
import sys
import asyncio

# Set Cloud Run mode explicitly
os.environ['DEPLOYMENT_TYPE'] = 'cloudrun'

# Import simple server and run
from simple_server import main

if __name__ == "__main__":
    asyncio.run(main())