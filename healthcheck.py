#!/usr/bin/env python3
"""
Health check script for deployment verification
"""

import sys
import requests
import time

def check_health(max_retries=3, delay=5):
    """Check if the application is healthy"""
    for attempt in range(max_retries):
        try:
            response = requests.get('http://localhost:5000/health', timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'healthy':
                    print(f"✅ Health check passed: {data}")
                    return True
                else:
                    print(f"❌ Health check failed: {data}")
            else:
                print(f"❌ HTTP error: {response.status_code}")
        except Exception as e:
            print(f"❌ Health check error (attempt {attempt + 1}): {e}")
        
        if attempt < max_retries - 1:
            print(f"⏳ Retrying in {delay} seconds...")
            time.sleep(delay)
    
    return False

if __name__ == "__main__":
    if check_health():
        sys.exit(0)
    else:
        print("❌ Health check failed after all retries")
        sys.exit(1)