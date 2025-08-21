"""
Умная суммаризация текста с экстрактивным подходом и структурированием
"""

import re
import logging
from typing import Dict, List, Tuple, Set
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)

# Проверяем наличие зависимостей
try:
    import razdel
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.summarizers.text_rank import TextRankSummarizer
    from sumy.summarizers.lex_rank import LexRankSummarizer
    import rutermextract
    from natasha import (
        Segmenter, MorphVocab, NewsEmbedding, NewsMorphTagger,
        NewsNERTagger, NewsSyntaxParser, Doc, NamesExtractor,
        DatesExtractor, MoneyExtractor
    )
    SUMMARIZATION_AVAILABLE = True
except ImportError as e:
    SUMMARIZATION_AVAILABLE = False
    logger.warning(f"Суммаризация недоступна: {e}")

# Ключевые триггеры для категоризации
AGREEMENT_TRIGGERS = [
    'договор', 'договорились', 'согласились', 'решили', 'обещали',
    'подтверждаем', 'принято', 'утверждено', 'одобрено', 'записались'
]

DEADLINE_TRIGGERS = [
    'срок', 'дедлайн', 'к', 'до', 'завтра', 'сегодня', 'через',
    'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье',
    'пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс',
    'утром', 'днем', 'вечером', 'времени'
]

ACTION_TRIGGERS = [
    'нужно', 'необходимо', 'следует', 'должны', 'планируем', 'будем',
    'сделать', 'выполнить', 'подготовить', 'организовать', 'связаться',
    'уточнить', 'проверить', 'подтвердить'
]

CONDITION_TRIGGERS = [
    'если', 'при условии', 'в случае', 'возможно', 'может быть',
    'по желанию', 'опционально', 'на выбор', 'при необходимости'
]

SPECIAL_TERMS = [
    'бесплатно', 'платно', 'стоимость', 'цена', 'расписание',
    'график', 'время', 'продолжительность', 'занятие', 'урок',
    'встреча', 'собрание', 'звонок', 'созвон'
]

# Глобальные объекты natasha для ленивой загрузки
_natasha_ready = False
_segmenter = None
_morph_vocab = None
_emb = None
_morph_tagger = None
_ner_tagger = None
_dates_extractor = None
_money_extractor = None


def init_natasha():
    """Инициализирует компоненты natasha"""
    global _natasha_ready, _segmenter, _morph_vocab, _emb, _morph_tagger, _ner_tagger, _dates_extractor, _money_extractor
    
    if _natasha_ready or not SUMMARIZATION_AVAILABLE:
        return
    
    try:
        logger.info("Инициализация natasha...")
        
        _segmenter = Segmenter()
        _morph_vocab = MorphVocab()
        _emb = NewsEmbedding()
        _morph_tagger = NewsMorphTagger(_emb)
        _ner_tagger = NewsNERTagger(_emb)
        _dates_extractor = DatesExtractor()
        _money_extractor = MoneyExtractor()
        
        _natasha_ready = True
        logger.info("Natasha инициализирована успешно")
        
    except Exception as e:
        logger.warning(f"Ошибка инициализации natasha: {e}")


def extract_sentences(text: str) -> List[str]:
    """Разбивает текст на предложения с помощью razdel"""
    if not SUMMARIZATION_AVAILABLE:
        # Fallback разбиение
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    try:
        sentences = razdel.sentenize(text)
        return [sent.text.strip() for sent in sentences if sent.text.strip()]
    except Exception as e:
        logger.warning(f"Ошибка razdel, использую fallback: {e}")
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]


def extract_key_terms(text: str, limit: int = 20) -> List[str]:
    """Извлекает ключевые термины с помощью rutermextract"""
    if not SUMMARIZATION_AVAILABLE:
        return []
    
    try:
        terms = rutermextract.TermExtractor()
        extracted = terms(text)
        
        # Берем только термины с высокой частотой
        key_terms = []
        for term in extracted[:limit]:
            if term.count >= 2 or len(term.normalized) > 3:
                key_terms.append(term.normalized)
        
        return key_terms
    except Exception as e:
        logger.warning(f"Ошибка rutermextract: {e}")
        return []


