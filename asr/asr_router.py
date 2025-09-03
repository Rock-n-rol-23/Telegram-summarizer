"""
ASR Router - Manages multiple ASR engines with fallback support
Primary: Faster-Whisper (free local)
Optional: Groq Whisper (paid fallback)
"""

import logging
from typing import Optional
from config import config

logger = logging.getLogger(__name__)

class ASRRouter:
    """Routes ASR requests through multiple engines with fallback"""
    
    def __init__(self):
        self.faster_whisper_engine = None
        self.groq_client = None
        
        self._initialize_engines()
    
    def _initialize_engines(self):
        """Initialize available ASR engines"""
        # Primary: Faster-Whisper
        if config.ASR_ENGINE == 'faster_whisper':
            try:
                from asr.engines.faster_whisper_engine import get_faster_whisper_engine
                self.faster_whisper_engine = get_faster_whisper_engine()
                logger.info("Faster-Whisper ASR engine initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Faster-Whisper: {e}")
        
        # Optional fallback: Groq Whisper
        if config.ASR_ENGINE == 'groq_whisper' or config.ENABLE_GROQ_FALLBACK:
            try:
                if config.GROQ_API_KEY:
                    from groq import Groq
                    self.groq_client = Groq(api_key=config.GROQ_API_KEY)
                    logger.info("Groq Whisper fallback initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Groq Whisper: {e}")
    
    def transcribe_audio(self, audio_file_path: str, language: Optional[str] = None) -> str:
        """
        Transcribe audio file using available engines
        
        Args:
            audio_file_path: Path to audio file
            language: Optional language hint
            
        Returns:
            Transcribed text
        """
        # Primary: Faster-Whisper
        if self.faster_whisper_engine and self.faster_whisper_engine.is_available():
            try:
                logger.info("Using Faster-Whisper for transcription")
                return self.faster_whisper_engine.transcribe(audio_file_path, language)
            except Exception as e:
                logger.error(f"Faster-Whisper failed: {e}")
                # Continue to fallback
        
        # Fallback: Groq Whisper
        if self.groq_client:
            try:
                logger.info("Using Groq Whisper fallback")
                return self._transcribe_with_groq(audio_file_path, language)
            except Exception as e:
                logger.error(f"Groq Whisper fallback failed: {e}")
        
        raise Exception("Все ASR движки недоступны. Проверьте конфигурацию.")
    
    def _transcribe_with_groq(self, audio_file_path: str, language: Optional[str] = None) -> str:
        """Transcribe using Groq Whisper API"""
        try:
            with open(audio_file_path, 'rb') as audio_file:
                # Map language codes for Groq
                groq_language = None
                if language == 'ru':
                    groq_language = 'ru'
                elif language == 'en':
                    groq_language = 'en'
                
                transcription = self.groq_client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-large-v3",
                    language=groq_language,
                    response_format="text"
                )
                
                result = transcription.strip()
                
                if not result:
                    raise Exception("No speech detected")
                
                logger.info(f"Groq transcription completed: {len(result)} characters")
                return result
                
        except Exception as e:
            logger.error(f"Groq transcription failed: {e}")
            raise Exception(f"Groq ASR failed: {str(e)}")
    
    def is_available(self) -> bool:
        """Check if any ASR engine is available"""
        return (
            (self.faster_whisper_engine and self.faster_whisper_engine.is_available()) or
            (self.groq_client is not None)
        )
    
    def get_engine_info(self) -> dict:
        """Get info about available engines"""
        return {
            'faster_whisper': {
                'available': self.faster_whisper_engine is not None and self.faster_whisper_engine.is_available(),
                'model': config.FASTER_WHISPER_MODEL if self.faster_whisper_engine else None
            },
            'groq_whisper': {
                'available': self.groq_client is not None,
                'enabled': config.ASR_ENGINE == 'groq_whisper' or config.ENABLE_GROQ_FALLBACK
            }
        }


# Global instance
asr_router = None

def get_asr_router() -> ASRRouter:
    """Get global ASR router instance"""
    global asr_router
    if asr_router is None:
        asr_router = ASRRouter()
    return asr_router

def transcribe_audio(audio_file_path: str, language: Optional[str] = None) -> str:
    """Convenience function for audio transcription"""
    router = get_asr_router()
    return router.transcribe_audio(audio_file_path, language)