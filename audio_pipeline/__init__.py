"""
Audio processing pipeline for Telegram bot
Handles voice messages, audio files, and video notes with transcription and summarization
"""

from .handler import AudioHandler
from .downloader import TelegramAudioDownloader
from .transcriber_adapter import transcribe_with_whisper
from .segmenter import AudioSegmenter

__all__ = [
    'AudioHandler',
    'TelegramAudioDownloader', 
    'transcribe_with_whisper',
    'AudioSegmenter'
]