def extract_entities_and_dates(text: str) -> Dict:
    """Извлекает именованные сущности и даты с помощью natasha"""
    init_natasha()
    
    entities = {
        'names': [],
        'organizations': [],
        'locations': [],
        'dates': [],
        'money': []
    }
    
    if not _natasha_ready:
        return entities
    
    try:
        doc = Doc(text)
        doc.segment(_segmenter)
        doc.tag_morph(_morph_tagger)
        doc.tag_ner(_ner_tagger)
        
        # Извлекаем NER
        for span in doc.spans:
            if span.type == 'PER':
                entities['names'].append(span.text)
            elif span.type == 'ORG':
                entities['organizations'].append(span.text)
            elif span.type == 'LOC':
                entities['locations'].append(span.text)
        
        # Извлекаем даты
        for match in _dates_extractor(text):
            entities['dates'].append(match.fact.as_json)
        
        # Извлекаем деньги
        for match in _money_extractor(text):
            entities['money'].append(match.fact.as_json)
            
    except Exception as e:
        logger.warning(f"Ошибка natasha extraction: {e}")
    
    return entities


def categorize_sentences(sentences: List[str]) -> Dict[str, List[Tuple[int, str]]]:
    """Категоризирует предложения по типам"""
    categories = {
        'agreements': [],      # Договоренности
        'deadlines': [],       # Сроки
        'actions': [],         # Действия
        'conditions': [],      # Условия
        'special_terms': [],   # Специальные термины
        'other': []           # Остальное
    }
    
    for i, sentence in enumerate(sentences):
        sentence_lower = sentence.lower()
        categorized = False
        
        # Проверяем каждую категорию
        for trigger in AGREEMENT_TRIGGERS:
            if trigger in sentence_lower:
                categories['agreements'].append((i, sentence))
                categorized = True
                break
        
        if not categorized:
            for trigger in DEADLINE_TRIGGERS:
                if trigger in sentence_lower:
                    categories['deadlines'].append((i, sentence))
                    categorized = True
                    break
        
        if not categorized:
            for trigger in ACTION_TRIGGERS:
                if trigger in sentence_lower:
                    categories['actions'].append((i, sentence))
                    categorized = True
                    break
        
        if not categorized:
            for trigger in CONDITION_TRIGGERS:
                if trigger in sentence_lower:
                    categories['conditions'].append((i, sentence))
                    categorized = True
                    break
        
        if not categorized:
            for trigger in SPECIAL_TERMS:
                if trigger in sentence_lower:
                    categories['special_terms'].append((i, sentence))
                    categorized = True
                    break
        
        if not categorized:
            categories['other'].append((i, sentence))
    
    return categories


def extract_important_sentences(text: str, verbosity: str = "normal") -> List[str]:
    """Извлекает важные предложения с помощью TextRank"""
    if not SUMMARIZATION_AVAILABLE:
        sentences = extract_sentences(text)
        # Простой fallback - берем первые и последние предложения
        count = {"short": 3, "normal": 6, "detailed": 10}.get(verbosity, 6)
        return sentences[:count]
    
    try:
        # Определяем количество предложений
        sentence_count = {
            "short": 4,
            "normal": 8, 
            "detailed": 14
        }.get(verbosity, 8)
        
        # Используем TextRank
        parser = PlaintextParser.from_string(text, Tokenizer("russian"))
        summarizer = TextRankSummarizer()
        
        summary_sentences = summarizer(parser.document, sentence_count)
        return [str(sentence) for sentence in summary_sentences]
        
    except Exception as e:
        logger.warning(f"Ошибка TextRank, использую fallback: {e}")
        sentences = extract_sentences(text)
        count = {"short": 3, "normal": 6, "detailed": 10}.get(verbosity, 6)
        return sentences[:count]


