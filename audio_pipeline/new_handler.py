"""
New audio processing handlers for voice, audio, and video_note messages
Implements the complete pipeline according to specifications
"""

import logging
import os
import tempfile
import asyncio
import io
from typing import Dict, Any, Optional

from .downloader import extract_file_id, download_audio_async, get_audio_metadata
from .transcriber import transcribe_audio
from .segmenter import AudioSegmenter
from utils.ffmpeg import to_wav_16k_mono, get_audio_info, check_ffmpeg
from summarization_adapter import run_summarization, format_audio_summary

logger = logging.getLogger(__name__)

# Configuration from environment
AUDIO_SUMMARY_ENABLED = os.getenv("AUDIO_SUMMARY_ENABLED", "true").lower() == "true"
ASR_ENGINE = os.getenv("ASR_ENGINE", "auto")
ASR_VAD_ENABLED = os.getenv("ASR_VAD_ENABLED", "true").lower() == "true"
ASR_MAX_DURATION_MIN = int(os.getenv("ASR_MAX_DURATION_MIN", "90"))
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
ASR_CHUNK_SEC = int(os.getenv("ASR_CHUNK_SEC", "45"))
ASR_CHUNK_OVERLAP_SEC = int(os.getenv("ASR_CHUNK_OVERLAP_SEC", "5"))

async def handle_voice(update, context):
    """Handle voice messages"""
    return await _handle_audio_message(update, context, "voice")

async def handle_audio(update, context):
    """Handle audio files"""
    return await _handle_audio_message(update, context, "audio")

async def handle_video_note(update, context):
    """Handle video notes (optional)"""
    return await _handle_audio_message(update, context, "video_note")

async def _handle_audio_message(update, context, message_type: str):
    """
    Main audio processing pipeline
    
    Args:
        update: Telegram update
        context: Bot context
        message_type: 'voice', 'audio', or 'video_note'
    """
    if not AUDIO_SUMMARY_ENABLED:
        await update.message.reply_text("⚠️ Аудио обработка отключена")
        return
    
    message = update.message
    user_id = message.from_user.id
    
    # Send initial processing message
    processing_msg = await message.reply_text("🎤 Получил аудио, обрабатываю...")
    
    temp_files = []
    temp_dirs = []
    
    try:
        # Step 1: Extract file ID and metadata
        logger.info(f"Step 1: Extracting file info from {message_type}")
        
        file_id = extract_file_id(message)
        metadata = get_audio_metadata(message)
        
        logger.info(f"Processing {message_type}: {file_id}")
        
        # Step 2: Validate limits
        if metadata.get('file_size') and metadata['file_size'] > 50 * 1024 * 1024:  # 50MB
            await processing_msg.edit_text("❌ Файл слишком большой (максимум 50 МБ)")
            return
        
        if metadata.get('duration') and metadata['duration'] > ASR_MAX_DURATION_MIN * 60:
            await processing_msg.edit_text(f"❌ Аудио слишком длинное (максимум {ASR_MAX_DURATION_MIN} мин)")
            return
        
        # Step 3: Download file
        logger.info("Step 2: Downloading audio file...")
        temp_dir = tempfile.mkdtemp(prefix="audio_processing_")
        temp_dirs.append(temp_dir)
        
        downloaded_path = await download_audio_async(context.bot, file_id, temp_dir)
        temp_files.append(downloaded_path)
        
        await processing_msg.edit_text("🔄 Конвертирую аудио...")
        
        # Step 4: Convert to WAV 16kHz mono
        logger.info("Step 3: Converting to WAV format...")
        wav_path = os.path.join(temp_dir, "converted.wav")
        
        if not check_ffmpeg():
            await processing_msg.edit_text("❌ FFmpeg недоступен для конвертации аудио")
            return
        
        if not to_wav_16k_mono(downloaded_path, wav_path):
            await processing_msg.edit_text("❌ Ошибка конвертации аудио")
            return
        
        temp_files.append(wav_path)
        
        # Step 5: Get audio info
        audio_info = get_audio_info(wav_path)
        duration_sec = audio_info.get("duration", 0)
        
        if duration_sec > ASR_MAX_DURATION_MIN * 60:
            await processing_msg.edit_text(f"❌ Аудио слишком длинное: {duration_sec/60:.1f} мин (максимум {ASR_MAX_DURATION_MIN} мин)")
            return
        
        await processing_msg.edit_text("🎯 Сегментирую аудио...")
        
        # Step 6: Segment audio if needed
        logger.info("Step 4: Segmenting audio...")
        segmenter = AudioSegmenter()
        segments = await segmenter.segment_audio(wav_path, duration_sec)
        temp_files.extend(segments)
        
        await processing_msg.edit_text(f"🔍 Транскрибирую {len(segments)} сегментов...")
        
        # Step 7: Transcribe segments
        logger.info("Step 5: Transcribing segments...")
        transcription_results = []
        
        for i, segment_path in enumerate(segments, 1):
            logger.info(f"Transcribing segment {i}/{len(segments)}")
            result = transcribe_audio(segment_path, language_hint="ru")
            transcription_results.append(result)
        
        # Step 8: Combine transcriptions
        logger.info("Step 6: Combining transcription results...")
        full_text = _combine_transcriptions(transcription_results)
        
        # Determine language and engine used
        language = transcription_results[0].get("language", "ru") if transcription_results else "ru"
        engine = transcription_results[0].get("engine", "fallback") if transcription_results else "fallback"
        
        await processing_msg.edit_text("🤖 Генерирую саммари...")
        
        # Step 9: Generate summary
        logger.info("Step 7: Generating summary...")
        
        if full_text and len(full_text.strip()) > 50:
            summary = await run_summarization(full_text, language_hint=language)
        else:
            summary = "Текст слишком короткий для создания саммари."
        
        # Step 10: Format result
        logger.info("Step 8: Preparing response...")
        
        result_metadata = {
            "engine": engine,
            "language": language,
            "duration_sec": duration_sec,
            "chunks": len(segments)
        }
        
        formatted_summary = format_audio_summary(summary, result_metadata)
        
        # Step 11: Send response
        await processing_msg.edit_text(formatted_summary)
        
        # Send transcription file if there's content
        if full_text and len(full_text.strip()) > 10:
            transcript_file = io.BytesIO(full_text.encode('utf-8'))
            transcript_file.name = f"transcript_{file_id[:8]}.txt"
            
            await message.reply_document(
                document=transcript_file,
                caption="📄 Полная транскрипция аудио"
            )
        
        logger.info(f"Audio processing completed successfully for user {user_id}")
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        await processing_msg.edit_text(f"❌ {str(e)}")
        
    except Exception as e:
        logger.error(f"Audio processing error: {e}")
        await processing_msg.edit_text("❌ Ошибка обработки аудио. Попробуйте позже.")
        
    finally:
        # Cleanup
        for file_path in temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"Failed to remove temp file {file_path}: {e}")
        
        for temp_dir in temp_dirs:
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Failed to remove temp dir {temp_dir}: {e}")

def _combine_transcriptions(transcription_results) -> str:
    """Combine multiple transcription results"""
    texts = []
    
    for result in transcription_results:
        if result and result.get('text'):
            text = result['text'].strip()
            # Skip fallback messages
            if not text.startswith('[ТРАНСКРИПЦИЯ НЕДОСТУПНА]'):
                texts.append(text)
    
    combined = ' '.join(texts).strip()
    
    # If no real transcription found, use the first fallback message
    if not combined and transcription_results:
        first_result = transcription_results[0]
        if first_result and first_result.get('text'):
            combined = first_result['text']
    
    return combined