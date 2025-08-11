"""
Main audio processing handler
Orchestrates the entire audio processing pipeline from download to summarization
"""

import logging
import os
import tempfile
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List

from .downloader import TelegramAudioDownloader
from .transcriber_adapter import transcribe_with_whisper, check_whisper_installation
from .segmenter import AudioSegmenter
from .summarization_adapter import run_summarization_with_bot_instance, prepare_audio_summary_response, validate_summarization_input
from utils.ffmpeg import to_wav_16k_mono, extract_audio, get_audio_duration, check_ffmpeg_available

logger = logging.getLogger(__name__)

class AudioHandler:
    """Main handler for audio processing pipeline"""
    
    def __init__(self, bot_token: str, config: Optional[Dict] = None):
        self.bot_token = bot_token
        self.downloader = TelegramAudioDownloader(bot_token)
        
        # Configuration with defaults
        self.config = {
            'AUDIO_SUMMARY_ENABLED': True,
            'ASR_VAD_ENABLED': True,
            'ASR_MAX_DURATION_MIN': 90,
            'FFMPEG_PATH': 'ffmpeg',
            'WHISPER_MODEL_SIZE': 'base',
            'DEFAULT_COMPRESSION_RATIO': 0.3,
            'MAX_FILE_SIZE_MB': 50,
            'TEMP_DIR': None
        }
        
        if config:
            self.config.update(config)
        
        # Initialize components
        self.segmenter = AudioSegmenter(vad_enabled=self.config['ASR_VAD_ENABLED'])
        
        logger.info("AudioHandler initialized")
    
    async def handle_voice(self, update: Dict, context: Any, bot_instance=None) -> bool:
        """
        Handle voice message
        
        Args:
            update: Telegram update object
            context: Telegram context
            bot_instance: Instance of bot for summarization
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            voice = update.get('message', {}).get('voice')
            if not voice:
                return False
            
            chat_id = update['message']['chat']['id']
            user_id = update['message']['from']['id']
            
            logger.info(f"Processing voice message from user {user_id}")
            
            # Check if audio processing is enabled
            if not self.config['AUDIO_SUMMARY_ENABLED']:
                await self._send_message(chat_id, "🔇 Обработка аудио временно отключена", bot_instance)
                return False
            
            # Check duration limit
            duration = voice.get('duration', 0)
            max_duration = self.config['ASR_MAX_DURATION_MIN'] * 60
            
            if duration > max_duration:
                await self._send_message(
                    chat_id,
                    f"❌ Аудио слишком длинное ({duration//60}:{duration%60:02d})\n"
                    f"Максимальная длительность: {self.config['ASR_MAX_DURATION_MIN']} минут",
                    bot_instance
                )
                return False
            
            # Send processing message
            processing_msg = await self._send_message(
                chat_id,
                f"🎤 Получил голосовое сообщение, обрабатываю... (≈{duration}с)",
                bot_instance
            )
            
            # Process the voice message
            result = await self._process_audio_file(
                voice['file_id'],
                'voice',
                duration,
                chat_id,
                user_id,
                bot_instance
            )
            
            if result:
                # Edit processing message with result
                if processing_msg:
                    await self._edit_message(chat_id, processing_msg, result['response_text'], bot_instance)
                else:
                    await self._send_message(chat_id, result['response_text'], bot_instance)
                
                # Send transcription file if available
                if result['transcription_file']:
                    await self._send_document(chat_id, result['transcription_file'], bot_instance)
                
                return True
            else:
                error_msg = "❌ Не удалось обработать голосовое сообщение\n\nПопробуйте позже или обратитесь к администратору."
                if processing_msg:
                    await self._edit_message(chat_id, processing_msg, error_msg, bot_instance)
                else:
                    await self._send_message(chat_id, error_msg, bot_instance)
                return False
                
        except Exception as e:
            logger.error(f"Error handling voice message: {e}")
            return False
    
    async def handle_audio(self, update: Dict, context: Any, bot_instance=None) -> bool:
        """
        Handle audio file
        
        Args:
            update: Telegram update object
            context: Telegram context
            bot_instance: Instance of bot for summarization
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            audio = update.get('message', {}).get('audio')
            if not audio:
                return False
            
            chat_id = update['message']['chat']['id']
            user_id = update['message']['from']['id']
            
            logger.info(f"Processing audio file from user {user_id}")
            
            # Check if audio processing is enabled
            if not self.config['AUDIO_SUMMARY_ENABLED']:
                await self._send_message(chat_id, "🔇 Обработка аудио временно отключена", bot_instance)
                return False
            
            # Check file size
            file_size = audio.get('file_size', 0)
            max_size = self.config['MAX_FILE_SIZE_MB'] * 1024 * 1024
            
            if file_size > max_size:
                await self._send_message(
                    chat_id,
                    f"❌ Файл слишком большой ({file_size/1024/1024:.1f}MB)\n"
                    f"Максимальный размер: {self.config['MAX_FILE_SIZE_MB']}MB",
                    bot_instance
                )
                return False
            
            # Check duration limit
            duration = audio.get('duration', 0)
            max_duration = self.config['ASR_MAX_DURATION_MIN'] * 60
            
            if duration > max_duration:
                await self._send_message(
                    chat_id,
                    f"❌ Аудио слишком длинное ({duration//60}:{duration%60:02d})\n"
                    f"Максимальная длительность: {self.config['ASR_MAX_DURATION_MIN']} минут",
                    bot_instance
                )
                return False
            
            # Get file info
            file_name = audio.get('file_name', 'audio')
            mime_type = audio.get('mime_type', '')
            
            # Send processing message
            processing_msg = await self._send_message(
                chat_id,
                f"🎵 Получил аудиофайл ({file_name}), обрабатываю... (≈{duration}с)",
                bot_instance
            )
            
            # Process the audio file
            result = await self._process_audio_file(
                audio['file_id'],
                'audio',
                duration,
                chat_id,
                user_id,
                bot_instance
            )
            
            if result:
                # Edit processing message with result
                if processing_msg:
                    await self._edit_message(chat_id, processing_msg, result['response_text'], bot_instance)
                else:
                    await self._send_message(chat_id, result['response_text'], bot_instance)
                
                # Send transcription file if available
                if result['transcription_file']:
                    await self._send_document(chat_id, result['transcription_file'], bot_instance)
                
                return True
            else:
                error_msg = "❌ Не удалось обработать аудиофайл\n\nПопробуйте другой файл или обратитесь к администратору."
                if processing_msg:
                    await self._edit_message(chat_id, processing_msg, error_msg, bot_instance)
                else:
                    await self._send_message(chat_id, error_msg, bot_instance)
                return False
                
        except Exception as e:
            logger.error(f"Error handling audio file: {e}")
            return False
    
    async def handle_video_note(self, update: Dict, context: Any, bot_instance=None) -> bool:
        """
        Handle video note (circle video message)
        
        Args:
            update: Telegram update object
            context: Telegram context
            bot_instance: Instance of bot for summarization
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            video_note = update.get('message', {}).get('video_note')
            if not video_note:
                return False
            
            chat_id = update['message']['chat']['id']
            user_id = update['message']['from']['id']
            
            logger.info(f"Processing video note from user {user_id}")
            
            # Check if audio processing is enabled
            if not self.config['AUDIO_SUMMARY_ENABLED']:
                await self._send_message(chat_id, "🔇 Обработка аудио временно отключена", bot_instance)
                return False
            
            # Check duration limit
            duration = video_note.get('duration', 0)
            max_duration = self.config['ASR_MAX_DURATION_MIN'] * 60
            
            if duration > max_duration:
                await self._send_message(
                    chat_id,
                    f"❌ Видео слишком длинное ({duration//60}:{duration%60:02d})\n"
                    f"Максимальная длительность: {self.config['ASR_MAX_DURATION_MIN']} минут",
                    bot_instance
                )
                return False
            
            # Send processing message
            processing_msg = await self._send_message(
                chat_id,
                f"🎥 Получил видеосообщение, извлекаю аудио... (≈{duration}с)",
                bot_instance
            )
            
            # Process the video note (extract audio)
            result = await self._process_audio_file(
                video_note['file_id'],
                'video_note',
                duration,
                chat_id,
                user_id,
                bot_instance
            )
            
            if result:
                # Edit processing message with result
                if processing_msg:
                    await self._edit_message(chat_id, processing_msg, result['response_text'], bot_instance)
                else:
                    await self._send_message(chat_id, result['response_text'], bot_instance)
                
                # Send transcription file if available
                if result['transcription_file']:
                    await self._send_document(chat_id, result['transcription_file'], bot_instance)
                
                return True
            else:
                error_msg = "❌ Не удалось обработать видеосообщение\n\nПопробуйте другое видео или обратитесь к администратору."
                if processing_msg:
                    await self._edit_message(chat_id, processing_msg, error_msg, bot_instance)
                else:
                    await self._send_message(chat_id, error_msg, bot_instance)
                return False
                
        except Exception as e:
            logger.error(f"Error handling video note: {e}")
            return False
    
    async def _process_audio_file(
        self,
        file_id: str,
        file_type: str,
        duration: int,
        chat_id: int,
        user_id: int,
        bot_instance=None
    ) -> Optional[Dict[str, Any]]:
        """
        Main audio processing pipeline
        
        Args:
            file_id: Telegram file ID
            file_type: Type of file ('voice', 'audio', 'video_note')
            duration: Duration in seconds
            chat_id: Chat ID for updates
            user_id: User ID for logging
            bot_instance: Bot instance for summarization
            
        Returns:
            Processing result dictionary or None if failed
        """
        temp_dir = None
        temp_files = []
        
        try:
            # Create temporary directory
            temp_dir = self.downloader.create_temp_dir()
            
            logger.info(f"Starting audio processing pipeline for {file_type}")
            
            # Step 1: Download file
            logger.info("Step 1: Downloading file...")
            download_result = await self.downloader.download_with_metadata(file_id, temp_dir)
            original_file = download_result['file_path']
            temp_files.append(original_file)
            
            # Step 2: Convert to WAV if needed
            logger.info("Step 2: Converting to WAV format...")
            wav_file = os.path.join(temp_dir, "converted.wav")
            
            if file_type == 'video_note':
                # Extract audio from video first
                audio_file = os.path.join(temp_dir, "extracted_audio.wav")
                extract_audio(original_file, audio_file, self.config['FFMPEG_PATH'])
                temp_files.append(audio_file)
                to_wav_16k_mono(audio_file, wav_file, self.config['FFMPEG_PATH'])
            else:
                to_wav_16k_mono(original_file, wav_file, self.config['FFMPEG_PATH'])
            
            temp_files.append(wav_file)
            
            # Step 3: Segment if necessary
            logger.info("Step 3: Segmenting audio if needed...")
            segments = await self.segmenter.segment_audio(
                wav_file,
                enable_vad=self.config['ASR_VAD_ENABLED'],
                target_len_sec=45,
                overlap_sec=5
            )
            temp_files.extend(segments)
            
            # Step 4: Transcribe
            logger.info("Step 4: Transcribing audio...")
            transcription_results = []
            
            for i, segment_path in enumerate(segments):
                logger.info(f"Transcribing segment {i+1}/{len(segments)}")
                
                try:
                    result = await transcribe_with_whisper(
                        segment_path,
                        language_hint=None,  # Let Whisper detect language
                        model_size=self.config['WHISPER_MODEL_SIZE']
                    )
                    transcription_results.append(result)
                except Exception as e:
                    logger.error(f"Failed to transcribe segment {i+1}: {e}")
                    continue
            
            if not transcription_results:
                raise Exception("No transcription results obtained")
            
            # Step 5: Combine transcriptions
            logger.info("Step 5: Combining transcription results...")
            combined_result = self._combine_transcription_results(transcription_results)
            
            full_text = combined_result['text']
            if not validate_summarization_input(full_text):
                raise Exception("Transcription too short or invalid for summarization")
            
            # Step 6: Summarize
            logger.info("Step 6: Generating summary...")
            summary = await run_summarization_with_bot_instance(
                bot_instance,
                full_text,
                target_ratio=self.config['DEFAULT_COMPRESSION_RATIO']
            )
            
            # Step 7: Prepare response
            logger.info("Step 7: Preparing response...")
            metadata = {
                'language': combined_result.get('language', 'неизвестен'),
                'duration_sec': combined_result.get('duration_sec', duration),
                'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'segments_count': len(segments),
                'file_type': file_type
            }
            
            result = prepare_audio_summary_response(
                summary=summary,
                transcription=full_text,
                metadata=metadata,
                create_file=True
            )
            
            logger.info(f"Audio processing completed successfully for user {user_id}")
            return result
            
        except Exception as e:
            logger.error(f"Audio processing failed: {e}")
            return None
            
        finally:
            # Cleanup temporary files
            self._cleanup_temp_files(temp_files, temp_dir)
    
    def _combine_transcription_results(self, results: List[Dict]) -> Dict[str, Any]:
        """Combine multiple transcription results into one"""
        if not results:
            return {"text": "", "language": None, "duration_sec": 0}
        
        # Combine text
        full_text = " ".join(result.get('text', '') for result in results if result.get('text'))
        
        # Get most common language
        languages = [result.get('language') for result in results if result.get('language')]
        language = max(set(languages), key=languages.count) if languages else None
        
        # Sum durations
        total_duration = sum(result.get('duration_sec', 0) for result in results if result.get('duration_sec'))
        
        # Average confidence
        probs = [result.get('avg_prob') for result in results if result.get('avg_prob')]
        avg_prob = sum(probs) / len(probs) if probs else None
        
        return {
            "text": full_text.strip(),
            "language": language,
            "duration_sec": total_duration,
            "avg_prob": avg_prob,
            "segments_count": len(results)
        }
    
    def _cleanup_temp_files(self, temp_files: List[str], temp_dir: Optional[str]):
        """Clean up temporary files and directory"""
        try:
            # Clean up individual files
            for file_path in temp_files:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logger.warning(f"Failed to remove temp file {file_path}: {e}")
            
            # Clean up directory
            if temp_dir:
                self.downloader.cleanup_temp_dir(temp_dir)
                
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
    
    # Helper methods for bot communication
    async def _send_message(self, chat_id: int, text: str, bot_instance=None) -> Optional[int]:
        """Send message via bot instance"""
        if bot_instance and hasattr(bot_instance, 'send_message'):
            try:
                response = await bot_instance.send_message(chat_id, text)
                if response and response.get('ok'):
                    return response['result']['message_id']
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
        return None
    
    async def _edit_message(self, chat_id: int, message_id: int, text: str, bot_instance=None):
        """Edit message via bot instance"""
        if bot_instance and hasattr(bot_instance, 'edit_message'):
            try:
                await bot_instance.edit_message(chat_id, message_id, text)
            except Exception as e:
                logger.error(f"Failed to edit message: {e}")
    
    async def _send_document(self, chat_id: int, file_path: str, bot_instance=None):
        """Send document via bot instance"""
        if bot_instance and hasattr(bot_instance, 'send_document'):
            try:
                await bot_instance.send_document(chat_id, file_path)
                # Clean up file after sending
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.error(f"Failed to send document: {e}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get status of audio processing system"""
        return {
            "audio_enabled": self.config['AUDIO_SUMMARY_ENABLED'],
            "ffmpeg_available": check_ffmpeg_available(self.config['FFMPEG_PATH']),
            "whisper_status": check_whisper_installation(),
            "vad_status": self.segmenter.get_vad_status(),
            "config": {
                "max_duration_min": self.config['ASR_MAX_DURATION_MIN'],
                "max_file_size_mb": self.config['MAX_FILE_SIZE_MB'],
                "whisper_model": self.config['WHISPER_MODEL_SIZE'],
                "vad_enabled": self.config['ASR_VAD_ENABLED']
            }
        }