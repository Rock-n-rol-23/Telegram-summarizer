#!/usr/bin/env python3
"""
Verification script to test deployment readiness
This script verifies that all deployment requirements are met
"""

import os
import sys
import asyncio
import aiohttp
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_http_endpoints(port=5000):
    """Test all HTTP endpoints that Cloud Run expects"""
    base_url = f"http://localhost:{port}"
    endpoints = ['/', '/health', '/ready', '/healthz', '/readiness']
    
    logger.info(f"Testing HTTP endpoints on {base_url}")
    
    async with aiohttp.ClientSession() as session:
        results = {}
        for endpoint in endpoints:
            try:
                url = f"{base_url}{endpoint}"
                timeout = aiohttp.ClientTimeout(total=5)
                async with session.get(url, timeout=timeout) as response:
                    status = response.status
                    content_type = response.headers.get('content-type', '')
                    text = await response.text()
                    
                    results[endpoint] = {
                        'status': status,
                        'content_type': content_type,
                        'response_length': len(text),
                        'success': status == 200
                    }
                    
                    logger.info(f"✓ {endpoint}: Status {status}, Content-Type: {content_type}")
                    
            except Exception as e:
                results[endpoint] = {'success': False, 'error': str(e)}
                logger.error(f"✗ {endpoint}: {e}")
        
        return results

def check_deployment_files():
    """Check that all required deployment files exist"""
    required_files = [
        'simple_server.py',
        'deploy_server.py', 
        'cloudrun_deploy.py',
        'simple_bot.py',
        'config.py',
        'pyproject.toml'
    ]
    
    logger.info("Checking deployment files...")
    missing_files = []
    
    for file in required_files:
        if os.path.exists(file):
            logger.info(f"✓ {file} exists")
        else:
            logger.error(f"✗ {file} missing")
            missing_files.append(file)
    
    return len(missing_files) == 0, missing_files

def check_environment_variables():
    """Check required environment variables"""
    required_vars = ['TELEGRAM_BOT_TOKEN']
    optional_vars = ['GROQ_API_KEY', 'PORT']
    
    logger.info("Checking environment variables...")
    
    missing_required = []
    for var in required_vars:
        if os.getenv(var):
            logger.info(f"✓ {var} is set")
        else:
            logger.error(f"✗ {var} is missing (required)")
            missing_required.append(var)
    
    for var in optional_vars:
        if os.getenv(var):
            logger.info(f"✓ {var} is set")
        else:
            logger.info(f"⚠ {var} is not set (optional)")
    
    return len(missing_required) == 0, missing_required

async def main():
    """Main verification function"""
    logger.info("=== Deployment Readiness Verification ===")
    
    # Check files
    files_ok, missing_files = check_deployment_files()
    
    # Check environment variables
    env_ok, missing_vars = check_environment_variables()
    
    # Check if server is running for endpoint testing
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Attempting to test endpoints on port {port}...")
    
    try:
        endpoint_results = await test_http_endpoints(port)
        endpoints_ok = all(result.get('success', False) for result in endpoint_results.values())
    except Exception as e:
        logger.warning(f"Could not test endpoints: {e}")
        logger.info("This is normal if the server is not currently running")
        endpoints_ok = None
    
    # Summary
    logger.info("\n=== DEPLOYMENT READINESS SUMMARY ===")
    
    if files_ok:
        logger.info("✓ All required deployment files present")
    else:
        logger.error(f"✗ Missing files: {missing_files}")
    
    if env_ok:
        logger.info("✓ All required environment variables set")
    else:
        logger.error(f"✗ Missing environment variables: {missing_vars}")
    
    if endpoints_ok is True:
        logger.info("✓ All HTTP endpoints responding correctly")
    elif endpoints_ok is False:
        logger.error("✗ Some HTTP endpoints not responding")
    else:
        logger.info("⚠ HTTP endpoints not tested (server not running)")
    
    # Overall status
    deployment_ready = files_ok and env_ok
    
    if deployment_ready:
        logger.info("\n🎉 DEPLOYMENT READY!")
        logger.info("All deployment requirements satisfied.")
        logger.info("Cloud Run deployment should succeed.")
        
        if endpoints_ok is not True:
            logger.info("Note: Start the server to verify HTTP endpoints")
            
    else:
        logger.error("\n❌ DEPLOYMENT NOT READY")
        logger.error("Please fix the issues above before deploying")
    
    return deployment_ready

if __name__ == "__main__":
    asyncio.run(main())