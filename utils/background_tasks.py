#!/usr/bin/env python3
"""
Background task processing with progress updates and timeout handling
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional
from utils.logging_config import set_request_context, TimedLogger
from config import config

logger = logging.getLogger(__name__)

class BackgroundTask:
    """Background task with progress tracking and timeout"""
    
    def __init__(self, task_id: str, user_id: int, chat_id: int, 
                 progress_callback: Callable = None):
        self.task_id = task_id
        self.user_id = user_id
        self.chat_id = chat_id
        self.progress_callback = progress_callback
        self.start_time = time.time()
        self.status = 'pending'
        self.progress = 0.0
        self.result = None
        self.error = None
        self.cancelled = False
        
    async def update_progress(self, progress: float, message: str = None):
        """Update task progress and notify user"""
        self.progress = min(max(progress, 0.0), 1.0)
        
        if self.progress_callback and message:
            try:
                await self.progress_callback(
                    self.chat_id, 
                    f"🔄 {message}\n📊 Прогресс: {self.progress:.0%}",
                    self.task_id
                )
            except Exception as e:
                logger.warning(f"Progress update failed: {e}")
    
    def cancel(self):
        """Cancel the task"""
        self.cancelled = True
        self.status = 'cancelled'
    
    @property
    def is_completed(self) -> bool:
        return self.status in ['completed', 'failed', 'cancelled']
    
    @property
    def duration(self) -> float:
        return time.time() - self.start_time

class BackgroundTaskManager:
    """Manages background tasks with timeout and cleanup"""
    
    def __init__(self):
        self.tasks: Dict[str, BackgroundTask] = {}
        self.cleanup_task = None
    
    async def start_cleanup_task(self):
        """Start periodic cleanup of completed tasks"""
        if not self.cleanup_task:
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def _cleanup_loop(self):
        """Periodic cleanup of old tasks"""
        while True:
            try:
                await asyncio.sleep(300)  # Clean up every 5 minutes
                self._cleanup_completed_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup task error: {e}")
    
    def _cleanup_completed_tasks(self):
        """Remove completed tasks older than 1 hour"""
        current_time = time.time()
        to_remove = []
        
        for task_id, task in self.tasks.items():
            if (task.is_completed and 
                current_time - task.start_time > 3600):  # 1 hour
                to_remove.append(task_id)
        
        for task_id in to_remove:
            del self.tasks[task_id]
            
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} completed tasks")
    
    async def create_task(self, task_id: str, user_id: int, chat_id: int,
                         task_func: Callable, progress_callback: Callable = None,
                         timeout: int = None, *args, **kwargs) -> BackgroundTask:
        """
        Create and start a background task
        
        Args:
            task_id: Unique task identifier
            user_id: User ID for context
            chat_id: Chat ID for progress updates
            task_func: Function to execute
            progress_callback: Function to call for progress updates
            timeout: Task timeout in seconds
            *args, **kwargs: Arguments for task_func
        """
        
        # Create task object
        bg_task = BackgroundTask(task_id, user_id, chat_id, progress_callback)
        self.tasks[task_id] = bg_task
        
        # Set request context
        set_request_context(task_id, user_id)
        
        # Create asyncio task with timeout
        timeout = timeout or config.BACKGROUND_TASK_TIMEOUT
        
        async def wrapped_task():
            try:
                bg_task.status = 'running'
                
                with TimedLogger(logger, f"background task {task_id}"):
                    result = await asyncio.wait_for(
                        task_func(bg_task, *args, **kwargs),
                        timeout=timeout
                    )
                
                bg_task.result = result
                bg_task.status = 'completed'
                bg_task.progress = 1.0
                
                logger.info(f"Background task completed: {task_id}")
                return result
                
            except asyncio.TimeoutError:
                bg_task.error = f"Task timed out after {timeout} seconds"
                bg_task.status = 'failed'
                logger.error(f"Background task timed out: {task_id}")
                
            except asyncio.CancelledError:
                bg_task.status = 'cancelled'
                logger.info(f"Background task cancelled: {task_id}")
                
            except Exception as e:
                bg_task.error = str(e)
                bg_task.status = 'failed'
                logger.error(f"Background task failed: {task_id} - {e}")
                
            return None
        
        # Start the task
        asyncio.create_task(wrapped_task())
        
        logger.info(f"Started background task: {task_id} (timeout: {timeout}s)")
        return bg_task
    
    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Get task by ID"""
        return self.tasks.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        task = self.tasks.get(task_id)
        if task and not task.is_completed:
            task.cancel()
            logger.info(f"Cancelled background task: {task_id}")
            return True
        return False
    
    def get_user_tasks(self, user_id: int) -> list:
        """Get all tasks for a user"""
        return [task for task in self.tasks.values() if task.user_id == user_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get task manager statistics"""
        total_tasks = len(self.tasks)
        status_counts = {}
        
        for task in self.tasks.values():
            status_counts[task.status] = status_counts.get(task.status, 0) + 1
        
        return {
            'total_tasks': total_tasks,
            'status_counts': status_counts,
            'cleanup_task_running': self.cleanup_task is not None
        }

# Global task manager
task_manager = BackgroundTaskManager()

async def run_in_background(task_id: str, user_id: int, chat_id: int,
                           task_func: Callable, progress_callback: Callable = None,
                           timeout: int = None, *args, **kwargs) -> BackgroundTask:
    """
    Convenience function to run a task in background
    """
    return await task_manager.create_task(
        task_id, user_id, chat_id, task_func, progress_callback, timeout,
        *args, **kwargs
    )

async def wait_for_task(task_id: str, poll_interval: float = 1.0) -> Any:
    """
    Wait for a background task to complete
    
    Returns:
        Task result or raises exception if task failed
    """
    
    while True:
        task = task_manager.get_task(task_id)
        
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        
        if task.status == 'completed':
            return task.result
        elif task.status == 'failed':
            raise Exception(f"Task failed: {task.error}")
        elif task.status == 'cancelled':
            raise asyncio.CancelledError("Task was cancelled")
        
        await asyncio.sleep(poll_interval)

# Example background task functions

async def process_large_document(task: BackgroundTask, file_path: str, 
                                processing_func: Callable) -> Dict:
    """Example: Process large document with progress updates"""
    
    await task.update_progress(0.1, "Загрузка документа...")
    
    # Simulate document loading
    await asyncio.sleep(1)
    
    await task.update_progress(0.3, "Извлечение текста...")
    
    # Process document
    result = await processing_func(file_path)
    
    await task.update_progress(0.8, "Создание резюме...")
    
    # Simulate summarization
    await asyncio.sleep(2)
    
    await task.update_progress(1.0, "Готово!")
    
    return result

async def process_youtube_video(task: BackgroundTask, url: str,
                               extraction_func: Callable) -> Dict:
    """Example: Process YouTube video with progress updates"""
    
    await task.update_progress(0.1, "Получение информации о видео...")
    
    # Get video info
    await asyncio.sleep(1)
    
    await task.update_progress(0.4, "Загрузка субтитров...")
    
    # Extract content
    result = await extraction_func(url)
    
    await task.update_progress(0.8, "Анализ контента...")
    
    await asyncio.sleep(2)
    
    await task.update_progress(1.0, "Обработка завершена!")
    
    return result