#!/usr/bin/env python3
"""
Centralized configuration management with environment variables and defaults
"""

import os
from typing import Optional

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
    
    # Debug settings
    DEBUG_MODE: bool = os.getenv('DEBUG', '0') == '1'
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def validate(cls) -> list:
        """Validate configuration and return list of errors"""
        errors = []
        
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        
        if not cls.GROQ_API_KEY:
            errors.append("GROQ_API_KEY is required")
        
        if cls.USE_WEBHOOK and not cls.WEBHOOK_URL:
            errors.append("WEBHOOK_URL is required when USE_WEBHOOK=1")
        
        return errors
    
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