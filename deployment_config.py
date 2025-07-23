#!/usr/bin/env python3
"""
Deployment Configuration Manager
Handles deployment mode selection and verification
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DeploymentConfig:
    """Manage deployment configuration and mode selection"""
    
    CLOUD_RUN_FILE = "cloudrun_optimized.py"
    BACKGROUND_WORKER_FILE = "background_worker_optimized.py"
    
    @classmethod
    def detect_deployment_mode(cls):
        """Detect the appropriate deployment mode based on environment"""
        
        # Check explicit deployment type setting
        deployment_type = os.getenv('DEPLOYMENT_TYPE', '').lower()
        if deployment_type in ['cloudrun', 'cloud-run', 'http']:
            return 'cloudrun'
        elif deployment_type in ['background', 'worker', 'bot']:
            return 'background'
        
        # Auto-detect based on environment variables
        if os.getenv('K_SERVICE'):  # Google Cloud Run
            return 'cloudrun'
        elif os.getenv('REPLIT_DEPLOYMENT'):  # Replit Deployment
            return 'cloudrun'
        elif os.getenv('PORT'):  # HTTP server expected
            return 'cloudrun'
        
        # Default to Cloud Run for maximum compatibility
        return 'cloudrun'
    
    @classmethod
    def get_entry_point(cls, mode=None):
        """Get the appropriate entry point file for deployment mode"""
        if mode is None:
            mode = cls.detect_deployment_mode()
        
        if mode == 'cloudrun':
            return cls.CLOUD_RUN_FILE
        elif mode == 'background':
            return cls.BACKGROUND_WORKER_FILE
        else:
            return cls.CLOUD_RUN_FILE  # Default fallback
    
    @classmethod
    def verify_deployment_files(cls):
        """Verify that all required deployment files exist"""
        required_files = [
            cls.CLOUD_RUN_FILE,
            cls.BACKGROUND_WORKER_FILE,
            "simple_bot.py",
            "summarizer.py",
            "database.py",
            "config.py"
        ]
        
        missing_files = []
        for file in required_files:
            if not Path(file).exists():
                missing_files.append(file)
        
        if missing_files:
            logger.error(f"Missing required files: {missing_files}")
            return False
        
        logger.info("✅ All required deployment files present")
        return True
    
    @classmethod
    def verify_environment_variables(cls):
        """Verify required environment variables"""
        required_vars = ['TELEGRAM_BOT_TOKEN']
        optional_vars = ['GROQ_API_KEY', 'PORT']
        
        missing_required = []
        for var in required_vars:
            if not os.getenv(var):
                missing_required.append(var)
        
        if missing_required:
            logger.error(f"Missing required environment variables: {missing_required}")
            return False
        
        logger.info("✅ Required environment variables present")
        
        # Log optional variables status
        for var in optional_vars:
            if os.getenv(var):
                logger.info(f"✅ {var} found")
            else:
                logger.info(f"ℹ️  {var} not set (optional)")
        
        return True
    
    @classmethod
    def get_deployment_summary(cls):
        """Get a summary of the current deployment configuration"""
        mode = cls.detect_deployment_mode()
        entry_point = cls.get_entry_point(mode)
        port = os.getenv('PORT', '5000')
        
        summary = {
            'mode': mode,
            'entry_point': entry_point,
            'port': port,
            'telegram_bot_token': '✅' if os.getenv('TELEGRAM_BOT_TOKEN') else '❌',
            'groq_api_key': '✅' if os.getenv('GROQ_API_KEY') else '❌',
            'files_ready': cls.verify_deployment_files(),
            'env_vars_ready': cls.verify_environment_variables()
        }
        
        return summary

async def main():
    """Main function for deployment configuration check"""
    logger.info("🔍 Deployment Configuration Check")
    logger.info("=" * 50)
    
    config = DeploymentConfig()
    summary = config.get_deployment_summary()
    
    logger.info(f"Deployment Mode: {summary['mode'].upper()}")
    logger.info(f"Entry Point: {summary['entry_point']}")
    logger.info(f"Port: {summary['port']}")
    logger.info(f"Files Ready: {'✅' if summary['files_ready'] else '❌'}")
    logger.info(f"Environment Ready: {'✅' if summary['env_vars_ready'] else '❌'}")
    
    if summary['files_ready'] and summary['env_vars_ready']:
        logger.info("✅ Deployment configuration is ready!")
        logger.info(f"✅ Run with: python {summary['entry_point']}")
    else:
        logger.error("❌ Deployment configuration has issues")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())