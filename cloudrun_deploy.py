#!/usr/bin/env python3
"""
Explicit Cloud Run deployment entry point
This file specifically addresses the Cloud Run deployment requirements
"""

import os
import sys
import asyncio

# Ensure we're in Cloud Run mode
os.environ['DEPLOYMENT_TYPE'] = 'cloudrun'

# Set the port from Cloud Run environment
if 'PORT' not in os.environ:
    os.environ['PORT'] = '5000'

print(f"Cloud Run Deployment Starting...")
print(f"Port: {os.environ.get('PORT')}")
print(f"Deployment Type: {os.environ.get('DEPLOYMENT_TYPE')}")

# Import and run the deployment server
try:
    from deploy_server import main
    
    if __name__ == "__main__":
        asyncio.run(main())
        
except ImportError as e:
    print(f"Import error: {e}")
    print("Falling back to simple_server...")
    
    # Fallback to simple_server
    from simple_server import main
    
    if __name__ == "__main__":
        asyncio.run(main())