#!/usr/bin/env python3
"""
Alternative entry point for Flask-style deployment compatibility
This ensures compatibility with various deployment platforms that expect app.py
"""

import os
import sys

# Set Cloud Run mode explicitly
os.environ['DEPLOYMENT_TYPE'] = 'cloudrun'

# Import main and run
from main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())