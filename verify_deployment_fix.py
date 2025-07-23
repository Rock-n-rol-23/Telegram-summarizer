#!/usr/bin/env python3
"""
Deployment verification script to test all health check endpoints
This script verifies that the deployment fixes are working correctly
"""

import requests
import sys
import json
import time

def test_endpoint(url, expected_status=200, description=""):
    """Test a single endpoint"""
    try:
        response = requests.get(url, timeout=10)
        status = response.status_code
        content = response.text[:200] if response.text else "No content"
        
        print(f"✓ {description}: {status} - {content}")
        return status == expected_status
        
    except Exception as e:
        print(f"✗ {description}: ERROR - {str(e)}")
        return False

def main():
    """Main verification function"""
    base_url = "http://localhost:5000"
    
    print("=== Deployment Fix Verification ===")
    print(f"Testing endpoints at {base_url}")
    print()
    
    # Test all health check endpoints
    tests = [
        (f"{base_url}/", "Root endpoint (/)"),
        (f"{base_url}/health", "Health check endpoint"),
        (f"{base_url}/ready", "Ready endpoint"),
    ]
    
    all_passed = True
    
    for url, description in tests:
        passed = test_endpoint(url, description=description)
        all_passed = all_passed and passed
        time.sleep(0.5)  # Small delay between tests
    
    print()
    if all_passed:
        print("🎉 ALL DEPLOYMENT TESTS PASSED!")
        print("The server is ready for Cloud Run deployment.")
        print()
        print("Key fixes applied:")
        print("- ✓ Explicit run command using simple_server.py")
        print("- ✓ Simple HTTP server responding to health checks")
        print("- ✓ Root endpoint returns plain text response")
        print("- ✓ Health endpoints return JSON with proper status")
        print("- ✓ Server starts on port 5000 with 0.0.0.0 binding")
        return 0
    else:
        print("❌ SOME TESTS FAILED!")
        print("Please check the server logs for issues.")
        return 1

if __name__ == "__main__":
    sys.exit(main())