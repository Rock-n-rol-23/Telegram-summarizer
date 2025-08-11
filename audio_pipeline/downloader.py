"""
Telegram audio downloader for voice messages, audio files, and video notes
Handles both direct and forwarded messages
"""

import logging
import os
import tempfile
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def extract_file_id(message):
    """Extract file_id from direct or forwarded message"""
    
    # 1) Direct message
    if hasattr(message, 'voice') and message.voice:
        return message.voice.file_id
    if hasattr(message, 'audio') and message.audio:
        return message.audio.file_id
    if hasattr(message, 'video_note') and message.video_note:
        return message.video_note.file_id

    # 2) Forwarded message
    fwd = getattr(message, "forward_from", None) or getattr(message, "forward_from_chat", None)
    if fwd:
        # Check if message itself has audio data (forwarded messages retain audio)
        if hasattr(message, 'voice') and message.voice:
            return message.voice.file_id
        if hasattr(message, 'audio') and message.audio:
            return message.audio.file_id
        if hasattr(message, 'video_note') and message.video_note:
            return message.video_note.file_id

    raise ValueError("В сообщении не найден поддерживаемый аудиофайл.")

def download_audio(bot, file_id: str, out_dir: str) -> str:
    """
    Download audio file from Telegram
    
    Args:
        bot: Telegram bot instance
        file_id: Telegram file ID
        out_dir: Output directory
        
    Returns:
        Path to downloaded file
    """
    try:
        # Get file info
        file_info = bot.get_file(file_id)
        
        # Determine extension
        if file_info.file_path:
            _, ext = os.path.splitext(file_info.file_path)
            if not ext:
                ext = '.ogg'  # Default
        else:
            ext = '.ogg'  # Default for voice messages
        
        # Create output path
        output_path = os.path.join(out_dir, f"tg_{file_id}{ext}")
        
        # Download
        file_info.download(custom_path=output_path)
        
        logger.info(f"Downloaded audio: {file_id} -> {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Download failed for {file_id}: {e}")
        raise RuntimeError(f"Не удалось скачать аудиофайл: {str(e)}")

async def download_audio_async(bot, file_id: str, out_dir: str) -> str:
    """Async version of download_audio"""
    try:
        # Get file info
        file_info = await bot.get_file(file_id)
        
        # Determine extension
        if file_info.file_path:
            _, ext = os.path.splitext(file_info.file_path)
            if not ext:
                ext = '.ogg'
        else:
            ext = '.ogg'
        
        # Create output path
        output_path = os.path.join(out_dir, f"tg_{file_id}{ext}")
        
        # Download
        await file_info.download_to_drive(output_path)
        
        logger.info(f"Downloaded audio: {file_id} -> {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Async download failed for {file_id}: {e}")
        raise RuntimeError(f"Не удалось скачать аудиофайл: {str(e)}")

def get_audio_metadata(message) -> Dict[str, Any]:
    """Extract audio metadata from message"""
    metadata = {
        "duration": None,
        "file_size": None,
        "mime_type": None,
        "title": None,
        "performer": None
    }
    
    audio_obj = None
    
    # Get audio object
    if hasattr(message, 'voice') and message.voice:
        audio_obj = message.voice
    elif hasattr(message, 'audio') and message.audio:
        audio_obj = message.audio
        metadata["title"] = getattr(audio_obj, 'title', None)
        metadata["performer"] = getattr(audio_obj, 'performer', None)
    elif hasattr(message, 'video_note') and message.video_note:
        audio_obj = message.video_note
    
    if audio_obj:
        metadata["duration"] = getattr(audio_obj, 'duration', None)
        metadata["file_size"] = getattr(audio_obj, 'file_size', None)
        metadata["mime_type"] = getattr(audio_obj, 'mime_type', None)
    
    return metadata

