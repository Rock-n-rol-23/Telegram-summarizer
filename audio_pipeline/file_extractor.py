"""
Извлечение file_id из различных типов сообщений
Поддерживает voice, audio, document (audio/*), video_note
"""
import logging

logger = logging.getLogger(__name__)

def extract_audio_file_id_and_kind(message):
    """
    Извлекает file_id и тип из аудио сообщения
    
    Args:
        message: Telegram message объект или dict
        
    Returns:
        tuple: (file_id, kind) или raises ValueError
        
    Supported kinds:
        - "voice": голосовые сообщения
        - "audio": аудио файлы
        - "document-audio": документы с audio/* mime-type
        - "video_note": видео заметки (кружочки)
    """
    try:
        # Проверяем voice message
        voice = getattr(message, "voice", None) or (isinstance(message, dict) and message.get("voice"))
        if voice:
            file_id = voice.get("file_id") if isinstance(voice, dict) else voice.file_id
            logger.info(f"Найдено voice сообщение: {file_id}")
            return file_id, "voice"
        
        # Проверяем audio file
        audio = getattr(message, "audio", None) or (isinstance(message, dict) and message.get("audio"))
        if audio:
            file_id = audio.get("file_id") if isinstance(audio, dict) else audio.file_id
            logger.info(f"Найден audio файл: {file_id}")
            return file_id, "audio"
            
        # Проверяем document с audio mime-type
        document = getattr(message, "document", None) or (isinstance(message, dict) and message.get("document"))
        if document:
            mime_type = document.get("mime_type") if isinstance(document, dict) else getattr(document, "mime_type", None)
            if mime_type and mime_type.startswith("audio/"):
                file_id = document.get("file_id") if isinstance(document, dict) else document.file_id
                logger.info(f"Найден document-audio файл: {file_id} (mime: {mime_type})")
                return file_id, "document-audio"
        
        # Проверяем video_note
        video_note = getattr(message, "video_note", None) or (isinstance(message, dict) and message.get("video_note"))
        if video_note:
            file_id = video_note.get("file_id") if isinstance(video_note, dict) else video_note.file_id
            logger.info(f"Найдена video_note: {file_id}")
            return file_id, "video_note"
        
        # Ничего не найдено
        logger.warning("В сообщении не найден поддерживаемый аудиофайл")
        raise ValueError("В сообщении не найден поддерживаемый аудиофайл (voice/audio/document/video_note)")
        
    except Exception as e:
        logger.error(f"Ошибка извлечения file_id: {e}")
        raise ValueError(f"Ошибка извлечения file_id: {e}")

def get_audio_metadata(message, kind: str) -> dict:
    """
    Извлекает метаданные из аудио сообщения
    
    Args:
        message: Telegram message объект
        kind: тип файла из extract_audio_file_id_and_kind
        
    Returns:
        dict с метаданными
    """
    metadata = {"kind": kind}
    
    try:
        if kind == "voice":
            voice = getattr(message, "voice", None) or (isinstance(message, dict) and message.get("voice"))
            if voice:
                metadata.update({
                    "duration": voice.get("duration") if isinstance(voice, dict) else getattr(voice, "duration", 0),
                    "mime_type": voice.get("mime_type") if isinstance(voice, dict) else getattr(voice, "mime_type", "audio/ogg"),
                    "file_size": voice.get("file_size") if isinstance(voice, dict) else getattr(voice, "file_size", 0)
                })
                
        elif kind == "audio":
            audio = getattr(message, "audio", None) or (isinstance(message, dict) and message.get("audio"))
            if audio:
                metadata.update({
                    "duration": audio.get("duration") if isinstance(audio, dict) else getattr(audio, "duration", 0),
                    "mime_type": audio.get("mime_type") if isinstance(audio, dict) else getattr(audio, "mime_type", "audio/mpeg"),
                    "file_size": audio.get("file_size") if isinstance(audio, dict) else getattr(audio, "file_size", 0),
                    "title": audio.get("title") if isinstance(audio, dict) else getattr(audio, "title", None),
                    "performer": audio.get("performer") if isinstance(audio, dict) else getattr(audio, "performer", None)
                })
                
        elif kind == "document-audio":
            document = getattr(message, "document", None) or (isinstance(message, dict) and message.get("document"))
            if document:
                metadata.update({
                    "mime_type": document.get("mime_type") if isinstance(document, dict) else getattr(document, "mime_type", "audio/wav"),
                    "file_size": document.get("file_size") if isinstance(document, dict) else getattr(document, "file_size", 0),
                    "file_name": document.get("file_name") if isinstance(document, dict) else getattr(document, "file_name", "audio.wav")
                })
                
        elif kind == "video_note":
            video_note = getattr(message, "video_note", None) or (isinstance(message, dict) and message.get("video_note"))
            if video_note:
                metadata.update({
                    "duration": video_note.get("duration") if isinstance(video_note, dict) else getattr(video_note, "duration", 0),
                    "file_size": video_note.get("file_size") if isinstance(video_note, dict) else getattr(video_note, "file_size", 0),
                    "length": video_note.get("length") if isinstance(video_note, dict) else getattr(video_note, "length", 0)
                })
        
        logger.info(f"Метаданные извлечены для {kind}: {metadata}")
        return metadata
        
    except Exception as e:
        logger.error(f"Ошибка извлечения метаданных: {e}")
        return metadata  # Возвращаем базовые метаданные