#!/usr/bin/env python3
"""
Text chunking for LLM processing with overlap and map-reduce summarization
"""

import logging
from typing import List, Dict, Any, Tuple
from utils.language_detection import split_into_sentences, detect_language, preserve_numbers_in_summary

logger = logging.getLogger(__name__)

class TextChunker:
    """Intelligent text chunking for LLM processing"""
    
    def __init__(self, max_chunk_size: int = 4000, overlap_size: int = 200):
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size
    
    def chunk_text(self, text: str, preserve_sentences: bool = True) -> List[Dict[str, Any]]:
        """
        Split text into overlapping chunks
        
        Args:
            text: Text to chunk
            preserve_sentences: Whether to preserve sentence boundaries
            
        Returns:
            List of chunk dictionaries with metadata
        """
        
        if len(text) <= self.max_chunk_size:
            return [{
                'text': text,
                'chunk_id': 0,
                'start_pos': 0,
                'end_pos': len(text),
                'total_chunks': 1
            }]
        
        chunks = []
        
        if preserve_sentences:
            chunks = self._chunk_by_sentences(text)
        else:
            chunks = self._chunk_by_characters(text)
        
        # Add metadata
        for i, chunk in enumerate(chunks):
            chunk.update({
                'chunk_id': i,
                'total_chunks': len(chunks)
            })
        
        logger.info(f"Text chunked into {len(chunks)} pieces")
        return chunks
    
    def _chunk_by_sentences(self, text: str) -> List[Dict[str, Any]]:
        """Chunk text preserving sentence boundaries"""
        
        # Detect language for appropriate sentence splitting
        language, _ = detect_language(text)
        sentences = split_into_sentences(text, language)
        
        chunks = []
        current_chunk = ""
        current_start = 0
        
        for sentence in sentences:
            # Check if adding this sentence exceeds limit
            test_chunk = current_chunk + " " + sentence if current_chunk else sentence
            
            if len(test_chunk) > self.max_chunk_size and current_chunk:
                # Save current chunk
                chunks.append({
                    'text': current_chunk.strip(),
                    'start_pos': current_start,
                    'end_pos': current_start + len(current_chunk),
                    'sentence_count': len(split_into_sentences(current_chunk, language))
                })
                
                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk)
                current_chunk = overlap_text + " " + sentence if overlap_text else sentence
                current_start = current_start + len(current_chunk) - len(overlap_text) - len(sentence)
            else:
                current_chunk = test_chunk
        
        # Add final chunk
        if current_chunk:
            chunks.append({
                'text': current_chunk.strip(),
                'start_pos': current_start,
                'end_pos': current_start + len(current_chunk),
                'sentence_count': len(split_into_sentences(current_chunk, language))
            })
        
        return chunks
    
    def _chunk_by_characters(self, text: str) -> List[Dict[str, Any]]:
        """Chunk text by character count with word boundaries"""
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.max_chunk_size
            
            if end >= len(text):
                # Last chunk
                chunk_text = text[start:]
            else:
                # Find word boundary for clean cut
                chunk_text = text[start:end]
                last_space = chunk_text.rfind(' ')
                
                if last_space > self.max_chunk_size * 0.8:  # At least 80% of max size
                    chunk_text = chunk_text[:last_space]
                    end = start + last_space
                else:
                    end = start + len(chunk_text)
            
            chunks.append({
                'text': chunk_text.strip(),
                'start_pos': start,
                'end_pos': end,
                'word_count': len(chunk_text.split())
            })
            
            # Move start position with overlap
            start = max(start + len(chunk_text) - self.overlap_size, end)
        
        return chunks
    
    def _get_overlap_text(self, chunk: str) -> str:
        """Get overlap text from end of chunk"""
        
        if len(chunk) <= self.overlap_size:
            return chunk
        
        # Try to find sentence boundary for clean overlap
        overlap_candidate = chunk[-self.overlap_size:]
        sentence_start = overlap_candidate.find('. ')
        
        if sentence_start > 0:
            return overlap_candidate[sentence_start + 2:]
        
        # Fallback to word boundary
        words = overlap_candidate.split()
        return ' '.join(words[-3:]) if len(words) > 3 else overlap_candidate

