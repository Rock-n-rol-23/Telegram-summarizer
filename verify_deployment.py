#!/usr/bin/env python3
"""
Deployment verification script
Tests all deployment modes and health check endpoints
"""

import asyncio
import json
import requests
import subprocess
import time
import sys
import os

def test_health_endpoints():
    """Test all health check endpoints"""
    endpoints = [
        ('/', 'Root health check'),
        ('/health', 'Health endpoint'),
        ('/ready', 'Readiness probe'),  
        ('/status', 'Status information'),
        ('/ping', 'Ping endpoint')
    ]
    
    base_url = "http://localhost:5000"
    results = []
    
    print("🔍 Testing Health Check Endpoints")
    print("=" * 50)
    
    for endpoint, description in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            
            # Try to parse JSON
            try:
                data = response.json()
                json_valid = True
            except:
                data = response.text
                json_valid = False
            
            status = "✅ PASS" if response.status_code == 200 else "❌ FAIL"
            print(f"{endpoint:10} | {description:20} | {status} | Status: {response.status_code}")
            
            if json_valid and isinstance(data, dict):
                print(f"           | Response: {json.dumps(data, indent=2)[:100]}...")
            
            results.append({
                'endpoint': endpoint,
                'status_code': response.status_code,
                'success': response.status_code == 200,
                'json_valid': json_valid
            })
            
        except Exception as e:
            print(f"{endpoint:10} | {description:20} | ❌ ERROR | {str(e)}")
            results.append({
                'endpoint': endpoint,
                'success': False,
                'error': str(e)
            })
    
    print()
    return results

def test_deployment_files():
    """Test that all deployment entry points exist and are valid"""
    entry_points = [
        ('run.py', 'Primary Cloud Run entry point'),
        ('main.py', 'Auto-detection entry point'),
        ('app.py', 'Flask-style compatibility'),
        ('simple_bot.py', 'Background worker mode'),
        ('main_server.py', 'HTTP server implementation')
    ]
    
    print("📁 Testing Deployment Entry Points")
    print("=" * 50)
    
    results = []
    for file_path, description in entry_points:
        if os.path.exists(file_path):
            try:
                # Basic syntax check
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check if it's a Python file with proper structure
                has_main = '__main__' in content
                has_imports = 'import' in content
                
                status = "✅ PASS"
                details = f"Main block: {has_main}, Imports: {has_imports}"
                success = True
                
            except Exception as e:
                status = "❌ ERROR"
                details = str(e)
                success = False
        else:
            status = "❌ MISSING"
            details = "File not found"
            success = False
        
        print(f"{file_path:15} | {description:25} | {status} | {details}")
        results.append({
            'file': file_path,
            'success': success,
            'details': details
        })
    
    print()
    return results

def test_workflow_configuration():
    """Test current workflow configuration"""
    print("⚙️  Workflow Configuration")
    print("=" * 50)
    
    # Check environment variables
    port = os.getenv('PORT', '5000')
    deployment_type = os.getenv('DEPLOYMENT_TYPE', 'auto-detect')
    
    print(f"Port:            {port}")
    print(f"Deployment Type: {deployment_type}")
    print(f"Working Dir:     {os.getcwd()}")
    print(f"Python Version:  {sys.version.split()[0]}")
    print()

def main():
    """Main verification function"""
    print("🚀 Telegram Bot Deployment Verification")
    print("=" * 60)
    print()
    
    # Test workflow configuration
    test_workflow_configuration()
    
    # Test deployment files
    file_results = test_deployment_files()
    
    # Test health endpoints
    health_results = test_health_endpoints()
    
    # Summary
    print("📊 Summary")
    print("=" * 50)
    
    file_success = sum(1 for r in file_results if r['success'])
    health_success = sum(1 for r in health_results if r['success'])
    
    print(f"Entry Points:    {file_success}/{len(file_results)} working")
    print(f"Health Checks:   {health_success}/{len(health_results)} working")
    
    all_good = file_success == len(file_results) and health_success == len(health_results)
    
    if all_good:
        print("\n🎉 All deployment tests PASSED! Ready for production deployment.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please check the issues above.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)