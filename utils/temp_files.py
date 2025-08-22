#!/usr/bin/env python3
"""
Temporary file management with automatic cleanup
"""

import asyncio
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional, Set
from config import config

logger = logging.getLogger(__name__)

class TempFileManager:
    """Manages temporary files with automatic cleanup"""
    
    def __init__(self):
        self.temp_dir = Path(config.DATA_DIR) / "telegram_bot_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.tracked_files: Set[Path] = set()
        self.cleanup_task: Optional[asyncio.Task] = None
        
        logger.info(f"Temp file manager initialized: {self.temp_dir}")
    
    def create_temp_file(self, suffix: str = "", prefix: str = "tb_") -> Path:
        """
        Create a temporary file and track it for cleanup
        
        Args:
            suffix: File suffix (e.g., '.pdf')
            prefix: File prefix
            
        Returns:
            Path to temporary file
        """
        
        fd, temp_path = tempfile.mkstemp(
            suffix=suffix,
            prefix=prefix,
            dir=self.temp_dir
        )
        
        # Close file descriptor immediately
        os.close(fd)
        
        temp_path = Path(temp_path)
        self.tracked_files.add(temp_path)
        
        logger.debug(f"Created temp file: {temp_path}")
        return temp_path
    
    def create_temp_dir(self, prefix: str = "tb_dir_") -> Path:
        """
        Create a temporary directory and track it for cleanup
        
        Args:
            prefix: Directory prefix
            
        Returns:
            Path to temporary directory
        """
        
        temp_dir = Path(tempfile.mkdtemp(
            prefix=prefix,
            dir=self.temp_dir
        ))
        
        self.tracked_files.add(temp_dir)
        
        logger.debug(f"Created temp directory: {temp_dir}")
        return temp_dir
    
    def cleanup_file(self, file_path: Path) -> bool:
        """
        Clean up a specific file or directory
        
        Args:
            file_path: Path to clean up
            
        Returns:
            True if cleanup successful, False otherwise
        """
        
        try:
            if file_path.is_file():
                file_path.unlink()
                logger.debug(f"Deleted temp file: {file_path}")
            elif file_path.is_dir():
                shutil.rmtree(file_path)
                logger.debug(f"Deleted temp directory: {file_path}")
            
            self.tracked_files.discard(file_path)
            return True
            
        except Exception as e:
            logger.warning(f"Failed to cleanup {file_path}: {e}")
            return False
    
    def cleanup_old_files(self, max_age_hours: float = None) -> int:
        """
        Clean up files older than specified age
        
        Args:
            max_age_hours: Maximum age in hours (default from config)
            
        Returns:
            Number of files cleaned up
        """
        
        max_age_hours = max_age_hours or config.TEMP_FILE_RETENTION_HOURS
        max_age_seconds = max_age_hours * 3600
        current_time = time.time()
        
        cleaned_count = 0
        files_to_remove = set()
        
        # Check all files in temp directory
        for file_path in self.temp_dir.rglob("*"):
            try:
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    
                    if file_age > max_age_seconds:
                        if self.cleanup_file(file_path):
                            cleaned_count += 1
                        files_to_remove.add(file_path)
                        
            except Exception as e:
                logger.warning(f"Error checking file age {file_path}: {e}")
        
        # Remove from tracking
        self.tracked_files -= files_to_remove
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old temp files")
        
        return cleaned_count
    
    def cleanup_all_tracked(self) -> int:
        """
        Clean up all tracked files
        
        Returns:
            Number of files cleaned up
        """
        
        cleaned_count = 0
        files_to_clean = list(self.tracked_files)
        
        for file_path in files_to_clean:
            if self.cleanup_file(file_path):
                cleaned_count += 1
        
        logger.info(f"Cleaned up {cleaned_count} tracked temp files")
        return cleaned_count
    
    def get_disk_usage(self) -> dict:
        """Get disk usage statistics for temp directory"""
        
        try:
            total_size = 0
            file_count = 0
            
            for file_path in self.temp_dir.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
                    file_count += 1
            
            return {
                'total_size_bytes': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'file_count': file_count,
                'tracked_files': len(self.tracked_files),
                'temp_dir': str(self.temp_dir)
            }
            
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return {
                'error': str(e),
                'temp_dir': str(self.temp_dir)
            }
    
    async def start_cleanup_task(self):
        """Start periodic cleanup task"""
        
        if self.cleanup_task and not self.cleanup_task.done():
            return
        
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Started periodic temp file cleanup task")
    
    async def _cleanup_loop(self):
        """Periodic cleanup loop"""
        
        while True:
            try:
                await asyncio.sleep(config.AUTO_CLEANUP_INTERVAL)
                
                # Cleanup old files
                self.cleanup_old_files()
                
                # Log disk usage periodically
                usage = self.get_disk_usage()
                if usage.get('total_size_mb', 0) > 100:  # Log if > 100MB
                    logger.info(f"Temp directory usage: {usage['total_size_mb']:.1f}MB, {usage['file_count']} files")
                
            except asyncio.CancelledError:
                logger.info("Cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Cleanup task error: {e}")
    
    def stop_cleanup_task(self):
        """Stop periodic cleanup task"""
        
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            logger.info("Stopped periodic temp file cleanup task")
    
    def __del__(self):
        """Cleanup on destruction"""
        self.stop_cleanup_task()

# Global temp file manager
temp_manager = TempFileManager()

# Convenience functions
def create_temp_file(suffix: str = "", prefix: str = "tb_") -> Path:
    """Create a temporary file"""
    return temp_manager.create_temp_file(suffix, prefix)

def create_temp_dir(prefix: str = "tb_dir_") -> Path:
    """Create a temporary directory"""
    return temp_manager.create_temp_dir(prefix)

def cleanup_file(file_path: Path) -> bool:
    """Clean up a specific file"""
    return temp_manager.cleanup_file(file_path)

async def startup_cleanup():
    """Perform cleanup on startup"""
    logger.info("Performing startup temp file cleanup...")
    
    # Clean up old files
    cleaned = temp_manager.cleanup_old_files()
    
    # Start periodic cleanup
    await temp_manager.start_cleanup_task()
    
    # Log initial status
    usage = temp_manager.get_disk_usage()
    logger.info(
        f"Startup cleanup completed: {cleaned} files removed, "
        f"{usage['total_size_mb']:.1f}MB in {usage['file_count']} files remaining"
    )

async def shutdown_cleanup():
    """Perform cleanup on shutdown"""
    logger.info("Performing shutdown temp file cleanup...")
    
    # Stop cleanup task
    temp_manager.stop_cleanup_task()
    
    # Clean up all tracked files
    cleaned = temp_manager.cleanup_all_tracked()
    
    logger.info(f"Shutdown cleanup completed: {cleaned} files removed")