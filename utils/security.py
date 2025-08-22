#!/usr/bin/env python3
"""
Security utilities: MIME validation, file type checking, sanitization
"""

import hashlib
import hmac
import logging
import mimetypes
import os
from typing import Dict, List, Optional, Tuple
from config import config

logger = logging.getLogger(__name__)

# File type allowlists
ALLOWED_MIME_TYPES = {
    'text': [
        'text/plain',
        'text/html',
        'text/csv',
        'text/markdown'
    ],
    'document': [
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    ],
    'image': [
        'image/jpeg',
        'image/jpg', 
        'image/png',
        'image/gif',
        'image/bmp',
        'image/tiff',
        'image/webp'
    ],
    'audio': [
        'audio/mpeg',
        'audio/mp3',
        'audio/wav',
        'audio/ogg',
        'audio/flac',
        'audio/aac',
        'audio/m4a',
        'audio/opus'
    ],
    'video': [
        'video/mp4',
        'video/avi',
        'video/mov',
        'video/wmv',
        'video/webm'
    ]
}

ALL_ALLOWED_MIME_TYPES = []
for category in ALLOWED_MIME_TYPES.values():
    ALL_ALLOWED_MIME_TYPES.extend(category)

def validate_file_size(file_size: int, file_type: str = 'general') -> Tuple[bool, str]:
    """Validate file size against limits"""
    
    limits = {
        'image': config.MAX_IMAGE_SIZE_MB * 1024 * 1024,
        'general': config.MAX_FILE_SIZE_MB * 1024 * 1024
    }
    
    limit = limits.get(file_type, limits['general'])
    
    if file_size > limit:
        return False, f"File too large: {file_size / (1024*1024):.1f}MB > {limit / (1024*1024)}MB"
    
    return True, "OK"

def detect_mime_type(file_path: str, filename: str = None) -> Optional[str]:
    """Detect MIME type with multiple methods"""
    
    mime_type = None
    
    # Try python-magic if available
    try:
        import magic
        mime_type = magic.from_file(file_path, mime=True)
        logger.debug(f"Magic detected MIME type: {mime_type}")
    except ImportError:
        logger.debug("python-magic not available, using mimetypes")
    except Exception as e:
        logger.warning(f"Magic MIME detection failed: {e}")
    
    # Fallback to mimetypes
    if not mime_type and filename:
        mime_type, _ = mimetypes.guess_type(filename)
        logger.debug(f"Mimetypes guessed: {mime_type}")
    
    # Final fallback based on file extension
    if not mime_type and filename:
        ext = os.path.splitext(filename.lower())[1]
        extension_map = {
            '.txt': 'text/plain',
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.ogg': 'audio/ogg',
            '.mp4': 'video/mp4'
        }
        mime_type = extension_map.get(ext)
        logger.debug(f"Extension mapping: {ext} -> {mime_type}")
    
    return mime_type

def validate_file_type(file_path: str, filename: str = None, 
                      allowed_categories: List[str] = None) -> Tuple[bool, str, str]:
    """
    Validate file type against allowlist
    
    Returns:
        (is_valid, mime_type, error_message)
    """
    
    if not config.MIME_TYPE_VALIDATION:
        # MIME validation disabled
        return True, "unknown", "Validation disabled"
    
    # Detect MIME type
    mime_type = detect_mime_type(file_path, filename)
    
    if not mime_type:
        return False, "unknown", "Could not determine file type"
    
    # Check against allowlist
    if allowed_categories:
        # Check specific categories
        allowed_types = []
        for category in allowed_categories:
            if category in ALLOWED_MIME_TYPES:
                allowed_types.extend(ALLOWED_MIME_TYPES[category])
    else:
        # Check all allowed types
        allowed_types = ALL_ALLOWED_MIME_TYPES
    
    if mime_type not in allowed_types:
        return False, mime_type, f"File type not allowed: {mime_type}"
    
    logger.info(f"File validation passed: {mime_type}")
    return True, mime_type, "OK"

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage"""
    
    # Remove directory separators and dangerous characters
    dangerous_chars = ['/', '\\', '..', '<', '>', ':', '"', '|', '?', '*', '\0']
    
    for char in dangerous_chars:
        filename = filename.replace(char, '_')
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        max_name_len = 255 - len(ext)
        filename = name[:max_name_len] + ext
    
    # Ensure it's not empty
    if not filename.strip():
        filename = "unnamed_file"
    
    return filename

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify Telegram webhook signature"""
    
    if not secret:
        logger.warning("No webhook secret configured")
        return True  # Allow if no secret is set
    
    try:
        # Telegram uses HMAC-SHA256
        expected_signature = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        # Remove 'sha256=' prefix if present
        if signature.startswith('sha256='):
            signature = signature[7:]
        
        return hmac.compare_digest(expected_signature, signature)
        
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {e}")
        return False

def sanitize_markdown(text: str) -> str:
    """Sanitize text for safe Telegram markdown parsing"""
    
    # Escape special Telegram MarkdownV2 characters
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

def get_file_hash(file_path: str) -> str:
    """Get SHA256 hash of file for deduplication"""
    
    hash_sha256 = hashlib.sha256()
    
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    
    return hash_sha256.hexdigest()

def validate_upload(file_path: str, filename: str = None, 
                   file_type_category: str = None) -> Dict:
    """
    Comprehensive file upload validation
    
    Returns:
        Dict with validation results
    """
    
    result = {
        'valid': False,
        'mime_type': None,
        'file_size': 0,
        'file_hash': None,
        'errors': []
    }
    
    try:
        # Check file exists
        if not os.path.exists(file_path):
            result['errors'].append("File does not exist")
            return result
        
        # Get file size
        file_size = os.path.getsize(file_path)
        result['file_size'] = file_size
        
        # Validate file size
        size_valid, size_error = validate_file_size(
            file_size, 
            file_type_category or 'general'
        )
        if not size_valid:
            result['errors'].append(size_error)
        
        # Validate file type
        type_valid, mime_type, type_error = validate_file_type(
            file_path, 
            filename,
            [file_type_category] if file_type_category else None
        )
        result['mime_type'] = mime_type
        if not type_valid:
            result['errors'].append(type_error)
        
        # Get file hash for deduplication
        try:
            result['file_hash'] = get_file_hash(file_path)
        except Exception as e:
            logger.warning(f"Could not compute file hash: {e}")
        
        # Overall validation result
        result['valid'] = size_valid and type_valid
        
        if result['valid']:
            logger.info(
                f"File validation passed: {filename} "
                f"({file_size} bytes, {mime_type})"
            )
        else:
            logger.warning(
                f"File validation failed: {filename} - "
                f"Errors: {', '.join(result['errors'])}"
            )
        
        return result
        
    except Exception as e:
        result['errors'].append(f"Validation error: {str(e)}")
        logger.error(f"File validation exception: {e}")
        return result