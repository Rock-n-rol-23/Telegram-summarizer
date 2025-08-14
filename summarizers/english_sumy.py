"""
Английский суммаризатор (простой экстрактивный алгоритм)
"""
import re
import logging
import math
from typing import List, Set
from collections import Counter

logger = logging.getLogger(__name__)

def summarize_en(text: str, max_sentences: int = 10) -> str:
    """
    Создает экстрактивное саммари для английского текста
    
    Args:
        text: Входной английский текст
        max_sentences: Максимальное количество предложений в саммари
        
    Returns:
        Саммари в виде списка с буллетами
    """
    if not text or len(text.strip()) < 50:
        return text.strip()
    
    # Для коротких текстов возвращаем краткую выжимку
    if len(text) < 800:
        return _create_short_summary(text)
    
    try:
        # Основной алгоритм - простая экстрактивная суммаризация
        summary_sentences = _extract_with_simple_scoring(text, max_sentences)
        
        # Если не сработал, используем fallback
        if not summary_sentences:
            return _create_fallback_summary(text, max_sentences)
        
        # Форматируем результат
        return _format_summary(summary_sentences)
        
    except Exception as e:
        logger.warning(f"Ошибка английской суммаризации: {e}")
        return _create_fallback_summary(text, max_sentences)

def _extract_with_simple_scoring(text: str, max_sentences: int) -> List[str]:
    """Простой алгоритм экстрактивной суммаризации на основе частоты слов"""
    try:
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 15]
        
        if len(sentences) <= max_sentences:
            return sentences
        
        # Подсчет частоты слов
        word_freq = _calculate_word_frequency(text)
        
        # Оценка предложений
        sentence_scores = []
        for i, sentence in enumerate(sentences):
            score = _score_sentence(sentence, word_freq)
            # Бонус за позицию (первые и последние предложения важнее)
            position_bonus = 1.0
            if i == 0:  # Первое предложение
                position_bonus = 1.5
            elif i == len(sentences) - 1:  # Последнее предложение
                position_bonus = 1.2
            elif i < len(sentences) * 0.3:  # Первая треть
                position_bonus = 1.3
            
            sentence_scores.append((score * position_bonus, sentence))
        
        # Сортируем по оценке и берем лучшие
        sentence_scores.sort(reverse=True)
        top_sentences = [sentence for _, sentence in sentence_scores[:max_sentences]]
        
        # Возвращаем в исходном порядке
        result = []
        for sentence in sentences:
            if sentence in top_sentences:
                result.append(sentence)
                if len(result) >= max_sentences:
                    break
        
        return result
    except Exception as e:
        logger.debug(f"Simple scoring failed: {e}")
        return []

def _calculate_word_frequency(text: str) -> Counter:
    """Подсчет частоты слов (исключая стоп-слова)"""
    # Простой список английских стоп-слов
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 
        'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 
        'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 
        'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 
        'us', 'them', 'my', 'your', 'his', 'its', 'our', 'their', 'as', 'if', 'when', 
        'where', 'why', 'how', 'what', 'which', 'who', 'whom'
    }
    
    words = re.findall(r'\b[a-z]+\b', text.lower())
    meaningful_words = [word for word in words if word not in stop_words and len(word) > 2]
    
    return Counter(meaningful_words)

def _score_sentence(sentence: str, word_freq: Counter) -> float:
    """Оценка предложения на основе частоты слов"""
    words = re.findall(r'\b[a-z]+\b', sentence.lower())
    if not words:
        return 0.0
    
    score = sum(word_freq.get(word, 0) for word in words)
    return score / len(words)  # Нормализация по длине предложения

def _create_short_summary(text: str) -> str:
    """Создание краткого саммари для коротких текстов"""
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
    
    if len(sentences) <= 3:
        return text.strip()
    
    # Берем первые 2-3 наиболее информативных предложения
    important_sentences = sentences[:3]
    formatted = []
    
    for sentence in important_sentences:
        if sentence and not sentence.endswith('.'):
            sentence += '.'
        formatted.append(f"• {sentence}")
    
    return '\n'.join(formatted)

def _create_fallback_summary(text: str, max_sentences: int) -> str:
    """Простая эвристическая суммаризация"""
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 15]
    
    if not sentences:
        return text[:500] + "..." if len(text) > 500 else text
    
    # Берем первые и самые длинные предложения
    important_sentences = []
    
    # Первое предложение (введение)
    if sentences:
        important_sentences.append(sentences[0])
    
    # Самые информативные предложения (длинные, с ключевыми словами)
    remaining = sentences[1:]
    remaining.sort(key=lambda s: len(s), reverse=True)
    
    for sentence in remaining[:max_sentences-1]:
        if sentence not in important_sentences:
            important_sentences.append(sentence)
    
    return _format_summary(important_sentences[:max_sentences])

def _format_summary(sentences: List[str]) -> str:
    """Форматирование списка предложений в буллеты"""
    if not sentences:
        return ""
    
    formatted = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # Удаляем дубликаты
        if sentence in formatted:
            continue
            
        # Нормализуем пробелы
        sentence = re.sub(r'\s+', ' ', sentence)
        
        # Добавляем точку если её нет
        if not sentence.endswith(('.', '!', '?')):
            sentence += '.'
            
        formatted.append(f"• {sentence}")
    
    # Удаляем дубликаты сохраняя порядок
    seen = set()
    unique_formatted = []
    for item in formatted:
        if item not in seen:
            seen.add(item)
            unique_formatted.append(item)
    
    return '\n'.join(unique_formatted)