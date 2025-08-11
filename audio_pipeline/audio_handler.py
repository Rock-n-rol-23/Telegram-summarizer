"""
Полноценный аудио хендлер для Railway продакшна
Поддерживает voice, audio, document-audio, video_note
"""
import os
import tempfile
import time
import logging
import shutil
from typing import Optional

from .file_extractor import extract_audio_file_id_and_kind, get_audio_metadata
from .downloader import download_audio_async
from .vosk_transcriber import transcribe_audio
from utils.ffmpeg import to_wav_16k_mono, is_ffmpeg_available

logger = logging.getLogger(__name__)

class ProductionAudioHandler:
    """Продакшн аудио хендлер с полным пайплайном"""
    
    def __init__(self):
        """Инициализация с проверками"""
        self.enabled = os.getenv('AUDIO_SUMMARY_ENABLED', 'true').lower() == 'true'
        self.max_duration = int(os.getenv('ASR_MAX_DURATION_MIN', '20')) * 60  # секунды
        self.max_file_size = int(os.getenv('AUDIO_MAX_FILE_SIZE_MB', '50')) * 1024 * 1024  # байты
        
        # Проверки при инициализации
        if not is_ffmpeg_available():
            logger.error("❌ FFmpeg не найден! Добавьте в nixpacks.toml: nixPkgs = ['ffmpeg']")
        else:
            logger.info("✅ FFmpeg доступен")
            
        logger.info(f"ProductionAudioHandler: enabled={self.enabled}, max_duration={self.max_duration}s")

    async def process_audio_message(self, bot, update, context):
        """
        Главный метод обработки аудио сообщений
        Поддерживает voice, audio, document-audio, video_note
        """
        message = update.message if hasattr(update, 'message') else update.get('message')
        if not message:
            logger.error("Сообщение не найдено в update")
            return
            
        chat_id = message.get('chat', {}).get('id') if isinstance(message, dict) else message.chat_id
        if not chat_id:
            logger.error("chat_id не найден")
            return
        
        status_msg = None
        temp_files = []
        
        try:
            # Шаг 1: Отправляем заглушку и сохраняем message_id
            status_msg = await bot.send_message(chat_id, "🎤 Получил аудио, обрабатываю...")
            status_msg_id = status_msg.get("result", {}).get("message", {}).get("message_id") if status_msg else None
            
            # Шаг 2: Извлекаем file_id и тип
            try:
                file_id, kind = extract_audio_file_id_and_kind(message)
                metadata = get_audio_metadata(message, kind)
                logger.info(f"Аудио обнаружено: {kind}, file_id={file_id}, metadata={metadata}")
            except ValueError as e:
                if status_msg_id:
                    await bot.edit_message_text(chat_id, status_msg_id, f"❌ {str(e)}")
                return
            
            # Шаг 3: Проверки размера и длительности
            file_size = metadata.get('file_size', 0)
            duration = metadata.get('duration', 0)
            
            if file_size > self.max_file_size:
                error_msg = f"❌ Файл слишком большой: {file_size/(1024*1024):.1f}MB (макс: {self.max_file_size/(1024*1024)}MB)"
                if status_msg_id:
                    await bot.edit_message_text(chat_id, status_msg_id, error_msg)
                return
                
            if duration > self.max_duration:
                error_msg = f"❌ Аудио слишком длинное: {duration//60}:{duration%60:02d} (макс: {self.max_duration//60}:{self.max_duration%60:02d})"
                if status_msg_id:
                    await bot.edit_message_text(chat_id, status_msg_id, error_msg)
                return
            
            # Шаг 4: Скачиваем файл
            if status_msg_id:
                await bot.edit_message_text(chat_id, status_msg_id, "📥 Скачиваю файл...")
                
            temp_dir = tempfile.mkdtemp()
            raw_path = await download_audio_async(bot, file_id, temp_dir)
            if not raw_path:
                if status_msg_id:
                    await bot.edit_message_text(chat_id, status_msg_id, "❌ Ошибка скачивания файла")
                return
            temp_files.append(raw_path)
            
            # Шаг 5: Конвертируем в WAV 16kHz mono
            if status_msg_id:
                await bot.edit_message_text(chat_id, status_msg_id, "🔧 Нормализую аудио...")
                
            wav_path = os.path.join(temp_dir, f"normalized_{int(time.time())}.wav")
            if not to_wav_16k_mono(raw_path, wav_path):
                if status_msg_id:
                    await bot.edit_message_text(chat_id, status_msg_id, "❌ Ошибка конвертации аудио")
                return
            temp_files.append(wav_path)
            
            # Шаг 6: Транскрибируем
            if status_msg_id:
                await bot.edit_message_text(chat_id, status_msg_id, "🎯 Распознаю речь...")
                
            asr_result = transcribe_audio(wav_path, language_hint=None)
            
            # Шаг 7: Проверяем результат транскрипции
            if asr_result.get("error"):
                error_msg = f"❌ {asr_result['error']}\n\n📋 Для установки ASR движков:\n• `pip install vosk==0.3.45`\n• `pip install transformers torch`"
                if status_msg_id:
                    await bot.edit_message_text(chat_id, status_msg_id, error_msg)
                return
                
            transcript = asr_result.get("text", "").strip()
            if not transcript:
                error_msg = "❌ Речь не распознана.\n\n🔧 Возможные причины:\n• ASR движок не установлен\n• Низкое качество записи\n• Тихая речь"
                if status_msg_id:
                    await bot.edit_message_text(chat_id, status_msg_id, error_msg)
                return
            
            # Шаг 8: Суммаризация
            if status_msg_id:
                await bot.edit_message_text(chat_id, status_msg_id, "📝 Создаю саммари...")
            
            # Используем встроенный суммаризатор бота
            if hasattr(bot, 'summarize_text'):
                summary = await bot.summarize_text(transcript)
            else:
                # Простое резюме если суммаризатор недоступен
                sentences = transcript.split('.')[:3]
                summary = '. '.join(sentences)[:500] + "..."
            
            # Шаг 9: Отправляем результат
            mime_type = metadata.get('mime_type', 'audio/unknown')
            engine = asr_result.get('engine', 'unknown')
            
            response = f"""🎤 **Саммари аудио** ({kind})

📋 **Резюме:**
{summary}

📊 **Статистика:**
• Формат: {mime_type}
• Размер: {file_size/(1024*1024):.1f}MB
• Длительность: {duration//60}:{duration%60:02d}
• Распознано: {len(transcript)} символов
• ASR движок: {engine}
• Компрессия: ~{int(len(summary)/len(transcript)*100) if transcript else 0}%"""

            if status_msg_id:
                await bot.edit_message_text(chat_id, status_msg_id, response, parse_mode="Markdown")
            
            # Шаг 10: Отправляем полную транскрипцию как файл
            try:
                transcript_path = os.path.join(temp_dir, f"transcript_{int(time.time())}.txt")
                with open(transcript_path, 'w', encoding='utf-8') as f:
                    f.write(f"Полная транскрипция аудио\n")
                    f.write(f"Тип: {kind}\n")
                    f.write(f"Формат: {mime_type}\n")
                    f.write(f"ASR движок: {engine}\n")
                    f.write(f"Длительность: {duration//60}:{duration%60:02d}\n")
                    f.write(f"\n--- ТРАНСКРИПЦИЯ ---\n\n")
                    f.write(transcript)
                
                await bot.send_document(chat_id, transcript_path, caption="📄 Полная транскрипция")
                temp_files.append(transcript_path)
                
            except Exception as e:
                logger.error(f"Ошибка отправки транскрипции: {e}")
            
            logger.info(f"Аудио успешно обработано: {len(transcript)} chars -> {len(summary)} chars")
            
        except Exception as e:
            logger.error(f"Ошибка обработки аудио: {e}")
            error_msg = f"❌ Ошибка обработки аудио: {str(e)[:100]}"
            try:
                if status_msg_id:
                    await bot.edit_message_text(chat_id, status_msg_id, error_msg)
                else:
                    await bot.send_message(chat_id, error_msg)
            except:
                pass  # Игнорируем ошибки отправки ошибок
                
        finally:
            # Очищаем временные файлы
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        if os.path.isfile(temp_file):
                            os.remove(temp_file)
                        elif os.path.isdir(temp_file):
                            shutil.rmtree(temp_file, ignore_errors=True)
                except:
                    pass

# Создаем глобальный экземпляр
_production_handler = ProductionAudioHandler()

# Хендлеры для интеграции с ботом
async def handle_voice_production(update, context):
    """Хендлер голосовых сообщений"""
    await _production_handler.process_audio_message(context.bot, update, context)

async def handle_audio_production(update, context):
    """Хендлер аудиофайлов"""
    await _production_handler.process_audio_message(context.bot, update, context)

async def handle_video_note_production(update, context):
    """Хендлер видеозаметок"""
    await _production_handler.process_audio_message(context.bot, update, context)

async def handle_document_audio_production(update, context):
    """Хендлер документов с audio/* mime-type"""
    await _production_handler.process_audio_message(context.bot, update, context)