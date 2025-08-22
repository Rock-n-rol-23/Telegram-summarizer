#!/usr/bin/env python3
"""
Enhanced summarization pipeline with language detection, chunking, and numeric consistency
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
from utils.language_detection import detect_language, choose_processing_strategy, preserve_numbers_in_summary
from utils.chunking import create_map_reduce_summarizer
from utils.logging_config import TimedLogger, log_external_call
from utils.rate_limiter import external_call
from config import config

logger = logging.getLogger(__name__)

class EnhancedSummarizer:
    """Enhanced summarization with language awareness and chunking"""
    
    def __init__(self, groq_client):
        self.groq_client = groq_client
        self.map_reduce_summarizer = None
        
        # Initialize map-reduce summarizer if available
        if groq_client:
            self.map_reduce_summarizer = create_map_reduce_summarizer(
                self._groq_summarize_chunk
            )
    
    async def summarize_text(self, text: str, compression_level: float = 0.3,
                           user_context: Dict = None) -> Dict[str, Any]:
        """
        Enhanced text summarization with language detection and chunking
        
        Args:
            text: Text to summarize
            compression_level: Target compression ratio (0.0 to 1.0)
            user_context: Optional user context for personalization
            
        Returns:
            Summarization result with enhanced metadata
        """
        
        start_time = time.time()
        original_length = len(text)
        
        try:
            # Language detection and strategy selection
            strategy = choose_processing_strategy(text)
            
            logger.info(
                f"Summarization strategy: {strategy['language']} "
                f"(confidence: {strategy['confidence']:.2f})"
            )
            
            # Determine if chunking is needed
            if original_length > 4000 and self.map_reduce_summarizer:
                logger.info("Using map-reduce summarization for long text")
                result = await self.map_reduce_summarizer.summarize_long_text(
                    text, compression_level
                )
            else:
                logger.info("Using direct summarization")
                result = await self._direct_summarize(text, compression_level, strategy)
            
            if result.get('success'):
                # Enhance result with metadata
                processing_time = time.time() - start_time
                
                result.update({
                    'language': strategy['language'],
                    'language_confidence': strategy['confidence'],
                    'processing_time': processing_time,
                    'original_length': original_length,
                    'enhanced_pipeline': True
                })
                
                # Log success metrics
                logger.info(
                    f"Summarization completed: {original_length} → "
                    f"{len(result['summary'])} chars "
                    f"({result.get('compression_ratio', 0):.1%} compression) "
                    f"in {processing_time:.1f}s"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Enhanced summarization failed: {e}")
            return {
                'success': False,
                'error': f"Summarization error: {str(e)}",
                'processing_time': time.time() - start_time
            }
    
    async def _direct_summarize(self, text: str, compression_level: float,
                               strategy: Dict) -> Dict[str, Any]:
        """Direct summarization without chunking"""
        
        # Choose prompt based on language
        prompt = self._get_summarization_prompt(
            compression_level, 
            strategy['language']
        )
        
        with TimedLogger(logger, "direct summarization", external_service="groq"):
            result = await self._groq_summarize_chunk(text, compression_level, prompt)
        
        if result.get('success'):
            # Apply numeric consistency check
            enhanced_summary = preserve_numbers_in_summary(text, result['summary'])
            result['summary'] = enhanced_summary
            result['method'] = 'direct'
        
        return result
    
    async def _groq_summarize_chunk(self, text: str, compression_level: float = 0.3,
                                   custom_prompt: str = None) -> Dict[str, Any]:
        """Summarize a single chunk using Groq API"""
        
        if not self.groq_client:
            return {
                'success': False,
                'error': 'Groq client not available'
            }
        
        try:
            # Build prompt
            if custom_prompt:
                prompt = custom_prompt
            else:
                language, _ = detect_language(text)
                prompt = self._get_summarization_prompt(compression_level, language)
            
            # Make API call with protection
            async def make_groq_call():
                response = await asyncio.to_thread(
                    self.groq_client.chat.completions.create,
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": text}
                    ],
                    temperature=0.3,
                    max_tokens=min(int(len(text) * compression_level * 1.5), 2000)
                )
                return response
            
            start_time = time.time()
            response = await external_call("groq", make_groq_call)
            duration = time.time() - start_time
            
            # Log external call
            log_external_call(logger, "groq", duration)
            
            summary = response.choices[0].message.content.strip()
            
            if summary:
                compression_ratio = len(summary) / len(text)
                
                return {
                    'success': True,
                    'summary': summary,
                    'compression_ratio': compression_ratio,
                    'api_duration': duration,
                    'model': 'llama-3.3-70b-versatile'
                }
            else:
                return {
                    'success': False,
                    'error': 'Empty response from Groq API'
                }
                
        except Exception as e:
            logger.error(f"Groq API call failed: {e}")
            return {
                'success': False,
                'error': f"API error: {str(e)}"
            }
    
    def _get_summarization_prompt(self, compression_level: float, language: str) -> str:
        """Get language-specific summarization prompt"""
        
        # Determine summary length guidance
        if compression_level <= 0.2:
            length_desc = "very brief summary"
            length_desc_ru = "очень краткое резюме"
        elif compression_level <= 0.4:
            length_desc = "concise summary"
            length_desc_ru = "краткое резюме"
        else:
            length_desc = "detailed summary"
            length_desc_ru = "подробное резюме"
        
        if language == 'ru':
            return f"""Ты профессиональный редактор. Создай {length_desc_ru} следующего текста.

ОБЯЗАТЕЛЬНЫЕ ТРЕБОВАНИЯ:
1. Сохрани все числа, даты, проценты, суммы ТОЧНО как в оригинале
2. Используй русский язык
3. Сохрани ключевые факты и выводы
4. Структурируй информацию логично
5. Не добавляй информацию, которой нет в тексте

Создай резюме:"""
        else:
            return f"""You are a professional editor. Create a {length_desc} of the following text.

MANDATORY REQUIREMENTS:
1. Preserve all numbers, dates, percentages, amounts EXACTLY as in the original
2. Use English language
3. Keep key facts and conclusions
4. Structure information logically
5. Do not add information not present in the text

Create summary:"""
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get summarizer capabilities"""
        
        return {
            'language_detection': True,
            'chunking_support': self.map_reduce_summarizer is not None,
            'numeric_preservation': True,
            'map_reduce': self.map_reduce_summarizer is not None,
            'max_text_length': 50000 if self.map_reduce_summarizer else 4000,
            'supported_languages': ['en', 'ru', 'mixed'],
            'groq_available': self.groq_client is not None
        }

def create_enhanced_summarizer(groq_client):
    """Factory function to create enhanced summarizer"""
    return EnhancedSummarizer(groq_client)