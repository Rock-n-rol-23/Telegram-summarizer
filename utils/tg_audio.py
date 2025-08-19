"""
Утилиты для обработки аудио сообщений в Telegram
Унифицированное извлечение аудио дескрипторов из различных типов сообщений
"""
import re
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

def _safe_int_seconds(value):
    """Пробует привести значение длительности к int секунд (поддерживает int/float/str)."""
    try:
        if value is None:
            return None
        return int(round(float(value)))
    except Exception:
        return None

def format_duration(value) -> str:
    """
    Возвращает строку формата M:SS (например, '1:06').
    Поддерживает входные int/float/str секунд, None -> ''.
    """
    total = _safe_int_seconds(value)
    if total is None:
        return ""
    minutes, seconds = divmod(total, 60)
    return f"{minutes}:{seconds:02d}"

# Поддерживаемые аудио расширения
AUDIO_EXTENSIONS = {'.ogg', '.oga', '.mp3', '.m4a', '.wav', '.flac', '.webm', '.aac', '.opus'}

# Поддерживаемые MIME типы для аудио
AUDIO_MIME_TYPES = {
    'audio/ogg', 'audio/mpeg', 'audio/mp3', 'audio/mp4', 'audio/m4a',
    'audio/wav', 'audio/x-wav', 'audio/flac', 'audio/webm', 'audio/aac',
    'audio/opus', 'audio/x-opus+ogg'
}

def extract_audio_descriptor(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Извлекает дескриптор аудио из сообщения Telegram.
    
    Поддерживает:
    - voice (голосовые сообщения)
    - audio (аудио файлы)
    - video_note (кружочки)
    - document с аудио MIME-типом или расширением
    - пересланные сообщения со всеми вышеперечисленными типами
    
    Args:
        message: Словарь сообщения Telegram
        
    Returns:
        Dict с полями:
        - kind: "voice" | "audio" | "video_note" | "document"
        - file_id: str
        - mime_type: Optional[str]
        - duration: Optional[int]
        - file_name: Optional[str]
        
        Или None, если аудио не найдено
    """
    
    # Функция для извлечения дескриптора из конкретного сообщения
    def _extract_from_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # 1. Проверяем voice (голосовые сообщения)
        if "voice" in msg:
            voice = msg["voice"]
            return {
                "kind": "voice",
                "file_id": voice["file_id"],
                "mime_type": voice.get("mime_type", "audio/ogg"),
                "duration": _safe_int_seconds(voice.get("duration")),
                "file_name": "voice.ogg"
            }
        
        # 2. Проверяем audio (аудио файлы)
        elif "audio" in msg:
            audio = msg["audio"]
            return {
                "kind": "audio", 
                "file_id": audio["file_id"],
                "mime_type": audio.get("mime_type"),
                "duration": _safe_int_seconds(audio.get("duration")),
                "file_name": audio.get("file_name", "audio.mp3")
            }
        
        # 3. Проверяем video_note (кружочки)
        elif "video_note" in msg:
            video_note = msg["video_note"]
            return {
                "kind": "video_note",
                "file_id": video_note["file_id"],
                "mime_type": "video/mp4",  # обычно MP4, но нам нужна аудио дорожка
                "duration": _safe_int_seconds(video_note.get("duration")),
                "file_name": "video_note.mp4"
            }
        
        # 4. Проверяем document с аудио содержимым
        elif "document" in msg:
            document = msg["document"]
            mime_type = document.get("mime_type", "")
            file_name = document.get("file_name", "")
            
            # Проверяем MIME тип
            is_audio_mime = mime_type.startswith("audio/") if mime_type else False
            
            # Проверяем расширение файла
            is_audio_extension = False
            if file_name:
                file_path = Path(file_name)
                is_audio_extension = file_path.suffix.lower() in AUDIO_EXTENSIONS
            
            if is_audio_mime or is_audio_extension:
                return {
                    "kind": "document",
                    "file_id": document["file_id"],
                    "mime_type": mime_type or "audio/mpeg",  # fallback MIME
                    "duration": None,  # у документов обычно нет duration
                    "file_name": file_name or "audio_document"
                }
        
        return None
    
    # Сначала пробуем извлечь из основного сообщения
    result = _extract_from_message(message)
    if result:
        logger.info(f"Найден аудио дескриптор: {result['kind']} - {result['file_name']}")
        return result
    
    # Фолбэк: если это reply на сообщение с аудио, пробуем из reply_to_message
    if "reply_to_message" in message:
        reply_msg = message["reply_to_message"]
        result = _extract_from_message(reply_msg)
        if result:
            logger.info(f"Найден аудио дескриптор в reply_to_message: {result['kind']} - {result['file_name']}")
            return result
    
    logger.debug("Аудио дескриптор не найден в сообщении")
    return None


def sanitize_filename(name: str) -> str:
    """
    Очищает имя файла от недопустимых символов.
    
    Args:
        name: Исходное имя файла
        
    Returns:
        Очищенное имя файла
    """
    if not name:
        return "audio_file"
    
    # Убираем недопустимые символы для файловой системы
    sanitized = re.sub(r'[<>:"/\\|?*]', '', name)
    
    # Заменяем пробелы на подчеркивания и убираем множественные подчеркивания
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Обрезаем до разумной длины
    if len(sanitized) > 100:
        path = Path(sanitized)
        name_part = path.stem[:90]
        ext_part = path.suffix
        sanitized = f"{name_part}{ext_part}"
    
    # Убираем ведущие/завершающие символы
    sanitized = sanitized.strip('._-')
    
    return sanitized or "audio_file"


def is_audio_document(document: Dict[str, Any]) -> bool:
    """
    Проверяет, является ли документ аудио файлом.
    
    Args:
        document: Словарь с данными документа из Telegram
        
    Returns:
        True, если документ содержит аудио
    """
    mime_type = document.get("mime_type", "")
    file_name = document.get("file_name", "")
    
    # Проверка MIME типа
    if mime_type and mime_type.startswith("audio/"):
        return True
    
    # Проверка расширения файла
    if file_name:
        file_path = Path(file_name)
        if file_path.suffix.lower() in AUDIO_EXTENSIONS:
            return True
    
    return False


def get_audio_info_text(descriptor: Dict[str, Any]) -> str:
    """
    Формирует текстовое описание аудио файла для пользователя.
    
    Args:
        descriptor: Дескриптор аудио из extract_audio_descriptor
        
    Returns:
        Форматированная строка с информацией об аудио
    """
    kind_names = {
        "voice": "Голосовое сообщение",
        "audio": "Аудио файл", 
        "video_note": "Видео сообщение",
        "document": "Аудио документ"
    }
    
    kind_name = kind_names.get(descriptor["kind"], "Аудио")
    file_name = descriptor.get("file_name", "неизвестно")
    duration = descriptor.get("duration")
    
    info = f"{kind_name}: {file_name}"
    
    dur_text = format_duration(duration)
    if dur_text:
        info += f" ({dur_text})"
    
    return info