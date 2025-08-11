"""
Синхронный обработчик аудио для основного цикла бота
Полная обработка: скачивание -> ffmpeg -> ASR -> саммари -> edit
"""
import os
import time
import traceback
import tempfile
import logging
from typing import Optional, Dict, Any

from .file_extractor import extract_audio_file_id_and_kind, get_audio_metadata
from .downloader import download_audio
from .vosk_transcriber import transcribe_audio, get_available_engines
from utils.ffmpeg import to_wav_16k_mono, is_ffmpeg_available
from summarizer import SummarizerService

logger = logging.getLogger(__name__)

def extract_audio_file_id_and_kind_from_message(message: dict) -> tuple:
    """
    Извлекает file_id и тип из сообщения Telegram
    
    Args:
        message: dict сообщения от Telegram
        
    Returns:
        tuple: (file_id, kind) или (None, None)
    """
    # Voice message
    if "voice" in message:
        return message["voice"]["file_id"], "voice"
    
    # Audio file
    if "audio" in message:
        return message["audio"]["file_id"], "audio"
    
    # Document with audio mime-type
    if "document" in message:
        doc = message["document"]
        mime_type = doc.get("mime_type", "")
        if mime_type.startswith("audio/"):
            return doc["file_id"], "document-audio"
    
    # Video note
    if "video_note" in message:
        return message["video_note"]["file_id"], "video_note"
    
    return None, None

def handle_audio_message_sync(bot, message: dict, workdir: str = "/tmp") -> bool:
    """
    Синхронная обработка аудио сообщения
    
    Args:
        bot: SimpleTelegramBot instance
        message: Telegram message dict
        workdir: рабочая директория для временных файлов
        
    Returns:
        bool: True если это было аудио сообщение (обработано), False если нет
    """
    file_id, kind = extract_audio_file_id_and_kind_from_message(message)
    if not file_id:
        return False  # не аудио - пусть дальше обработает текстовый путь
    
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    
    logger.info(f"🎵 ROUTE audio -> start: file_id={file_id}, kind={kind}, user={user_id}")
    
    # Отправляем заглушку
    try:
        placeholder_response = bot.send_message(chat_id, "🎵 Получил аудио, обрабатываю...")
        if not placeholder_response or not placeholder_response.get("ok"):
            logger.error(f"Не удалось отправить заглушку: {placeholder_response}")
            return True
        
        status_msg_id = placeholder_response["result"]["message_id"]
        logger.info(f"Отправлена заглушка: message_id={status_msg_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки заглушки: {e}")
        return True
    
    t0 = time.time()
    raw_path = wav_path = None
    
    try:
        # Проверяем FFmpeg
        if not is_ffmpeg_available():
            error_msg = "❌ FFmpeg недоступен. Обработка аудио невозможна."
            logger.error(error_msg)
            bot.edit_message_text(chat_id, status_msg_id, error_msg)
            return True
        
        # Проверяем ASR движки
        available_engines = get_available_engines()
        if not available_engines:
            error_msg = "❌ ASR движки не установлены.\n\nУстановите: pip install vosk==0.3.45"
            logger.error(error_msg)
            bot.edit_message_text(chat_id, status_msg_id, error_msg)
            return True
        
        logger.info(f"ASR движки доступны: {available_engines}")
        
        # Создаем рабочую директорию
        os.makedirs(workdir, exist_ok=True)
        
        # 1) Скачиваем файл
        try:
            raw_path = download_audio(bot, file_id, workdir)
            logger.info(f"✅ download ok: {raw_path}")
        except Exception as e:
            error_msg = f"❌ Ошибка скачивания: {e}"
            logger.error(error_msg)
            bot.edit_message_text(chat_id, status_msg_id, error_msg)
            return True
        
        # 2) Конвертируем в WAV 16kHz mono
        try:
            wav_path = os.path.join(workdir, f"norm_{int(time.time())}_{user_id}.wav")
            success = to_wav_16k_mono(raw_path, wav_path)
            if not success:
                raise Exception("FFmpeg конвертация не удалась")
            logger.info(f"✅ ffmpeg ok: {wav_path}")
        except Exception as e:
            error_msg = f"❌ Ошибка конвертации: {e}"
            logger.error(error_msg)
            bot.edit_message_text(chat_id, status_msg_id, error_msg)
            return True
        
        # 3) ASR транскрипция
        try:
            asr_result = transcribe_audio(wav_path, language_hint="ru")
            
            if asr_result.get("error"):
                error_msg = f"❌ Ошибка ASR: {asr_result['error']}"
                logger.error(error_msg)
                bot.edit_message_text(chat_id, status_msg_id, error_msg)
                return True
            
            transcript_text = asr_result.get("text", "").strip()
            if not transcript_text:
                error_msg = "❌ Транскрипция пуста. Возможно, аудио без речи."
                logger.warning(error_msg)
                bot.edit_message_text(chat_id, status_msg_id, error_msg)
                return True
            
            engine = asr_result.get("engine", "unknown")
            logger.info(f"✅ asr ok: engine={engine}, text_len={len(transcript_text)}")
            
        except Exception as e:
            error_msg = f"❌ Ошибка транскрипции: {e}"
            logger.error(error_msg)
            bot.edit_message_text(chat_id, status_msg_id, error_msg)
            return True
        
        # 4) Суммаризация
        try:
            # Получаем предпочтения пользователя (по умолчанию 30%)
            from database import get_user_settings
            user_settings = get_user_settings(user_id)
            compression_ratio = user_settings.get("compression_ratio", 0.3)
            
            # Создаем суммаризатор и суммаризируем  
            from summarizer import summarize_text_sync
            summary = summarize_text_sync(transcript_text, compression_ratio)
            
            if not summary:
                summary = transcript_text  # fallback на полный текст
                
            logger.info(f"✅ summary ok: len={len(summary)}")
            
        except Exception as e:
            error_msg = f"❌ Ошибка суммаризации: {e}"
            logger.error(error_msg)
            # Fallback на транскрипцию
            summary = transcript_text
        
        # 5) Формируем финальное сообщение
        total_time = time.time() - t0
        final_text = (
            f"🎵 **Саммари аудио**\n\n"
            f"🔧 Движок: {engine}\n"
            f"⏱ Время: {total_time:.1f}с\n"
            f"📝 Тип: {kind}\n\n"
            f"{summary}"
        )
        
        # 6) Редактируем заглушку
        try:
            bot.edit_message_text(chat_id, status_msg_id, final_text)
            logger.info(f"✅ ROUTE audio -> done ({total_time:.1f}s)")
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
            # Fallback - отправляем новое сообщение
            bot.send_message(chat_id, final_text)
        
        return True
        
    except Exception as e:
        error_msg = f"❌ Общая ошибка обработки аудио: {e.__class__.__name__}: {e}"
        logger.error(error_msg)
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        
        try:
            bot.edit_message_text(chat_id, status_msg_id, error_msg)
        except Exception:
            try:
                bot.send_message(chat_id, error_msg)
            except Exception:
                pass
        
        return True  # считаем обработанным, чтобы не зациклить
    
    finally:
        # Очищаем временные файлы
        for path in (raw_path, wav_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"Удален временный файл: {path}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить {path}: {e}")

def bot_log(message: str):
    """Лог с префиксом для отладки"""
    logger.info(f"🎵 AUDIO: {message}")