"""
Простой аудио хендлер для Vosk + Railway
Быстрая интеграция с диагностикой
"""
import os
import logging
import tempfile
import shutil
from typing import Optional

from .vosk_transcriber import transcribe_audio, to_wav_16k_mono, check_ffmpeg

logger = logging.getLogger(__name__)

class SimpleAudioHandler:
    """Простой обработчик аудио для продакшна"""
    
    def __init__(self):
        """Инициализация с проверками"""
        self.enabled = os.getenv('AUDIO_SUMMARY_ENABLED', 'true').lower() == 'true'
        self.max_duration = int(os.getenv('ASR_MAX_DURATION_MIN', '20')) * 60  # секунды
        self.max_file_size = int(os.getenv('AUDIO_MAX_FILE_SIZE_MB', '50')) * 1024 * 1024  # байты
        
        # Проверки при инициализации
        if not check_ffmpeg():
            logger.error("❌ FFmpeg не найден! Добавьте в nixpacks.toml: nixPkgs = ['ffmpeg']")
        else:
            logger.info("✅ FFmpeg доступен")
            
        logger.info(f"SimpleAudioHandler: enabled={self.enabled}, max_duration={self.max_duration}s")

    def extract_file_id(self, message) -> Optional[str]:
        """Извлекаем file_id из voice/audio/video_note"""
        try:
            # Проверяем разные типы
            if hasattr(message, 'voice') and message.voice:
                file_id = message.voice.file_id
                logger.info(f"Voice message detected: {file_id}")
                return file_id
            elif hasattr(message, 'audio') and message.audio:
                file_id = message.audio.file_id  
                logger.info(f"Audio file detected: {file_id}")
                return file_id
            elif hasattr(message, 'video_note') and message.video_note:
                file_id = message.video_note.file_id
                logger.info(f"Video note detected: {file_id}")
                return file_id
            else:
                logger.warning("No audio file_id found in message")
                return None
                
        except Exception as e:
            logger.error(f"Error extracting file_id: {e}")
            return None

    async def download_file(self, bot, file_id: str) -> Optional[str]:
        """Скачиваем файл через Telegram API"""
        try:
            # Получаем информацию о файле
            file_info = await bot.get_file(file_id)
            
            # Проверяем размер
            if file_info.file_size > self.max_file_size:
                logger.warning(f"File too large: {file_info.file_size} bytes")
                return None
                
            # Создаем временный файл
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, f"audio_{file_id}")
            
            # Скачиваем файл
            await file_info.download_to_drive(file_path)
            logger.info(f"Downloaded: {file_path} ({file_info.file_size} bytes)")
            
            return file_path
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

    async def process_audio(self, bot, update, context):
        """Основная функция обработки аудио"""
        message = update.message
        chat_id = message.chat_id
        
        try:
            # Шаг 1: Извлекаем file_id
            file_id = self.extract_file_id(message)
            if not file_id:
                await context.bot.send_message(chat_id, "❌ Не удалось найти аудио файл")
                return

            # Шаг 2: Отправляем статус
            status_msg = await context.bot.send_message(chat_id, "🔄 Загружаю аудио...")

            # Шаг 3: Скачиваем файл
            audio_path = await self.download_file(context.bot, file_id)
            if not audio_path:
                await context.bot.edit_message_text(
                    "❌ Ошибка загрузки файла", chat_id, status_msg.message_id
                )
                return

            # Шаг 4: Конвертируем в WAV
            await context.bot.edit_message_text(
                "🔄 Конвертирую аудио...", chat_id, status_msg.message_id
            )
            
            wav_path = audio_path + ".wav"
            if not to_wav_16k_mono(audio_path, wav_path):
                await context.bot.edit_message_text(
                    "❌ Ошибка конвертации аудио", chat_id, status_msg.message_id
                )
                return

            # Шаг 5: Транскрибируем
            await context.bot.edit_message_text(
                "🔄 Распознаю речь...", chat_id, status_msg.message_id
            )
            
            result = transcribe_audio(wav_path)
            
            # Шаг 6: Проверяем результат
            if result.get("error"):
                error_msg = f"❌ {result['error']}\n\n📋 Для установки ASR движков:\n• `pip install vosk==0.3.45`\n• `pip install transformers torch`"
                await context.bot.edit_message_text(error_msg, chat_id, status_msg.message_id)
                return
                
            transcript = result.get("text", "").strip()
            if not transcript:
                await context.bot.edit_message_text(
                    "❌ Речь не распознана.\n\n🔧 Возможные причины:\n• ASR движок не установлен\n• Низкое качество записи\n• Тихая речь",
                    chat_id, status_msg.message_id
                )
                return

            # Шаг 7: Суммаризация (используем существующий механизм бота)
            await context.bot.edit_message_text(
                "🔄 Создаю саммари...", chat_id, status_msg.message_id
            )
            
            # Используем встроенный суммаризатор бота
            if hasattr(bot, 'summarize_text'):
                summary = await bot.summarize_text(transcript)
            else:
                # Простое резюме если суммаризатор недоступен
                sentences = transcript.split('.')[:3]
                summary = '. '.join(sentences)[:500] + "..."

            # Шаг 8: Отправляем результат
            response = f"🎤 **Саммари аудио:**\n\n{summary}\n\n"
            response += f"📊 _Распознано {len(transcript)} символов движком {result.get('engine', 'unknown')}_"
            
            await context.bot.edit_message_text(response, chat_id, status_msg.message_id, parse_mode='Markdown')
            
            logger.info(f"Audio processing completed: {len(transcript)} chars -> {len(summary)} chars")

        except Exception as e:
            logger.error(f"Audio processing error: {e}")
            error_msg = f"❌ Ошибка обработки аудио: {str(e)[:100]}"
            try:
                if 'status_msg' in locals():
                    await context.bot.edit_message_text(error_msg, chat_id, status_msg.message_id)
                else:
                    await context.bot.send_message(chat_id, error_msg)
            except:
                pass  # Игнорируем ошибки отправки ошибок
                
        finally:
            # Очищаем временные файлы
            try:
                if 'audio_path' in locals() and audio_path:
                    temp_dir = os.path.dirname(audio_path)
                    if temp_dir.startswith('/tmp'):
                        shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass

# Создаем глобальный экземпляр
_audio_handler = SimpleAudioHandler()

# Функции-хендлеры для интеграции
async def handle_voice(update, context):
    """Хендлер голосовых сообщений"""
    await _audio_handler.process_audio(context.bot, update, context)

async def handle_audio(update, context):
    """Хендлер аудиофайлов"""
    await _audio_handler.process_audio(context.bot, update, context)

async def handle_video_note(update, context):
    """Хендлер видеозаметок"""
    await _audio_handler.process_audio(context.bot, update, context)