def format_bullets(categories: Dict[str, List[Tuple[int, str]]], entities: Dict) -> str:
    """Форматирует саммари в виде маркированного списка"""
    result = []
    
    # Основные моменты
    if categories['agreements']:
        result.append("🤝 **Договоренности:**")
        for _, sentence in categories['agreements'][:3]:
            result.append(f"• {sentence}")
        result.append("")
    
    # Сроки
    if categories['deadlines']:
        result.append("⏰ **Сроки и расписание:**")
        for _, sentence in categories['deadlines'][:3]:
            result.append(f"• {sentence}")
        result.append("")
    
    # Действия
    if categories['actions']:
        result.append("✅ **Следующие шаги:**")
        for _, sentence in categories['actions'][:3]:
            result.append(f"• {sentence}")
        result.append("")
    
    # Условия
    if categories['conditions']:
        result.append("❓ **Условия и ограничения:**")
        for _, sentence in categories['conditions'][:2]:
            result.append(f"• {sentence}")
        result.append("")
    
    # Важные факты
    fact_check = []
    if entities['dates']:
        fact_check.append(f"Даты: {', '.join([str(d) for d in entities['dates'][:3]])}")
    if entities['money']:
        fact_check.append(f"Суммы: {', '.join([str(m) for m in entities['money'][:2]])}")
    
    if fact_check:
        result.append("🔍 **Проверка важного:**")
        result.append(f"• {'; '.join(fact_check)}")
    
    return "\n".join(result)


def format_paragraph(important_sentences: List[str], entities: Dict) -> str:
    """Форматирует саммари в виде абзацев"""
    # Группируем предложения в 2-3 абзаца
    paragraphs = []
    
    # Первый абзац - основное содержание
    if len(important_sentences) >= 3:
        paragraphs.append(" ".join(important_sentences[:3]))
    
    # Второй абзац - детали и следующие шаги
    if len(important_sentences) >= 6:
        paragraphs.append(" ".join(important_sentences[3:6]))
    
    # Третий абзац - дополнительная информация
    if len(important_sentences) > 6:
        paragraphs.append(" ".join(important_sentences[6:]))
    
    result = "\n\n".join(paragraphs)
    
    # Добавляем проверку важных фактов
    fact_check = []
    if entities['dates']:
        fact_check.append(f"даты: {', '.join([str(d) for d in entities['dates'][:3]])}")
    if entities['money']:
        fact_check.append(f"суммы: {', '.join([str(m) for m in entities['money'][:2]])}")
    
    if fact_check:
        result += f"\n\n**Важные факты:** {'; '.join(fact_check)}."
    
    return result


def format_structured(categories: Dict[str, List[Tuple[int, str]]], important_sentences: List[str], entities: Dict, verbosity: str) -> str:
    """Форматирует саммари в структурированном виде"""
    result = []
    
    # Краткий итог в 1-2 предложения
    if important_sentences:
        summary = " ".join(important_sentences[:2])
        result.append(f"📋 **Краткий итог:** {summary}")
        result.append("")
    
    # Договоренности
    if categories['agreements']:
        result.append("🤝 **Ключевые договоренности:**")
        count = 2 if verbosity == "short" else 3 if verbosity == "normal" else 4
        for _, sentence in categories['agreements'][:count]:
            result.append(f"• {sentence}")
        result.append("")
    
    # Сроки и расписание
    deadline_items = categories['deadlines'] + categories['special_terms']
    if deadline_items:
        result.append("⏰ **Сроки и расписание:**")
        count = 2 if verbosity == "short" else 3 if verbosity == "normal" else 4
        for _, sentence in deadline_items[:count]:
            result.append(f"• {sentence}")
        result.append("")
    
    # Следующие шаги
    if categories['actions']:
        result.append("✅ **Следующие шаги:**")
        count = 2 if verbosity == "short" else 3 if verbosity == "normal" else 5
        for _, sentence in categories['actions'][:count]:
            result.append(f"• {sentence}")
        result.append("")
    
    # Открытые вопросы
    if categories['conditions'] and verbosity != "short":
        result.append("❓ **Открытые вопросы:**")
        for _, sentence in categories['conditions'][:2]:
            result.append(f"• {sentence}")
        result.append("")
    
    # Проверка важного
    fact_check = []
    if entities.get('dates'):
        dates_str = ', '.join([str(d) for d in entities['dates'][:3]])
        fact_check.append(f"Даты/время: {dates_str}")
    
    if entities.get('money'):
        money_str = ', '.join([str(m) for m in entities['money'][:2]])
        fact_check.append(f"Суммы: {money_str}")
    
    # Ищем дополнительные важные факты в тексте
    important_facts = []
    all_text = " ".join([sent for _, sent in sum(categories.values(), [])])
    
    if re.search(r'\bбесплатн\w*', all_text, re.IGNORECASE):
        important_facts.append("бесплатные условия")
    if re.search(r'\bрасписани\w*', all_text, re.IGNORECASE):
        important_facts.append("вопросы расписания")
    if re.search(r'\bпервое занятие\b', all_text, re.IGNORECASE):
        important_facts.append("пробное занятие")
    
    if fact_check or important_facts:
        result.append("🔍 **Проверка важного:**")
        if fact_check:
            result.append(f"• {'; '.join(fact_check)}")
        if important_facts:
            result.append(f"• Отмечено: {', '.join(important_facts)}")
    
    return "\n".join(result)


