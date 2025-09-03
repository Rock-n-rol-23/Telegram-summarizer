"""
Faster-Whisper ASR Engine - Free local alternative to Groq Whisper
Uses CTranslate2 for efficient CPU inference
"""

import os
import logging
import tempfile
import hashlib
from typing import Optional, Tuple
from pathlib import Path
import subprocess

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    WhisperModel = None

from config import config

logger = logging.getLogger(__name__)

class FasterWhisperEngine:
    """Faster-Whisper ASR engine with caching and preprocessing"""
    
    def __init__(self):
        self.model = None
        self.model_size = config.FASTER_WHISPER_MODEL
        self.compute_type = config.FASTER_WHISPER_COMPUTE
        self.cache_dir = Path("./asr_cache")
        self.cache_dir.mkdir(exist_ok=True)
        
        if not FASTER_WHISPER_AVAILABLE:
            raise ImportError("faster-whisper не установлен. Установите: pip install faster-whisper")
        
        self._load_model()
    
    def _load_model(self):
        """Load the Whisper model with caching"""
        try:
            logger.info(f"Loading Faster-Whisper model: {self.model_size} with compute_type: {self.compute_type}")
            
            # Try to use the specified compute type, fallback to float32 if needed
            try:
                self.model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type=self.compute_type
                )
            except Exception as e:
                logger.warning(f"Failed to load with {self.compute_type}, trying float32: {e}")
                self.model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="float32"
                )
            
            logger.info("Faster-Whisper model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load Faster-Whisper model: {e}")
            raise
    
    def _get_file_hash(self, file_path: str) -> str:
        """Get hash of audio file for caching"""
        with open(file_path, 'rb') as f:
            content = f.read()
        return hashlib.md5(content).hexdigest()
    
    def _get_cached_result(self, file_hash: str) -> Optional[str]:
        """Check if transcription is cached"""
        cache_file = self.cache_dir / f"{file_hash}.txt"
        if cache_file.exists():
            try:
                return cache_file.read_text(encoding='utf-8')
            except Exception as e:
                logger.warning(f"Failed to read cache file: {e}")
        return None
    
    def _save_to_cache(self, file_hash: str, transcription: str):
        """Save transcription to cache"""
        try:
            cache_file = self.cache_dir / f"{file_hash}.txt"
            cache_file.write_text(transcription, encoding='utf-8')
        except Exception as e:
            logger.warning(f"Failed to save to cache: {e}")
    
    def _preprocess_audio(self, input_path: str) -> str:
        """
        Preprocess audio to mono 16kHz WAV format
        
        Args:
            input_path: Path to input audio file
            
        Returns:
            Path to preprocessed audio file
        """
        try:
            # Create temporary file for processed audio
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_path = temp_file.name
            temp_file.close()
            
            # Use ffmpeg to convert to mono 16kHz WAV
            cmd = [
                'ffmpeg', '-i', input_path,
                '-ac', '1',  # mono
                '-ar', '16000',  # 16kHz sample rate
                '-y',  # overwrite output
                temp_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"ffmpeg error: {result.stderr}")
                raise Exception(f"Audio preprocessing failed: {result.stderr}")
            
            logger.info(f"Audio preprocessed: {input_path} -> {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Audio preprocessing failed: {e}")
            raise
    
    def transcribe(self, audio_file_path: str, language: Optional[str] = None) -> str:
        """
        Transcribe audio file to text
        
        Args:
            audio_file_path: Path to audio file
            language: Optional language code ('ru', 'en', etc.)
            
        Returns:
            Transcribed text
        """
        if not self.model:
            raise RuntimeError("Faster-Whisper model not loaded")
        
        # Check cache first
        file_hash = self._get_file_hash(audio_file_path)
        cached_result = self._get_cached_result(file_hash)
        if cached_result:
            logger.info("Using cached transcription")
            return cached_result
        
        preprocessed_path = None
        try:
            # Preprocess audio
            preprocessed_path = self._preprocess_audio(audio_file_path)
            
            # Transcribe
            logger.info(f"Starting transcription with language: {language}")
            
            segments, info = self.model.transcribe(
                preprocessed_path,
                language=language,
                beam_size=5,
                best_of=5,
                temperature=0.0,
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Collect segments into text
            transcription_parts = []
            for segment in segments:
                transcription_parts.append(segment.text.strip())
            
            transcription = " ".join(transcription_parts).strip()
            
            if not transcription:
                raise Exception("No speech detected in audio file")
            
            logger.info(f"Transcription completed: {len(transcription)} characters")
            logger.info(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")
            
            # Cache the result
            self._save_to_cache(file_hash, transcription)
            
            return transcription
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise Exception(f"Не удалось распознать речь: {str(e)}")
            
        finally:
            # Clean up preprocessed file
            if preprocessed_path and os.path.exists(preprocessed_path):
                try:
                    os.unlink(preprocessed_path)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file: {e}")
    
    def is_available(self) -> bool:
        """Check if engine is available and working"""
        return FASTER_WHISPER_AVAILABLE and self.model is not None


# Global instance
faster_whisper_engine = None

def get_faster_whisper_engine() -> FasterWhisperEngine:
    """Get global Faster-Whisper engine instance"""
    global faster_whisper_engine
    if faster_whisper_engine is None:
        faster_whisper_engine = FasterWhisperEngine()
    return faster_whisper_engine

def transcribe_audio(audio_file_path: str, language: Optional[str] = None) -> str:
    """Convenience function for audio transcription"""
    engine = get_faster_whisper_engine()
    return engine.transcribe(audio_file_path, language)