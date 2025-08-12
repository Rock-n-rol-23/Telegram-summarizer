import os
import tempfile
import logging
import aiofiles
import aiohttp
import subprocess
import shutil
from typing import Dict, Any, Optional
import speech_recognition as sr
from groq import Groq

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Класс для обработки аудио файлов и транскрипции речи в текст"""
    
    def __init__(self, groq_client: Optional[Groq] = None):
        self.supported_extensions = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.opus', '.wma']
        self.max_file_size = 50 * 1024 * 1024  # 50MB для аудио
        self.max_duration = 3600  # Максимум 1 час
        
        # Инициализируем распознаватель речи
        self.recognizer = sr.Recognizer()
        
        # Groq клиент для транскрипции
        self.groq_client = groq_client
        
        # Проверяем наличие ffmpeg
        self.ffmpeg_available = self._check_ffmpeg()
        if not self.ffmpeg_available:
            logger.warning("FFmpeg не найден - конвертация аудио недоступна")
        
    def _check_ffmpeg(self) -> bool:
        """Проверяет наличие ffmpeg в системе"""
        try:
            # Сначала пробуем найти ffmpeg через which
            ffmpeg_path = shutil.which('ffmpeg')
            if ffmpeg_path:
                subprocess.run([ffmpeg_path, '-version'], capture_output=True, check=True)
                logger.info(f"FFmpeg найден: {ffmpeg_path}")
                return True
            else:
                # Пробуем прямо вызвать ffmpeg
                subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
                logger.info("FFmpeg найден в PATH")
                return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"FFmpeg не найден: {e}")
            return False
    
    async def download_telegram_audio(self, file_info: Dict[str, Any], file_name: str, file_size: int) -> Dict[str, Any]:
        """Скачивает аудио файл от Telegram бота"""
        try:
            # Проверяем размер файла
            if file_size > self.max_file_size:
                return {
                    'success': False,
                    'error': f'Аудио файл слишком большой (максимум {self.max_file_size // 1024 // 1024}MB)'
                }
            
            # Проверяем расширение файла
            file_extension = os.path.splitext(file_name.lower())[1]
            if file_extension not in self.supported_extensions:
                return {
                    'success': False,
                    'error': f'Неподдерживаемый формат аудио. Поддерживаются: {", ".join(self.supported_extensions)}'
                }
            
            # Создаем временную директорию
            temp_dir = tempfile.mkdtemp()
            local_file_path = os.path.join(temp_dir, file_name)
            
            # Скачиваем файл
            async with aiohttp.ClientSession() as session:
                async with session.get(file_info['file_path']) as response:
                    if response.status == 200:
                        async with aiofiles.open(local_file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                    else:
                        return {
                            'success': False,
                            'error': f'Ошибка скачивания аудио: HTTP {response.status}'
                        }
            
            return {
                'success': True,
                'file_path': local_file_path,
                'file_name': file_name,
                'file_size': file_size,
                'file_extension': file_extension,
                'temp_dir': temp_dir
            }
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании аудио: {e}")
            return {
                'success': False,
                'error': f'Ошибка при скачивании аудио: {str(e)}'
            }
    
    def convert_to_wav(self, input_path: str, output_path: str) -> Dict[str, Any]:
        """Конвертирует аудио в формат WAV для обработки"""
        if not self.ffmpeg_available:
            return {
                'success': False,
                'error': 'FFmpeg недоступен для конвертации аудио'
            }
        
        try:
            logger.info(f"🎵 Конвертация аудио: {input_path} -> {output_path}")
            
            # Получаем путь к ffmpeg
            ffmpeg_path = shutil.which('ffmpeg') or 'ffmpeg'
            
            # Команда ffmpeg для конвертации в WAV с настройками для речи
            cmd = [
                ffmpeg_path, '-i', input_path,
                '-ar', '16000',  # 16kHz sample rate (хорошо для речи)
                '-ac', '1',      # Моно
                '-c:a', 'pcm_s16le',  # 16-bit PCM
                '-y',            # Перезаписать выходной файл
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"🎵 Конвертация завершена успешно")
                return {
                    'success': True,
                    'output_path': output_path
                }
            else:
                logger.error(f"🎵 Ошибка конвертации: {result.stderr}")
                return {
                    'success': False,
                    'error': f'Ошибка конвертации аудио: {result.stderr}'
                }
                
        except Exception as e:
            logger.error(f"🎵 Критическая ошибка конвертации: {e}")
            return {
                'success': False,
                'error': f'Критическая ошибка конвертации: {str(e)}'
            }
    
    def get_audio_duration(self, file_path: str) -> float:
        """Получает длительность аудио файла в секундах"""
        if not self.ffmpeg_available:
            return 0.0
        
        try:
            # Получаем путь к ffprobe
            ffprobe_path = shutil.which('ffprobe') or 'ffprobe'
            
            cmd = [
                ffprobe_path, '-v', 'quiet', '-show_entries', 
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                return duration
            else:
                logger.warning(f"Не удалось получить длительность аудио: {result.stderr}")
                return 0.0
                
        except Exception as e:
            logger.warning(f"Ошибка получения длительности аудио: {e}")
            return 0.0
    
    def transcribe_audio(self, file_path: str) -> Dict[str, Any]:
        """Транскрибирует аудио в текст используя SpeechRecognition"""
        try:
            logger.info(f"🎤 Начинаю транскрипцию аудио: {file_path}")
            
            # Получаем длительность аудио
            duration = self.get_audio_duration(file_path)
            if duration > self.max_duration:
                return {
                    'success': False,
                    'error': f'Аудио слишком длинное ({duration/60:.1f} мин). Максимум: {self.max_duration/60} мин'
                }
            
            # Определяем нужно ли конвертировать файл
            file_extension = os.path.splitext(file_path)[1].lower()
            wav_path = file_path
            
            # Если файл не WAV, конвертируем его
            if file_extension != '.wav':
                temp_wav = file_path.replace(file_extension, '_converted.wav')
                conversion_result = self.convert_to_wav(file_path, temp_wav)
                
                if not conversion_result['success']:
                    return conversion_result
                
                wav_path = temp_wav
            
            # Транскрибируем аудио
            logger.info(f"🎤 Загружаю аудио файл для распознавания...")
            with sr.AudioFile(wav_path) as source:
                # Настраиваем распознаватель на шум
                self.recognizer.adjust_for_ambient_noise(source)
                logger.info(f"🎤 Записываю аудио...")
                audio = self.recognizer.record(source)
            
            # Пробуем несколько методов распознавания
            transcription_methods = []
            
            # Groq Whisper - приоритетный метод если доступен
            if self.groq_client:
                transcription_methods.append(('Groq Whisper API', lambda audio: self._transcribe_with_groq_whisper(wav_path)))
            
            transcription_methods.extend([
                ('Google Speech Recognition', self._transcribe_with_google),
                ('Sphinx (offline)', self._transcribe_with_sphinx),
            ])
            
            for method_name, method_func in transcription_methods:
                try:
                    logger.info(f"🎤 Пробую {method_name}...")
                    text = method_func(audio)
                    
                    if text and len(text.strip()) > 0:
                        logger.info(f"🎤 Транскрипция успешна через {method_name}: {len(text)} символов")
                        
                        # Очищаем временный WAV файл если создавали
                        if wav_path != file_path and os.path.exists(wav_path):
                            os.remove(wav_path)
                        
                        return {
                            'success': True,
                            'text': text.strip(),
                            'method': method_name,
                            'duration': duration
                        }
                        
                except Exception as e:
                    logger.warning(f"🎤 {method_name} не сработал: {e}")
                    continue
            
            # Если все методы не сработали
            return {
                'success': False,
                'error': 'Не удалось распознать речь ни одним из доступных методов'
            }
            
        except Exception as e:
            logger.error(f"🎤 Критическая ошибка транскрипции: {e}")
            return {
                'success': False,
                'error': f'Критическая ошибка транскрипции: {str(e)}'
            }
    
    def _transcribe_with_google(self, audio) -> str:
        """Транскрипция через Google Speech Recognition (бесплатно, с лимитами)"""
        return self.recognizer.recognize_google(audio, language='ru-RU')
    
    def _transcribe_with_sphinx(self, audio) -> str:
        """Транскрипция через CMU Sphinx (офлайн, бесплатно)"""
        return self.recognizer.recognize_sphinx(audio)
    
    def _transcribe_with_groq_whisper(self, audio_file_path: str) -> str:
        """Транскрипция через Groq Whisper API"""
        try:
            with open(audio_file_path, 'rb') as file:
                transcription = self.groq_client.audio.transcriptions.create(
                    file=(os.path.basename(audio_file_path), file.read()),
                    model="whisper-large-v3",
                    language="ru",
                    response_format="text"
                )
                return transcription
        except Exception as e:
            logger.error(f"Groq Whisper транскрипция не удалась: {e}")
            raise e
    
    def cleanup_temp_file(self, temp_dir: str):
        """Очищает временные файлы"""
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"🎵 Временная аудио директория удалена: {temp_dir}")
        except Exception as e:
            logger.error(f"🎵 Ошибка при удалении временной аудио директории {temp_dir}: {e}")