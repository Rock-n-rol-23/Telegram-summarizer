# audio_processor.py
import os
import io
import tempfile
import logging
import asyncio
import aiohttp
import aiofiles
import math
import subprocess
import shutil
from typing import Dict, Any, Optional, List, Tuple
from groq import Groq

# --- ADD: make pydub use bundled ffmpeg ---
from utils.ffmpeg import ensure_ffmpeg
FFMPEG_BIN = ensure_ffmpeg()

# Проброс для pydub
from pydub import AudioSegment
AudioSegment.converter = FFMPEG_BIN
AudioSegment.ffmpeg = FFMPEG_BIN
# AudioSegment.ffprobe = FFMPEG_BIN  # Не нужно - pydub не использует этот атрибут

# Чтобы subprocess/другие либы находили бинарь
os.environ["FFMPEG_BINARY"] = FFMPEG_BIN
os.environ["PATH"] = os.path.dirname(FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")
# --- END ADD ---

logger = logging.getLogger(__name__)
logger.info(f"Using ffmpeg binary at: {FFMPEG_BIN}")

SUPPORTED_EXTS = {".ogg", ".oga", ".mp3", ".m4a", ".wav", ".flac", ".webm", ".aac"}

class AudioProcessor:
    def __init__(self, groq_client: Groq, max_file_size_mb: int = 50):
        self.groq = groq_client
        self.max_mb = max_file_size_mb

    async def download_telegram_file(self, file_url: str, dst_path: str) -> None:
        """Скачивает файл из Telegram через aiohttp"""
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600)) as session:
            async with session.get(file_url) as resp:
                resp.raise_for_status()
                async with aiofiles.open(dst_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        await f.write(chunk)

    def _convert_to_wav16k_mono(self, src_path: str, dst_path: str) -> Tuple[float, int]:
        """Конвертация через ffmpeg + возврат (длительность_сек, битрейт_Гц)."""
        ffmpeg = FFMPEG_BIN  # вместо строкового 'ffmpeg'
        cmd = [ffmpeg, "-y", "-i", src_path, "-ac", "1", "-ar", "16000", "-vn", dst_path]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        audio = AudioSegment.from_wav(dst_path)
        duration = len(audio) / 1000.0
        return duration, 16000

    def _split_wav(self, wav_path: str, chunk_secs: int = 600) -> List[str]:
        """Режем на куски по chunk_secs секунд, возвращаем пути к кускам."""
        audio = AudioSegment.from_wav(wav_path)
        chunks = []
        for i in range(0, len(audio), chunk_secs * 1000):
            chunk = audio[i:i + chunk_secs * 1000]
            out_path = wav_path.replace(".wav", f".part{i//1000:04d}.wav")
            chunk.export(out_path, format="wav", parameters=["-ac", "1", "-ar", "16000"])
            chunks.append(out_path)
        return chunks

    async def transcribe_wav(self, wav_path: str) -> str:
        """Транскрипция одним вызовом Groq Whisper для одного файла."""
        with open(wav_path, "rb") as f:
            res = self.groq.audio.transcriptions.create(
                file=("audio.wav", f, "audio/wav"),
                model="whisper-large-v3",
                response_format="verbose_json",
                temperature=0.0
            )
        # res.text содержит текст, res.language — язык, если verbose_json
        text = getattr(res, "text", "") or ""
        return text.strip()

    async def process_audio_from_telegram(self, file_url: str, filename_hint: str) -> Dict[str, Any]:
        """Основной метод обработки аудио из Telegram"""
        if not filename_hint:
            filename_hint = "audio.ogg"
        _, ext = os.path.splitext(filename_hint.lower())
        if ext not in SUPPORTED_EXTS:
            return {"success": False, "error": f"Неподдерживаемый формат: {ext}. Поддерживаемые: {', '.join(sorted(SUPPORTED_EXTS))}"}

        tmp_dir = tempfile.mkdtemp(prefix="tg_audio_")
        original_path = os.path.join(tmp_dir, f"orig{ext or '.bin'}")
        wav_path = os.path.join(tmp_dir, "audio.wav")

        try:
            await self.download_telegram_file(file_url, original_path)

            size_mb = os.path.getsize(original_path) / (1024 * 1024)
            if size_mb > self.max_mb:
                return {"success": False, "error": f"Аудио слишком большое ({size_mb:.1f}MB), лимит {self.max_mb}MB"}

            # Конвертируем в WAV 16kHz mono
            duration, _ = self._convert_to_wav16k_mono(original_path, wav_path)

            # Если длительное — режем и транскрибируем по кускам
            chunk_paths = self._split_wav(wav_path, chunk_secs=600) if duration > 620 else [wav_path]

            parts = []
            for cp in chunk_paths:
                text = await self.transcribe_wav(cp)
                if text:
                    parts.append(text)

            if not parts:
                return {"success": False, "error": "Не удалось распознать речь."}

            transcript = "\n".join(parts)
            return {
                "success": True,
                "transcript": transcript,
                "duration_sec": duration,
                "tmp_dir": tmp_dir
            }
        except Exception as e:
            logger.exception("Ошибка обработки аудио")
            # Специальная обработка ошибок FFmpeg
            if isinstance(e, FileNotFoundError) and "ffmpeg" in str(e).lower():
                return {"success": False, "error": "FFmpeg не найден или не запускается. Обратитесь к администратору."}
            elif isinstance(e, subprocess.CalledProcessError):
                return {"success": False, "error": f"Ошибка конвертации аудио (FFmpeg): {e}"}
            else:
                return {"success": False, "error": f"Ошибка обработки аудио: {e}"}
        finally:
            # Очистка временных файлов
            try:
                if os.path.exists(tmp_dir):
                    shutil.rmtree(tmp_dir)
            except Exception as e:
                logger.warning(f"Не удалось удалить временную директорию {tmp_dir}: {e}")

    def cleanup_temp_file(self, temp_dir: str):
        """Очищает временные файлы (обратная совместимость)"""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            logger.warning(f"Не удалось удалить временную директорию {temp_dir}: {e}")

    # Старые методы для обратной совместимости
    def transcribe_audio(self, file_path: str) -> Dict[str, Any]:
        """Синхронная обертка для транскрипции (обратная совместимость)"""
        try:
            loop = asyncio.get_event_loop()
            text = loop.run_until_complete(self.transcribe_wav(file_path))
            return {
                'success': True,
                'text': text,
                'method': 'Groq Whisper API'
            }
        except Exception as e:
            logger.error(f"Ошибка транскрипции: {e}")
            return {
                'success': False,
                'error': f'Ошибка транскрипции: {str(e)}'
            }

    async def download_telegram_audio(self, file_info: Dict[str, Any], file_name: str, file_size: int) -> Dict[str, Any]:
        """Старый метод для обратной совместимости"""
        try:
            file_url = file_info.get('file_path', '')
            if not file_url:
                return {'success': False, 'error': 'Неверная информация о файле'}

            tmp_dir = tempfile.mkdtemp(prefix="tg_audio_")
            local_file_path = os.path.join(tmp_dir, file_name)

            await self.download_telegram_file(file_url, local_file_path)

            return {
                'success': True,
                'file_path': local_file_path,
                'temp_dir': tmp_dir
            }
        except Exception as e:
            logger.error(f"Ошибка скачивания аудио: {e}")
            return {
                'success': False,
                'error': f'Ошибка при скачивании аудио: {str(e)}'
            }