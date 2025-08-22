#!/usr/bin/env python3
"""
Telegram utilities for message formatting and chunking
"""

import re
from typing import List

def escape_markdown_v2(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2
    
    Args:
        text: Text to escape
        
    Returns:
        Escaped text safe for MarkdownV2
    """
    # Characters that need escaping in MarkdownV2
    special_chars = r'_*[]()~`>#+-=|{}.!'
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

def split_message(text: str, max_length: int = 4096, preserve_formatting: bool = True) -> List[str]:
    """
    Split long message into chunks that fit Telegram's limits
    
    Args:
        text: Text to split
        max_length: Maximum length per chunk (default 4096 for Telegram)
        preserve_formatting: Try to preserve markdown formatting
        
    Returns:
        List of text chunks
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # Split by lines first to preserve structure
    lines = text.split('\n')
    
    for line in lines:
        # If single line is too long, split it
        if len(line) > max_length:
            # Split long line by sentences, then words
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # Split by sentences
            sentences = re.split(r'[.!?]+\s+', line)
            for sentence in sentences:
                if len(sentence) > max_length:
                    # Split by words as last resort
                    words = sentence.split()
                    for word in words:
                        if len(current_chunk + " " + word) > max_length:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                                current_chunk = word
                            else:
                                # Single word is too long - truncate
                                chunks.append(word[:max_length-3] + "...")
                                current_chunk = ""
                        else:
                            current_chunk += " " + word if current_chunk else word
                else:
                    if len(current_chunk + "\n" + sentence) > max_length:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = sentence
                        else:
                            current_chunk = sentence
                    else:
                        current_chunk += "\n" + sentence if current_chunk else sentence
        else:
            # Normal line processing
            if len(current_chunk + "\n" + line) > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = line
                else:
                    current_chunk = line
            else:
                current_chunk += "\n" + line if current_chunk else line
    
    # Add remaining chunk
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def format_summary_message(summary: str, compression_ratio: float, processing_time: float, 
                         source_type: str = "текст") -> str:
    """
    Format summary message with statistics
    
    Args:
        summary: The summarized text
        compression_ratio: Compression ratio (0.0 to 1.0)
        processing_time: Processing time in seconds
        source_type: Type of source content
        
    Returns:
        Formatted message
    """
    stats = f"• Сжатие: {compression_ratio:.1%}\n• Время обработки: {processing_time:.1f}с"
    
    return f"📄 **Краткое содержание {source_type}:**\n\n{summary}\n\n{stats}"

def format_error_message(error_type: str, details: str = "") -> str:
    """
    Format error message for user
    
    Args:
        error_type: Type of error
        details: Additional details
        
    Returns:
        Formatted error message
    """
    emoji_map = {
        "rate_limit": "⏰",
        "size_limit": "📏", 
        "network": "🌐",
        "ssrf": "🛡️",
        "timeout": "⏱️",
        "processing": "⚙️",
        "unknown": "❌"
    }
    
    emoji = emoji_map.get(error_type, "❌")
    
    if details:
        return f"{emoji} **Ошибка {error_type}:**\n{details}"
    else:
        return f"{emoji} **Произошла ошибка при обработке запроса**"