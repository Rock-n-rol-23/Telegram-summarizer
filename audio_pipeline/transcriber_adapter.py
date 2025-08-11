"""
Whisper transcription adapter
Provides a unified interface to Whisper transcription functionality
Since no existing Whisper implementation was found, this creates a new one using OpenAI Whisper
"""

import logging
import os
import tempfile
from typing import Dict, Optional, List, Any
import asyncio

logger = logging.getLogger(__name__)

# Global variables for lazy loading
_whisper_model = None
_whisper_available = False

def _check_whisper_availability():
    """Check if Whisper is available and initialize if needed"""
    global _whisper_available
    try:
        import whisper
        _whisper_available = True
        logger.info("OpenAI Whisper is available")
        return True
    except ImportError:
        logger.warning("OpenAI Whisper not installed. Install with: pip install openai-whisper")
        _whisper_available = False
        return False

def _initialize_whisper_model(model_size: str = "base"):
    """Lazy initialization of Whisper model"""
    global _whisper_model
    
    if not _check_whisper_availability():
        return False
        
    if _whisper_model is None:
        try:
            import whisper
            logger.info(f"Loading Whisper model: {model_size}")
            _whisper_model = whisper.load_model(model_size)
            logger.info("Whisper model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            return False
    
    return True

async def transcribe_with_whisper(
    src_wav_path: str, 
    language_hint: Optional[str] = None,
    model_size: str = "base"
) -> Dict[str, Any]:
    """
    Transcribe audio file using Whisper
    
    Args:
        src_wav_path: Path to WAV audio file (should be 16kHz mono)
        language_hint: Optional language hint (e.g., 'ru', 'en')
        model_size: Whisper model size ('tiny', 'base', 'small', 'medium', 'large')
    
    Returns:
        Dictionary with transcription results:
        {
            "text": str,                    # Full transcribed text
            "language": str | None,         # Detected language
            "duration_sec": float | None,   # Audio duration
            "segments": list | None,        # Segment-level transcription
            "avg_prob": float | None        # Average confidence probability
        }
    """
    result = {
        "text": "",
        "language": None,
        "duration_sec": None,
        "segments": None,
        "avg_prob": None
    }
    
    if not os.path.exists(src_wav_path):
        raise FileNotFoundError(f"Audio file not found: {src_wav_path}")
    
    # Check if Whisper is available
    if not _check_whisper_availability():
        # Provide a helpful fallback message instead of completely failing
        try:
            import librosa
            y, sr = librosa.load(src_wav_path, sr=None)
            duration = len(y) / sr
        except:
            duration = 0
        
        fallback_text = f"""[ТРАНСКРИПЦИЯ НЕДОСТУПНА]

Для работы с аудио файлами необходимо установить OpenAI Whisper:
pip install openai-whisper

После установки бот сможет автоматически транскрибировать:
• Голосовые сообщения
• Аудиофайлы (MP3, WAV, M4A, FLAC)
• Видеосообщения с аудиодорожкой

Файл обработан, но транскрипция не выполнена.
Длительность аудио: ~{duration:.1f} сек."""
        
        result["text"] = fallback_text
        result["duration_sec"] = duration
        result["language"] = "ru"  # Default language for the message
        return result
    
    # Initialize model if needed
    if not _initialize_whisper_model(model_size):
        raise RuntimeError("Failed to initialize Whisper model")
    
    try:
        logger.info(f"Transcribing audio file: {src_wav_path}")
        logger.info(f"Language hint: {language_hint}")
        
        # Run transcription in executor to avoid blocking
        transcription_result = await asyncio.get_event_loop().run_in_executor(
            None,
            _transcribe_sync,
            src_wav_path,
            language_hint
        )
        
        if transcription_result is None:
            raise RuntimeError("Transcription failed")
        
        # Extract results from Whisper response
        result["text"] = transcription_result.get("text", "").strip()
        result["language"] = transcription_result.get("language")
        
        # Calculate duration and confidence from segments if available
        segments = transcription_result.get("segments", [])
        if segments:
            result["segments"] = segments
            
            # Calculate duration from segments
            if segments:
                last_segment = segments[-1]
                result["duration_sec"] = last_segment.get("end", 0)
            
            # Calculate average probability
            probs = []
            for segment in segments:
                if "avg_logprob" in segment:
                    # Convert log probability to probability
                    import math
                    prob = math.exp(segment["avg_logprob"])
                    probs.append(prob)
            
            if probs:
                result["avg_prob"] = sum(probs) / len(probs)
        
        logger.info(f"Transcription completed. Text length: {len(result['text'])} chars")
        logger.info(f"Detected language: {result['language']}")
        logger.info(f"Duration: {result['duration_sec']}s")
        
        return result
        
    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        raise RuntimeError(f"Transcription failed: {str(e)}")

def _transcribe_sync(src_wav_path: str, language_hint: Optional[str]) -> Optional[Dict]:
    """Synchronous transcription function for executor"""
    try:
        import whisper
        global _whisper_model
        
        # Transcribe with language hint if provided
        transcribe_options = {
            "verbose": False,
            "word_timestamps": False
        }
        
        if language_hint:
            transcribe_options["language"] = language_hint
        
        result = _whisper_model.transcribe(src_wav_path, **transcribe_options)
        return result
        
    except Exception as e:
        logger.error(f"Sync transcription error: {e}")
        return None

def get_supported_languages() -> List[str]:
    """Get list of supported languages for Whisper"""
    try:
        import whisper
        return list(whisper.tokenizer.LANGUAGES.keys())
    except ImportError:
        return []

def estimate_transcription_time(duration_sec: float, model_size: str = "base") -> float:
    """
    Estimate transcription time based on audio duration and model size
    
    Args:
        duration_sec: Audio duration in seconds
        model_size: Whisper model size
        
    Returns:
        Estimated transcription time in seconds
    """
    # Rough estimates based on typical performance
    time_multipliers = {
        "tiny": 0.1,     # ~10% of audio duration
        "base": 0.2,     # ~20% of audio duration  
        "small": 0.3,    # ~30% of audio duration
        "medium": 0.5,   # ~50% of audio duration
        "large": 1.0     # ~100% of audio duration
    }
    
    multiplier = time_multipliers.get(model_size, 0.3)
    return duration_sec * multiplier

def check_whisper_installation() -> Dict[str, Any]:
    """
    Check Whisper installation status
    
    Returns:
        Status information dictionary
    """
    status = {
        "installed": False,
        "model_loaded": False,
        "supported_languages": [],
        "available_models": []
    }
    
    try:
        import whisper
        status["installed"] = True
        status["supported_languages"] = list(whisper.tokenizer.LANGUAGES.keys())
        status["available_models"] = whisper.available_models()
        
        # Check if model is loaded
        global _whisper_model
        status["model_loaded"] = _whisper_model is not None
        
    except ImportError:
        pass
    
    return status

# Alternative transcription using API (if local Whisper fails)
async def transcribe_with_openai_api(
    audio_path: str,
    api_key: str,
    language_hint: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fallback transcription using OpenAI API (requires API key)
    
    Args:
        audio_path: Path to audio file
        api_key: OpenAI API key
        language_hint: Language hint
        
    Returns:
        Transcription result dictionary
    """
    try:
        import openai
        
        openai.api_key = api_key
        
        with open(audio_path, 'rb') as audio_file:
            params = {"model": "whisper-1"}
            if language_hint:
                params["language"] = language_hint
                
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: openai.Audio.transcribe(file=audio_file, **params)
            )
            
            return {
                "text": result.get("text", "").strip(),
                "language": language_hint,  # API doesn't return detected language
                "duration_sec": None,
                "segments": None,
                "avg_prob": None
            }
            
    except Exception as e:
        logger.error(f"OpenAI API transcription failed: {e}")
        raise RuntimeError(f"API transcription failed: {str(e)}")