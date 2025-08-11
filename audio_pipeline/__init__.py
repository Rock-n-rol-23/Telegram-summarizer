"""
Audio processing pipeline for Railway production
Production-ready audio handler with multi-engine ASR support
"""

from .audio_handler import ProductionAudioHandler
from .downloader import download_audio_async, download_audio
from .file_extractor import extract_audio_file_id_and_kind, get_audio_metadata
from .vosk_transcriber import transcribe_audio, get_available_engines

__version__ = "3.0.0"
__all__ = [
    "ProductionAudioHandler",
    "download_audio_async", 
    "download_audio",
    "extract_audio_file_id_and_kind",
    "get_audio_metadata",
    "transcribe_audio",
    "get_available_engines"
]