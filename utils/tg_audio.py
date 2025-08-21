"""
Модуль для извлечения информации об аудио из сообщений Telegram
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

def extract_audio_descriptor(message: Dict) -> Dict:
    """
    Извлекает информацию об аудио из сообщения Telegram
    
    Args:
        message: Объект сообщения Telegram
        
    Returns:
        {
            "success": bool,
            "file_id": str,
            "type": str,           # "voice", "audio", "video_note", "document"
            "filename": str,
            "duration": float,
            "file_size": int,
            "error": str           # если success=False
        }
    """
    
    try:
        # Голосовое сообщение
        if "voice" in message:
            voice = message["voice"]
            return {
                "success": True,
                "file_id": voice["file_id"],
                "type": "голосовое сообщение",
                "filename": f"voice_{voice['file_id'][:8]}.ogg",
                "duration": voice.get("duration", 0.0),
                "file_size": voice.get("file_size", 0),
                "mime_type": voice.get("mime_type", "audio/ogg")
            }
        
        # Аудиофайл
        elif "audio" in message:
            audio = message["audio"]
            filename = audio.get("file_name", f"audio_{audio['file_id'][:8]}.mp3")
            return {
                "success": True,
                "file_id": audio["file_id"],
                "type": "аудиофайл",
                "filename": filename,
                "duration": audio.get("duration", 0.0),
                "file_size": audio.get("file_size", 0),
                "mime_type": audio.get("mime_type", "audio/mpeg")
            }
        
        # Видео-заметка (круглое видео)
        elif "video_note" in message:
            video_note = message["video_note"]
            return {
                "success": True,
                "file_id": video_note["file_id"],
                "type": "видео-заметка",
                "filename": f"video_note_{video_note['file_id'][:8]}.mp4",
                "duration": video_note.get("duration", 0.0),
                "file_size": video_note.get("file_size", 0),
                "mime_type": "video/mp4"
            }
        
        # Документ с аудио
        elif "document" in message:
            document = message["document"]
            mime_type = document.get("mime_type", "")
            filename = document.get("file_name", "")
            
            # Проверяем, является ли документ аудиофайлом
            audio_mime_types = [
                "audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg", 
                "audio/m4a", "audio/aac", "audio/flac", "audio/opus"
            ]
            
            audio_extensions = [".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".opus"]
            
            is_audio = (
                mime_type in audio_mime_types or
                any(filename.lower().endswith(ext) for ext in audio_extensions)
            )
            
            if is_audio:
                return {
                    "success": True,
                    "file_id": document["file_id"],
                    "type": "аудио-документ",
                    "filename": filename or f"document_{document['file_id'][:8]}",
                    "duration": 0.0,  # Документы не имеют duration в API
                    "file_size": document.get("file_size", 0),
                    "mime_type": mime_type
                }
        
        # Не найдено аудио
        return {
            "success": False,
            "error": "В сообщении не найдено аудио, голосового сообщения или видео-заметки"
        }
        
    except Exception as e:
        logger.error(f"Ошибка извлечения аудио дескриптора: {e}")
        return {
            "success": False,
            "error": f"Ошибка обработки сообщения: {str(e)}"
        }


def format_duration(duration: float) -> str:
    """Форматирует длительность в человекочитаемый вид"""
    try:
        if duration <= 0:
            return "неизвестно"
        
        duration = int(duration)
        
        if duration < 60:
            return f"{duration}с"
        elif duration < 3600:
            minutes = duration // 60
            seconds = duration % 60
            return f"{minutes}м {seconds}с"
        else:
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            return f"{hours}ч {minutes}м"
            
    except Exception:
        return "неизвестно"


def format_file_size(size: int) -> str:
    """Форматирует размер файла в человекочитаемый вид"""
    try:
        if size <= 0:
            return "неизвестно"
        
        if size < 1024:
            return f"{size} Б"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} КБ"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} МБ"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} ГБ"
            
    except Exception:
        return "неизвестно"


def get_audio_info_text(audio_info: Dict) -> str:
    """Создает текстовое описание аудио для пользователя"""
    if not audio_info["success"]:
        return f"❌ {audio_info['error']}"
    
    parts = [f"🎧 {audio_info['type'].title()}: {audio_info['filename']}"]
    
    duration = audio_info.get("duration", 0)
    if duration > 0:
        parts.append(f"⏱️ Длительность: {format_duration(duration)}")
    
    file_size = audio_info.get("file_size", 0)
    if file_size > 0:
        parts.append(f"📦 Размер: {format_file_size(file_size)}")
    
    return "\n".join(parts)