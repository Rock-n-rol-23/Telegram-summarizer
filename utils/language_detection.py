#!/usr/bin/env python3
"""
Language detection and text processing utilities
"""

import logging
import re
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# Language detection with fallback
LANGUAGE_AVAILABLE = False
try:
    from langdetect import detect, detect_langs
    from langdetect.lang_detect_exception import LangDetectException
    LANGUAGE_AVAILABLE = True
    logger.info("Language detection available")
except ImportError:
    logger.warning("langdetect not available - using fallback detection")

def detect_language(text: str) -> Tuple[str, float]:
    """
    Detect language of text with confidence score
    
    Returns:
        (language_code, confidence)
    """
    
    if not text or len(text.strip()) < 10:
        return 'unknown', 0.0
    
    if LANGUAGE_AVAILABLE:
        try:
            # Use langdetect for accurate detection
            lang_probs = detect_langs(text)
            if lang_probs:
                best_lang = lang_probs[0]
                return best_lang.lang, best_lang.prob
        except LangDetectException as e:
            logger.debug(f"Language detection failed: {e}")
    
    # Fallback to simple heuristic detection
    return _heuristic_language_detection(text)

def _heuristic_language_detection(text: str) -> Tuple[str, float]:
    """Simple heuristic language detection"""
    
    # Count Cyrillic vs Latin characters
    cyrillic_count = len(re.findall(r'[а-яё]', text.lower()))
    latin_count = len(re.findall(r'[a-z]', text.lower()))
    total_letters = cyrillic_count + latin_count
    
    if total_letters == 0:
        return 'unknown', 0.0
    
    cyrillic_ratio = cyrillic_count / total_letters
    
    # Russian if majority Cyrillic
    if cyrillic_ratio > 0.6:
        return 'ru', min(cyrillic_ratio + 0.2, 1.0)
    # English if majority Latin
    elif cyrillic_ratio < 0.1:
        return 'en', min((1 - cyrillic_ratio) * 0.8, 1.0)
    # Mixed or uncertain
    else:
        return 'mixed', 0.5

def choose_processing_strategy(text: str) -> Dict[str, str]:
    """
    Choose text processing strategy based on detected language
    
    Returns:
        Dictionary with processing parameters
    """
    
    lang, confidence = detect_language(text)
    
    strategy = {
        'language': lang,
        'confidence': confidence,
        'sentence_splitter': 'default',
        'tokenizer': 'default',
        'summarization_prompt': 'default'
    }
    
    if lang == 'ru' and confidence > 0.7:
        strategy.update({
            'sentence_splitter': 'razdel',
            'tokenizer': 'razdel',
            'summarization_prompt': 'russian'
        })
    elif lang == 'en' and confidence > 0.7:
        strategy.update({
            'sentence_splitter': 'nltk',
            'tokenizer': 'nltk', 
            'summarization_prompt': 'english'
        })
    
    logger.debug(f"Processing strategy: {strategy}")
    return strategy

def split_into_sentences(text: str, language: str = None) -> List[str]:
    """
    Split text into sentences using language-appropriate method
    """
    
    if not text:
        return []
    
    # Detect language if not provided
    if not language:
        language, _ = detect_language(text)
    
    sentences = []
    
    if language == 'ru':
        sentences = _split_russian_sentences(text)
    else:
        sentences = _split_default_sentences(text)
    
    # Clean up sentences
    cleaned_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 10:  # Filter out very short fragments
            cleaned_sentences.append(sentence)
    
    return cleaned_sentences

def _split_russian_sentences(text: str) -> List[str]:
    """Split Russian text using razdel if available"""
    
    try:
        import razdel
        sentences = [sent.text for sent in razdel.sentenize(text)]
        logger.debug(f"Razdel split {len(sentences)} sentences")
        return sentences
    except ImportError:
        logger.debug("Razdel not available, using fallback")
        return _split_default_sentences(text)

def _split_default_sentences(text: str) -> List[str]:
    """Default sentence splitting using regex"""
    
    # Simple sentence boundary detection
    sentence_endings = r'[.!?]+\s+'
    sentences = re.split(sentence_endings, text)
    
    # Rejoin sentences that were split incorrectly (e.g., abbreviations)
    cleaned_sentences = []
    for i, sentence in enumerate(sentences):
        if sentence.strip():
            # Check if this looks like an abbreviation
            if (len(sentence) < 5 and 
                i > 0 and 
                not sentence[0].isupper()):
                # Rejoin with previous sentence
                if cleaned_sentences:
                    cleaned_sentences[-1] += '. ' + sentence
                else:
                    cleaned_sentences.append(sentence)
            else:
                cleaned_sentences.append(sentence)
    
    return cleaned_sentences

def extract_key_numbers(text: str) -> List[Dict[str, str]]:
    """
    Extract important numbers, dates, percentages from text
    """
    
    key_numbers = []
    
    # Patterns for different number types
    patterns = {
        'percentage': r'\b\d+(?:\.\d+)?%',
        'currency': r'[$₽€£¥]\s?\d+(?:,\d{3})*(?:\.\d{2})?|\b\d+(?:,\d{3})*(?:\.\d{2})?\s?(?:dollars?|рублей|euros?|pounds?)',
        'date': r'\b(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[./-]\d{1,2}[./-]\d{1,2})',
        'large_number': r'\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b',
        'decimal': r'\b\d+\.\d+\b',
        'year': r'\b(?:19|20)\d{2}\b',
        'time': r'\b\d{1,2}:\d{2}(?::\d{2})?\s?(?:AM|PM|am|pm)?\b'
    }
    
    for number_type, pattern in patterns.items():
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            key_numbers.append({
                'type': number_type,
                'value': match.group(),
                'position': match.span()
            })
    
    return key_numbers

def preserve_numbers_in_summary(original_text: str, summary: str) -> str:
    """
    Ensure critical numbers from original text are preserved in summary
    """
    
    # Extract key numbers from original
    original_numbers = extract_key_numbers(original_text)
    summary_numbers = extract_key_numbers(summary)
    
    # Find missing critical numbers
    original_values = {num['value'] for num in original_numbers}
    summary_values = {num['value'] for num in summary_numbers}
    
    missing_numbers = original_values - summary_values
    
    # If important numbers are missing, add a note
    if missing_numbers:
        critical_missing = []
        for num in original_numbers:
            if (num['value'] in missing_numbers and 
                num['type'] in ['percentage', 'currency', 'large_number']):
                critical_missing.append(num['value'])
        
        if critical_missing:
            numbers_note = "Ключевые числа: " + ", ".join(critical_missing[:5])
            summary += f"\n\n📊 {numbers_note}"
            
            logger.info(f"Added missing numbers to summary: {critical_missing}")
    
    return summary

def get_language_info() -> Dict:
    """Get language detection system information"""
    
    return {
        'langdetect_available': LANGUAGE_AVAILABLE,
        'razdel_available': _check_razdel_available(),
        'supported_languages': ['ru', 'en', 'mixed'] if LANGUAGE_AVAILABLE else ['heuristic']
    }

def _check_razdel_available() -> bool:
    """Check if razdel is available"""
    try:
        import razdel
        return True
    except ImportError:
        return False