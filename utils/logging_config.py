#!/usr/bin/env python3
"""
Structured logging configuration with JSON output and request tracking
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

from config import config

# Context variables for request tracking
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
user_id_var: ContextVar[Optional[int]] = ContextVar('user_id', default=None)

class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        
        # Base log entry
        log_entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add request context if available
        request_id = request_id_var.get()
        if request_id:
            log_entry['request_id'] = request_id
            
        user_id = user_id_var.get()
        if user_id:
            log_entry['user_id'] = user_id
        
        # Add extra fields from record
        if hasattr(record, 'duration'):
            log_entry['duration'] = record.duration
            
        if hasattr(record, 'external_service'):
            log_entry['external_service'] = record.external_service
            
        if hasattr(record, 'external_duration'):
            log_entry['external_duration'] = record.external_duration
            
        if hasattr(record, 'status_code'):
            log_entry['status_code'] = record.status_code
            
        if hasattr(record, 'file_size'):
            log_entry['file_size'] = record.file_size
            
        if hasattr(record, 'compression_ratio'):
            log_entry['compression_ratio'] = record.compression_ratio
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add module and function info for debugging
        if config.DEBUG_MODE:
            log_entry.update({
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno,
            })
        
        return json.dumps(log_entry, ensure_ascii=False)

def setup_logging():
    """Configure logging based on config settings"""
    
    # Set log level
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Set formatter based on structured logging setting
    if config.STRUCTURED_LOGGING:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Silence noisy third-party loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    
    return root_logger

def get_request_id() -> str:
    """Get or create request ID for current context"""
    request_id = request_id_var.get()
    if not request_id:
        request_id = str(uuid.uuid4())[:8]
        request_id_var.set(request_id)
    return request_id

def set_request_context(request_id: str = None, user_id: int = None):
    """Set request context variables"""
    if request_id:
        request_id_var.set(request_id)
    if user_id:
        user_id_var.set(user_id)

def clear_request_context():
    """Clear request context variables"""
    request_id_var.set(None)
    user_id_var.set(None)

class TimedLogger:
    """Context manager for timing operations with structured logging"""
    
    def __init__(self, logger: logging.Logger, operation: str, 
                 external_service: str = None, **extra_fields):
        self.logger = logger
        self.operation = operation
        self.external_service = external_service
        self.extra_fields = extra_fields
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.logger.info(
            f"Starting {self.operation}",
            extra={
                'external_service': self.external_service,
                **self.extra_fields
            }
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        if exc_type is None:
            self.logger.info(
                f"Completed {self.operation}",
                extra={
                    'duration': duration,
                    'external_service': self.external_service,
                    'external_duration': duration if self.external_service else None,
                    **self.extra_fields
                }
            )
        else:
            self.logger.error(
                f"Failed {self.operation}: {exc_val}",
                extra={
                    'duration': duration,
                    'external_service': self.external_service,
                    'external_duration': duration if self.external_service else None,
                    **self.extra_fields
                },
                exc_info=True
            )

def log_external_call(logger: logging.Logger, service_name: str, 
                     duration: float, status_code: int = None, **extra):
    """Log external service call timing"""
    logger.info(
        f"External call to {service_name}",
        extra={
            'external_service': service_name,
            'external_duration': duration,
            'status_code': status_code,
            **extra
        }
    )

# Initialize logging on import
logger = setup_logging()