# Legacy class for backward compatibility
class TelegramAudioDownloader:
    """Legacy class - use functions above instead"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get file information from Telegram API
        
        Args:
            file_id: Telegram file ID
            
        Returns:
            File info dict or None if failed
        """
        url = f"{self.base_url}/getFile"
        params = {"file_id": file_id}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("ok"):
                            return data["result"]
                        else:
                            logger.error(f"Telegram API error: {data}")
                    else:
                        logger.error(f"HTTP error {response.status} getting file info")
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
        
        return None
    
    async def download_audio(self, file_id: str, out_dir: str) -> str:
        """
        Download audio file from Telegram
        
        Args:
            file_id: Telegram file ID
            out_dir: Output directory for downloaded file
            
        Returns:
            Path to downloaded file
            
        Raises:
            Exception: If download fails
        """
        # Get file info
        file_info = await self.get_file_info(file_id)
        if not file_info:
            raise Exception(f"Failed to get file info for file_id: {file_id}")
        
        file_path = file_info.get("file_path")
        file_size = file_info.get("file_size", 0)
        
        if not file_path:
            raise Exception("File path not found in Telegram response")
        
        # Check file size limit (50MB for Telegram Bot API)
        if file_size > 50 * 1024 * 1024:
            raise Exception(f"File too large: {file_size} bytes (max 50MB)")
        
        # Construct download URL
        download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
        
        # Determine file extension
        original_ext = os.path.splitext(file_path)[1]
        if not original_ext:
            original_ext = ".ogg"  # Default for voice messages
        
        # Create unique output filename
        import uuid
        output_filename = f"audio_{uuid.uuid4().hex}{original_ext}"
        output_path = os.path.join(out_dir, output_filename)
        
        # Ensure output directory exists
        os.makedirs(out_dir, exist_ok=True)
        
        try:
            logger.info(f"Downloading file from: {download_url}")
            logger.info(f"Output path: {output_path}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(download_url) as response:
                    if response.status == 200:
                        with open(output_path, "wb") as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        
                        # Verify file was downloaded
                        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                            logger.info(f"Successfully downloaded: {output_path} ({os.path.getsize(output_path)} bytes)")
                            return output_path
                        else:
                            raise Exception("Downloaded file is empty or doesn't exist")
                    else:
                        raise Exception(f"HTTP error {response.status} downloading file")
                        
        except Exception as e:
            # Clean up partial download
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except:
                    pass
            raise Exception(f"Failed to download file: {str(e)}")
    
    async def download_with_metadata(self, file_id: str, out_dir: str) -> Dict[str, Any]:
        """
        Download file and return path with metadata
        
        Args:
            file_id: Telegram file ID
            out_dir: Output directory
            
        Returns:
            Dict with file_path, file_size, duration, format info
        """
        file_info = await self.get_file_info(file_id)
        if not file_info:
            raise Exception(f"Failed to get file info for file_id: {file_id}")
        
        file_path = await self.download_audio(file_id, out_dir)
        
        # Extract format from file path
        file_ext = os.path.splitext(file_info.get("file_path", ""))[1].lower()
        
        # Get duration if available (requires ffmpeg)
        duration = None
        try:
            from utils.ffmpeg import get_audio_duration
            duration = get_audio_duration(file_path)
        except Exception as e:
            logger.warning(f"Could not get duration: {e}")
        
        return {
            "file_path": file_path,
            "file_size": file_info.get("file_size", 0),
            "original_path": file_info.get("file_path", ""),
            "format": file_ext,
            "duration": duration
        }

    @staticmethod
    def create_temp_dir() -> str:
        """Create temporary directory for audio processing"""
        temp_dir = tempfile.mkdtemp(prefix="telegram_audio_")
        logger.info(f"Created temp directory: {temp_dir}")
        return temp_dir
    
    @staticmethod
    def cleanup_temp_files(*file_paths: str) -> None:
        """Clean up temporary files"""
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.debug(f"Cleaned up temp file: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {file_path}: {e}")
    
    @staticmethod
    def cleanup_temp_dir(dir_path: str) -> None:
        """Clean up temporary directory and all contents"""
        if dir_path and os.path.exists(dir_path):
            try:
                import shutil
                shutil.rmtree(dir_path)
                logger.debug(f"Cleaned up temp directory: {dir_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup directory {dir_path}: {e}")