class MapReduceSummarizer:
    """Map-reduce style summarization for long texts"""
    
    def __init__(self, summarizer_func, chunk_compression: float = 0.3, 
                 final_compression: float = 0.5):
        self.summarizer_func = summarizer_func
        self.chunk_compression = chunk_compression
        self.final_compression = final_compression
        self.chunker = TextChunker()
    
    async def summarize_long_text(self, text: str, target_compression: float = 0.3) -> Dict[str, Any]:
        """
        Summarize long text using map-reduce approach
        
        Args:
            text: Text to summarize
            target_compression: Target compression ratio
            
        Returns:
            Summarization result with metadata
        """
        
        original_length = len(text)
        
        # Check if chunking is needed
        if original_length <= 4000:
            return await self.summarizer_func(text, target_compression)
        
        logger.info(f"Starting map-reduce summarization for {original_length} characters")
        
        # Phase 1: Map - Summarize individual chunks
        chunks = self.chunker.chunk_text(text)
        chunk_summaries = []
        
        for i, chunk in enumerate(chunks):
            logger.debug(f"Summarizing chunk {i+1}/{len(chunks)}")
            
            try:
                chunk_result = await self.summarizer_func(
                    chunk['text'], 
                    self.chunk_compression
                )
                
                if chunk_result.get('success'):
                    chunk_summaries.append({
                        'summary': chunk_result['summary'],
                        'chunk_id': chunk['chunk_id'],
                        'original_length': len(chunk['text']),
                        'summary_length': len(chunk_result['summary'])
                    })
                else:
                    logger.warning(f"Chunk {i+1} summarization failed")
                    
            except Exception as e:
                logger.error(f"Error summarizing chunk {i+1}: {e}")
        
        if not chunk_summaries:
            return {
                'success': False,
                'error': 'All chunk summarizations failed'
            }
        
        # Phase 2: Reduce - Combine and re-summarize
        combined_summaries = '\n\n'.join([cs['summary'] for cs in chunk_summaries])
        
        logger.info(f"Combining {len(chunk_summaries)} chunk summaries")
        
        # If combined summaries are still too long, recursively apply map-reduce
        if len(combined_summaries) > 6000:
            final_result = await self.summarize_long_text(
                combined_summaries, 
                self.final_compression
            )
        else:
            final_result = await self.summarizer_func(
                combined_summaries, 
                target_compression
            )
        
        if final_result.get('success'):
            # Preserve numbers from original text
            final_summary = preserve_numbers_in_summary(text, final_result['summary'])
            
            # Calculate overall compression
            final_length = len(final_summary)
            overall_compression = final_length / original_length
            
            return {
                'success': True,
                'summary': final_summary,
                'compression_ratio': overall_compression,
                'method': 'map_reduce',
                'chunks_processed': len(chunks),
                'chunk_summaries_count': len(chunk_summaries),
                'original_length': original_length,
                'final_length': final_length,
                'processing_stages': 2
            }
        else:
            return {
                'success': False,
                'error': 'Final summarization failed',
                'chunks_processed': len(chunks)
            }
    
    def estimate_processing_time(self, text_length: int) -> int:
        """Estimate processing time in seconds"""
        
        # Rough estimates based on text length
        if text_length <= 4000:
            return 5  # Simple summarization
        
        chunks_needed = (text_length // 4000) + 1
        chunk_time = chunks_needed * 3  # 3 seconds per chunk
        reduction_time = 5  # Final reduction
        
        return chunk_time + reduction_time

def create_map_reduce_summarizer(summarizer_func):
    """Factory function to create map-reduce summarizer"""
    return MapReduceSummarizer(summarizer_func)