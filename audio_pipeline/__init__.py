"""
Audio processing pipeline for Telegram bot
Handles voice messages, audio files, and video notes with transcription and summarization
"""

from .handler import AudioHandler
from .downloader import TelegramAudioDownloader, extract_file_id, download_audio, get_audio_metadata
from .transcriber_adapter import transcribe_with_whisper
from .transcriber import transcribe_audio, get_available_engines
from .segmenter import AudioSegmenter
from .new_handler import handle_voice, handle_audio, handle_video_note

__all__ = [
    'AudioHandler',
    'TelegramAudioDownloader', 
    'transcribe_with_whisper',
    'transcribe_audio',
    'AudioSegmenter',
    'extract_file_id',
    'download_audio',
    'get_audio_metadata',
    'get_available_engines',
    'handle_voice',
    'handle_audio', 
    'handle_video_note'
]