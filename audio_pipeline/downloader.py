"""
Единая точка скачивания аудио файлов
Простая и надежная реализация для Railway
"""
import os
import time
import tempfile
import logging

logger = logging.getLogger(__name__)

def download_audio(bot, file_id: str, out_dir: str = None) -> str:
    """
    Скачивает файл по file_id в out_dir и возвращает путь к файлу
    
    Args:
        bot: SimpleTelegramBot instance с методом download_file
        file_id: Telegram file_id
        out_dir: Директория для сохранения (по умолчанию /tmp)
        
    Returns:
        Путь к скачанному файлу или None при ошибке
    """
    if out_dir is None:
        out_dir = tempfile.gettempdir()
    
    try:
        # Создаем директорию если нужно
        os.makedirs(out_dir, exist_ok=True)
        
        # Генерируем уникальное имя файла
        timestamp = int(time.time() * 1000)
        filename = f"tg_{timestamp}_{file_id[:8]}.bin"
        dst_path = os.path.join(out_dir, filename)
        
        # Скачиваем через bot.download_file
        result = bot.download_file(file_id, dst_path)
        
        if result and os.path.exists(dst_path):
            file_size = os.path.getsize(dst_path)
            logger.info(f"Файл скачан: {dst_path} ({file_size} bytes)")
            return dst_path
        else:
            logger.error(f"Файл не был скачан: {file_id}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка скачивания файла {file_id}: {e}")
        return None

async def download_audio_async(bot, file_id: str, out_dir: str = None) -> str:
    """
    Асинхронная версия download_audio
    
    Args:
        bot: SimpleTelegramBot instance с методом download_file
        file_id: Telegram file_id
        out_dir: Директория для сохранения (по умолчанию /tmp)
        
    Returns:
        Путь к скачанному файлу или None при ошибке
    """
    if out_dir is None:
        out_dir = tempfile.gettempdir()
    
    try:
        # Создаем директорию если нужно
        os.makedirs(out_dir, exist_ok=True)
        
        # Генерируем уникальное имя файла
        timestamp = int(time.time() * 1000)
        filename = f"tg_{timestamp}_{file_id[:8]}.bin"
        dst_path = os.path.join(out_dir, filename)
        
        # Скачиваем через bot.download_file (должен быть async)
        result = await bot.download_file(file_id, dst_path)
        
        if result and os.path.exists(dst_path):
            file_size = os.path.getsize(dst_path)
            logger.info(f"Файл скачан: {dst_path} ({file_size} bytes)")
            return dst_path
        else:
            logger.error(f"Файл не был скачан: {file_id}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка скачивания файла {file_id}: {e}")
        return None