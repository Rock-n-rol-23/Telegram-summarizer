"""
Summarization adapter for audio transcription
Integrates with existing Llama summarization without modifying core code
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def run_summarization(full_text: str, language_hint: Optional[str] = None, compression: float = 0.3):
    """
    Run summarization using existing bot summarization method
    
    Args:
        full_text: Full transcribed text
        language_hint: Language hint for summarization
        compression: Compression ratio (0.1, 0.3, 0.5)
    
    Returns:
        Summarized text
    """
    try:
        # Import here to avoid circular imports
        from simple_bot import bot_instance
        
        if not bot_instance:
            raise RuntimeError("Bot instance not available")
        
        # Use bot's existing summarization method
        summary = await bot_instance.summarize_text(
            text=full_text,
            compression_level=compression,
            language_hint=language_hint
        )
        
        return summary
        
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        
        # Fallback summary
        lines = full_text.split('\n')[:10]  # First 10 lines
        fallback = '\n'.join(f"• {line.strip()}" for line in lines if line.strip())
        
        return f"""[АВТОМАТИЧЕСКОЕ РЕЗЮМЕ]

{fallback}

Полный текст доступен в приложенном файле."""

def format_audio_summary(summary: str, metadata: dict) -> str:
    """
    Format summary with audio metadata
    
    Args:
        summary: Generated summary text
        metadata: Audio processing metadata
        
    Returns:
        Formatted summary with metadata
    """
    engine = metadata.get("engine", "unknown")
    language = metadata.get("language", "unknown")
    duration_sec = metadata.get("duration_sec", 0)
    chunks = metadata.get("chunks", 1)
    
    # Format duration
    minutes = int(duration_sec // 60)
    seconds = int(duration_sec % 60)
    duration_str = f"{minutes}:{seconds:02d}"
    
    header = f"""📊 Саммари аудио (движок: {engine}, язык: {language}, длительность: {duration_str}, чанков: {chunks})

"""
    
    return header + summary