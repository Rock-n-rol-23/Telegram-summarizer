"""
Summarization adapter for audio transcriptions
Provides unified interface to existing Llama/Groq summarization without modifying original code
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def run_summarization(
    text: str, 
    language_hint: Optional[str] = None, 
    max_sentences: Optional[int] = None,
    target_ratio: float = 0.3
) -> str:
    """
    Run text summarization using existing Groq/Llama implementation
    
    Args:
        text: Text to summarize
        language_hint: Language hint (e.g., 'ru', 'en') 
        max_sentences: Maximum sentences in summary (not used with current implementation)
        target_ratio: Target compression ratio (0.1 = 10%, 0.3 = 30%, 0.5 = 50%)
        
    Returns:
        Summarized text
        
    Raises:
        Exception: If summarization fails
    """
    if not text or len(text.strip()) < 50:
        raise ValueError("Text too short for summarization (minimum 50 characters)")
    
    logger.info(f"Running summarization for {len(text)} character text, target ratio: {target_ratio:.0%}")
    
    try:
        # Import the existing bot instance to use its summarization method
        # We need to create a minimal interface to the existing summarization
        from groq import Groq
        import os
        
        groq_api_key = os.getenv('GROQ_API_KEY')
        if not groq_api_key:
            raise Exception("GROQ_API_KEY not found in environment variables")
        
        groq_client = Groq(api_key=groq_api_key)
        
        # Use the same prompt structure as the existing implementation
        target_length = int(len(text) * target_ratio)
        
        # Create prompt similar to existing implementation
        prompt = f"""Ты - эксперт по суммаризации текстов. Создай краткое саммари следующего текста на том же языке, что и исходный текст.

Требования:
- Саммари должно быть примерно {target_length} символов (целевое сжатие: {target_ratio:.0%})
- Сохрани все ключевые моменты и важную информацию
- Используй структурированный формат с bullet points (•)
- Пиши естественным языком, сохраняя стиль исходного текста
- Если текст на русском - отвечай на русском языке
- Начни ответ сразу с саммари, без вступлений

Текст для суммаризации:
{text}"""

        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=2000,
            top_p=0.9,
        )
        
        summary = response.choices[0].message.content
        if summary:
            summary = summary.strip()
            logger.info(f"Summarization completed. Output length: {len(summary)} characters")
            return summary
        else:
            raise Exception("Empty response from summarization API")
            
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        
        # Fallback: create simple bullet-point summary
        logger.info("Using fallback summarization")
        return _create_fallback_summary(text, target_ratio)

def _create_fallback_summary(text: str, target_ratio: float = 0.3) -> str:
    """Create simple fallback summary when API fails"""
    try:
        import re
        
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        if len(sentences) <= 3:
            return f"• {text[:int(len(text) * target_ratio)]}..."
        
        # Take first, middle, and last sentences
        summary_sentences = [
            sentences[0],
            sentences[len(sentences) // 2],
            sentences[-1]
        ]
        
        # Format as bullet points
        summary = "• " + "\n• ".join(summary_sentences)
        
        # Trim if too long
        target_length = int(len(text) * target_ratio)
        if len(summary) > target_length:
            summary = summary[:target_length] + "..."
        
        return summary
        
    except Exception as e:
        logger.error(f"Fallback summary creation failed: {e}")
        return f"• {text[:200]}..." if len(text) > 200 else f"• {text}"

async def run_summarization_with_bot_instance(bot_instance, text: str, target_ratio: float = 0.3) -> str:
    """
    Alternative method using existing bot instance
    This is preferred if available as it uses the exact same summarization logic
    
    Args:
        bot_instance: Instance of SimpleTelegramBot 
        text: Text to summarize
        target_ratio: Target compression ratio
        
    Returns:
        Summarized text
    """
    try:
        if hasattr(bot_instance, 'summarize_text'):
            logger.info("Using bot instance summarize_text method")
            summary = await bot_instance.summarize_text(text, target_ratio)
            
            # Check if summary indicates an error
            if summary and not summary.startswith("❌"):
                return summary
            else:
                logger.warning(f"Bot summarization returned error: {summary}")
                raise Exception("Bot summarization failed")
        else:
            raise AttributeError("Bot instance does not have summarize_text method")
            
    except Exception as e:
        logger.error(f"Bot instance summarization failed: {e}")
        # Fallback to direct API call
        return await run_summarization(text, target_ratio=target_ratio)

def validate_summarization_input(text: str) -> bool:
    """
    Validate text input for summarization
    
    Args:
        text: Input text
        
    Returns:
        True if valid, False otherwise
    """
    if not text or not isinstance(text, str):
        return False
    
    text = text.strip()
    
    # Check minimum length
    if len(text) < 50:
        return False
    
    # Check maximum length (based on existing limits)
    if len(text) > 50000:  # 50k character limit
        return False
    
    # Check if text contains meaningful content (not just whitespace/punctuation)
    import re
    meaningful_chars = re.sub(r'[\s\.\!\?\,\;\:\-\(\)\"\']+', '', text)
    if len(meaningful_chars) < 20:
        return False
    
    return True

def prepare_audio_summary_response(
    summary: str,
    transcription: str,
    metadata: dict,
    create_file: bool = True
) -> dict:
    """
    Prepare formatted response for audio summarization
    
    Args:
        summary: Generated summary
        transcription: Full transcription text
        metadata: Audio metadata (language, duration, etc.)
        create_file: Whether to create transcription file
        
    Returns:
        Dictionary with formatted response data
    """
    language = metadata.get('language', 'неизвестен')
    duration = metadata.get('duration_sec', 0)
    
    # Format duration as MM:SS
    duration_formatted = "—"
    if duration and duration > 0:
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        duration_formatted = f"{minutes}:{seconds:02d}"
    
    # Create main response text
    response_text = f"🎵 **Саммари аудио** (язык: {language}, длительность: {duration_formatted})\n\n{summary}"
    
    # Prepare transcription file if requested
    transcription_file_path = None
    if create_file and transcription:
        try:
            import tempfile
            import os
            
            # Create temporary file for transcription
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.txt', delete=False) as f:
                f.write(f"Полная транскрипция аудио\n")
                f.write(f"Язык: {language}\n")
                f.write(f"Длительность: {duration_formatted}\n")
                f.write(f"Дата обработки: {metadata.get('processed_at', 'неизвестно')}\n")
                f.write(f"\n" + "="*50 + "\n\n")
                f.write(transcription)
                transcription_file_path = f.name
                
        except Exception as e:
            logger.warning(f"Failed to create transcription file: {e}")
    
    return {
        "response_text": response_text,
        "transcription_file": transcription_file_path,
        "metadata": {
            "language": language,
            "duration_formatted": duration_formatted,
            "summary_length": len(summary),
            "transcription_length": len(transcription),
            "compression_ratio": len(summary) / len(transcription) if transcription else 0
        }
    }