def smart_summarize(transcript: Dict, format: str = "structured", verbosity: str = "normal") -> str:
    """
    Умная суммаризация транскрипта
    
    Args:
        transcript: результат transcribe_audio
        format: "structured" | "bullets" | "paragraph" 
        verbosity: "short" | "normal" | "detailed"
    
    Returns:
        Готовый текст саммари
    """
    
    if not SUMMARIZATION_AVAILABLE:
        # Простой fallback
        text = transcript.get("text", "")
        sentences = extract_sentences(text)
        count = {"short": 3, "normal": 5, "detailed": 8}.get(verbosity, 5)
        summary_sentences = sentences[:count]
        return "\n• ".join(summary_sentences)
    
    text = transcript.get("text", "")
    if not text or len(text) < 50:
        return "Слишком мало текста для суммаризации"
    
    try:
        logger.info(f"Начинаю умную суммаризацию: {len(text)} символов, формат={format}, подробность={verbosity}")
        
        # 1. Разбиваем на предложения
        sentences = extract_sentences(text)
        if len(sentences) < 2:
            return text
        
        # 2. Категоризируем предложения
        categories = categorize_sentences(sentences)
        
        # 3. Извлекаем важные предложения через TextRank
        important_sentences = extract_important_sentences(text, verbosity)
        
        # 4. Извлекаем сущности и даты
        entities = extract_entities_and_dates(text)
        
        # 5. Форматируем результат
        if format == "bullets":
            result = format_bullets(categories, entities)
        elif format == "paragraph":
            result = format_paragraph(important_sentences, entities)
        else:  # structured
            result = format_structured(categories, important_sentences, entities, verbosity)
        
        # Проверяем минимальную длину
        if len(result) < 100:
            # Добавляем еще предложений
            additional = important_sentences[len(important_sentences)//2:]
            if format == "paragraph":
                result += "\n\n" + " ".join(additional[:3])
            else:
                result += "\n\n📄 **Дополнительно:**\n• " + "\n• ".join(additional[:3])
        
        logger.info(f"Суммаризация завершена: {len(result)} символов")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка умной суммаризации: {e}")
        
        # Fallback к простой суммаризации
        sentences = extract_sentences(text)
        count = {"short": 4, "normal": 8, "detailed": 12}.get(verbosity, 8)
        summary_sentences = sentences[:count]
        
        if format == "bullets":
            return "• " + "\n• ".join(summary_sentences)
        else:
            return "\n\n".join([" ".join(summary_sentences[i:i+3]) for i in range(0, len(summary_sentences), 3)])


def check_summarization_availability() -> Dict[str, bool]:
    """Проверяет доступность компонентов суммаризации"""
    availability = {
        "razdel": False,
        "sumy": False,
        "rutermextract": False,
        "natasha": False
    }
    
    try:
        import razdel
        availability["razdel"] = True
    except ImportError:
        pass
    
    try:
        from sumy.summarizers.text_rank import TextRankSummarizer
        availability["sumy"] = True
    except ImportError:
        pass
    
    try:
        import rutermextract
        availability["rutermextract"] = True
    except ImportError:
        pass
    
    try:
        from natasha import Segmenter
        availability["natasha"] = True
    except ImportError:
        pass
    
    return availability


def get_summarization_info() -> str:
    """Возвращает информацию о доступности суммаризации"""
    availability = check_summarization_availability()
    
    available_count = sum(availability.values())
    total_count = len(availability)
    
    if available_count == total_count:
        return "Умная суммаризация полностью поддерживается"
    elif available_count >= 2:
        return f"Умная суммаризация частично поддерживается ({available_count}/{total_count} модулей)"
    else:
        return "Умная суммаризация недоступна - установите razdel, sumy, rutermextract, natasha"