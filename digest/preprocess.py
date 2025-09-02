"""
Text preprocessing for digest system
"""

import re
import logging
from typing import List, Set
from stop_words import get_stop_words

logger = logging.getLogger(__name__)

# Cache stop words
_stop_words_cache = {}

def get_stop_words_set(lang: str = 'ru') -> Set[str]:
    """Get stop words for language with caching"""
    if lang not in _stop_words_cache:
        try:
            if lang == 'ru':
                # Russian stop words
                stop_words = set(get_stop_words('russian'))
                # Add some common Russian words that might be missing
                stop_words.update([
                    'это', 'что', 'как', 'где', 'когда', 'кто', 'почему', 'зачем',
                    'да', 'нет', 'ок', 'хорошо', 'плохо', 'может', 'можно', 'нужно',
                    'очень', 'просто', 'только', 'тоже', 'также', 'еще', 'уже',
                    'сейчас', 'теперь', 'потом', 'здесь', 'там', 'тут'
                ])
            elif lang == 'en':
                # English stop words
                stop_words = set(get_stop_words('english'))
                # Add some common words
                stop_words.update([
                    'ok', 'okay', 'yeah', 'yes', 'no', 'maybe', 'really', 'just',
                    'like', 'well', 'now', 'then', 'here', 'there', 'also', 'too'
                ])
            else:
                # Fallback to English
                stop_words = set(get_stop_words('english'))
                
            _stop_words_cache[lang] = stop_words
        except Exception as e:
            logger.warning(f"Could not load stop words for {lang}: {e}")
            _stop_words_cache[lang] = set()
    
    return _stop_words_cache[lang]

def clean_text(text: str) -> str:
    """Clean text from URLs, emojis, extra whitespace"""
    if not text:
        return ""
    
    # Remove URLs
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'www\.[^\s]+', '', text)
    
    # Remove Telegram entities like @username, #hashtag
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'#\w+', '', text)
    
    # Remove emojis (basic version)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)
    
    # Remove special characters but keep basic punctuation
    text = re.sub(r'[^\w\s\.\,\!\?\-\(\)\:\;]', ' ', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def tokenize(text: str, lang: str = 'ru') -> List[str]:
    """Tokenize text into words, removing stop words"""
    if not text:
        return []
    
    # Basic tokenization
    words = re.findall(r'\b\w+\b', text.lower())
    
    # Remove stop words
    stop_words = get_stop_words_set(lang)
    words = [word for word in words if word not in stop_words and len(word) > 2]
    
    return words

def for_vectorizer(text: str, lang: str = 'ru') -> str:
    """Prepare text for TF-IDF vectorizer"""
    cleaned = clean_text(text)
    tokens = tokenize(cleaned, lang)
    return ' '.join(tokens)

def extract_numbers_and_dates(text: str) -> List[str]:
    """Extract numbers, dates, percentages for preservation"""
    if not text:
        return []
    
    patterns = []
    
    # Numbers with units/currency
    patterns.extend(re.findall(r'\d+[.,]?\d*\s*(?:руб|рубл|доллар|евро|%|млн|млрд|тыс)', text, re.IGNORECASE))
    
    # Dates
    patterns.extend(re.findall(r'\d{1,2}[./]\d{1,2}[./]\d{2,4}', text))
    patterns.extend(re.findall(r'\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4}', text, re.IGNORECASE))
    
    # Percentages
    patterns.extend(re.findall(r'\d+[.,]?\d*%', text))
    
    # Large numbers
    patterns.extend(re.findall(r'\d{4,}', text))
    
    return list(set(patterns))

def detect_language(text: str) -> str:
    """Simple language detection for Russian/English"""
    if not text:
        return 'ru'
    
    # Count Cyrillic vs Latin characters
    cyrillic_count = len(re.findall(r'[а-яё]', text.lower()))
    latin_count = len(re.findall(r'[a-z]', text.lower()))
    
    if cyrillic_count > latin_count:
        return 'ru'
    elif latin_count > cyrillic_count * 2:  # Strong bias towards English
        return 'en'
    else:
        return 'ru'  # Default to Russian

def prepare_for_clustering(messages: List[dict], lang: str = 'ru') -> List[str]:
    """Prepare message texts for clustering"""
    prepared_texts = []
    
    for msg in messages:
        text = msg.get('text', '')
        if text:
            # Clean and prepare for vectorization
            processed = for_vectorizer(text, lang)
            if processed:  # Only add non-empty texts
                prepared_texts.append(processed)
            else:
                prepared_texts.append('')  # Keep index alignment
        else:
            prepared_texts.append('')
    
    return prepared_texts

def extract_key_phrases(text: str, lang: str = 'ru', max_phrases: int = 5) -> List[str]:
    """Extract key phrases using simple regex patterns"""
    if not text:
        return []
    
    phrases = []
    
    # Numbers and important metrics
    numbers = extract_numbers_and_dates(text)
    phrases.extend(numbers[:3])  # Top 3 numbers
    
    # Quoted text
    quotes = re.findall(r'[«"„]([^»"'"]+)[»"'"]', text)
    phrases.extend([q.strip() for q in quotes[:2]])
    
    # Important phrases (capitalized words sequence)
    caps_phrases = re.findall(r'[А-ЯA-Z][а-яa-z]+(?:\s+[А-ЯA-Z][а-яa-z]+)*', text)
    phrases.extend(caps_phrases[:2])
    
    return phrases[:max_phrases]