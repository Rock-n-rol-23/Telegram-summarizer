#!/usr/bin/env python3
"""
Centralized configuration management with environment variables and defaults
"""

import os
import sys
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

class Config:
    """Configuration management class"""
    
    # Database configuration
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///bot_database.db')
    
    # Telegram configuration
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv('TELEGRAM_BOT_TOKEN')
    WEBHOOK_URL: Optional[str] = os.getenv('WEBHOOK_URL')
    USE_WEBHOOK: bool = os.getenv('USE_WEBHOOK', '0') == '1'
    
    # API keys
    GROQ_API_KEY: Optional[str] = os.getenv('GROQ_API_KEY')
    
    # Rate limiting
    MAX_REQUESTS_PER_MINUTE: int = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '20'))
    
    # File processing limits
    MAX_FILE_SIZE_MB: int = int(os.getenv('MAX_FILE_SIZE_MB', '20'))
    MAX_WEB_CONTENT_SIZE_MB: int = int(os.getenv('MAX_WEB_CONTENT_SIZE_MB', '10'))
    
    # OCR configuration
    OCR_LANGS: str = os.getenv('OCR_LANGS', 'rus+eng')
    PDF_OCR_DPI: int = int(os.getenv('PDF_OCR_DPI', '150'))
    MAX_PAGES_OCR: int = int(os.getenv('MAX_PAGES_OCR', '10'))
    
    # Network timeouts
    HTTP_TIMEOUT: int = int(os.getenv('HTTP_TIMEOUT', '60'))
    HTTP_CONNECT_TIMEOUT: int = int(os.getenv('HTTP_CONNECT_TIMEOUT', '30'))
    
    # Server configuration
    PORT: int = int(os.getenv('PORT', '5000'))
    HOST: str = os.getenv('HOST', '0.0.0.0')
    USE_GUNICORN: bool = os.getenv('USE_GUNICORN', '0') == '1'
    WORKERS: int = int(os.getenv('WORKERS', '2'))
    
    # Data directory (for SQLite and cache files)
    DATA_DIR: str = os.getenv('DATA_DIR', '/tmp')
    
    # Feature flags
    ENABLE_OCR: bool = os.getenv('ENABLE_OCR', '1') == '1'
    ENABLE_YOUTUBE: bool = os.getenv('ENABLE_YOUTUBE', '1') == '1'
    ENABLE_PDF_PROCESSING: bool = os.getenv('ENABLE_PDF_PROCESSING', '1') == '1'
    ENABLE_WEB_EXTRACTION: bool = os.getenv('ENABLE_WEB_EXTRACTION', '1') == '1'
    ENABLE_AUDIO_PROCESSING: bool = os.getenv('ENABLE_AUDIO_PROCESSING', '1') == '1'
    
    # Security
    WEBHOOK_SECRET_TOKEN: Optional[str] = os.getenv('WEBHOOK_SECRET_TOKEN')
    MIME_TYPE_VALIDATION: bool = os.getenv('MIME_TYPE_VALIDATION', '1') == '1'
    MAX_IMAGE_SIZE_MB: int = int(os.getenv('MAX_IMAGE_SIZE_MB', '2'))
    
    # Rate limiting
    GLOBAL_QPS_LIMIT: int = int(os.getenv('GLOBAL_QPS_LIMIT', '10'))
    
    # Logging & observability
    STRUCTURED_LOGGING: bool = os.getenv('STRUCTURED_LOGGING', '1') == '1'
    LOG_REQUEST_ID: bool = os.getenv('LOG_REQUEST_ID', '1') == '1'
    
    # Background processing
    BACKGROUND_TASK_TIMEOUT: int = int(os.getenv('BACKGROUND_TASK_TIMEOUT', '300'))
    PROGRESS_UPDATE_INTERVAL: int = int(os.getenv('PROGRESS_UPDATE_INTERVAL', '5'))
    
    # Temp files & cleanup
    TEMP_FILE_RETENTION_HOURS: int = int(os.getenv('TEMP_FILE_RETENTION_HOURS', '24'))
    AUTO_CLEANUP_INTERVAL: int = int(os.getenv('AUTO_CLEANUP_INTERVAL', '3600'))
    
    # Debug settings
    DEBUG_MODE: bool = os.getenv('DEBUG', '0') == '1'
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def validate(cls) -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []
        
        # Required environment variables
        required_vars = {
            'TELEGRAM_BOT_TOKEN': cls.TELEGRAM_BOT_TOKEN,
            'GROQ_API_KEY': cls.GROQ_API_KEY,
        }
        
        for var_name, var_value in required_vars.items():
            if not var_value:
                errors.append(f"{var_name} is required")
        
        # Conditional requirements
        if cls.USE_WEBHOOK and not cls.WEBHOOK_URL:
            errors.append("WEBHOOK_URL is required when USE_WEBHOOK=1")
            
        if cls.USE_WEBHOOK and not cls.WEBHOOK_SECRET_TOKEN:
            errors.append("WEBHOOK_SECRET_TOKEN is required when USE_WEBHOOK=1")
        
        # Validate numeric ranges
        if cls.MAX_REQUESTS_PER_MINUTE < 1 or cls.MAX_REQUESTS_PER_MINUTE > 1000:
            errors.append("MAX_REQUESTS_PER_MINUTE must be between 1 and 1000")
            
        if cls.MAX_FILE_SIZE_MB < 1 or cls.MAX_FILE_SIZE_MB > 100:
            errors.append("MAX_FILE_SIZE_MB must be between 1 and 100")
        
        return errors
    
    @classmethod
    def validate_and_exit(cls) -> None:
        """Validate configuration and exit if errors found"""
        errors = cls.validate()
        if errors:
            logger.error("Configuration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            logger.error("Please check your environment variables and try again.")
            sys.exit(1)
        logger.info("Configuration validation passed")
    
    @classmethod
    def get_cache_db_path(cls) -> str:
        """Get cache database path"""
        if cls.DATABASE_URL.startswith('sqlite:'):
            # Use same directory as main database for SQLite
            return cls.DATABASE_URL.replace('bot_database.db', 'web_cache.db')
        else:
            # Use temp directory for PostgreSQL setups
            return os.path.join(cls.DATA_DIR, 'web_cache.db')
    
    @classmethod
    def get_summary(cls) -> dict:
        """Get configuration summary for health checks"""
        return {
            'database_type': 'postgresql' if cls.DATABASE_URL.startswith('postgresql:') else 'sqlite',
            'webhook_enabled': cls.USE_WEBHOOK,
            'gunicorn_enabled': cls.USE_GUNICORN,
            'ocr_languages': cls.OCR_LANGS,
            'max_file_size_mb': cls.MAX_FILE_SIZE_MB,
            'rate_limit_per_minute': cls.MAX_REQUESTS_PER_MINUTE,
            'debug_mode': cls.DEBUG_MODE
        }

# Global config instance
config = Config()