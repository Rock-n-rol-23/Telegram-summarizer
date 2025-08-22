"""
Модуль для извлечения ключевых фактов из текста с сохранением чисел, дат и валют
"""

import re
import logging
from typing import Dict, List, Set, Optional, Literal, Union
from datetime import datetime
try:
    import dateparser
except ImportError:
    # Fallback to simple dateparser
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'simple_deps'))
    from simple_dateparser import parse as dateparser_parse
    
    class DateparserFallback:
        @staticmethod
        def parse(text, languages=None):
            return dateparser_parse(text, languages)
    
    dateparser = DateparserFallback()

logger = logging.getLogger(__name__)

# Lazy imports for optional dependencies
natasha = None
spacy = None

def _import_natasha():
    """Lazy import for natasha"""
    global natasha
    if natasha is None:
        try:
            from natasha import (
                Segmenter, MorphVocab, NewsEmbedding, NewsMorphTagger,
                NewsSyntaxParser, NewsNERTagger, PER, LOC, ORG, Doc
            )
            natasha = {
                'Segmenter': Segmenter,
                'MorphVocab': MorphVocab,
                'NewsEmbedding': NewsEmbedding,
                'NewsMorphTagger': NewsMorphTagger,
                'NewsSyntaxParser': NewsSyntaxParser,
                'NewsNERTagger': NewsNERTagger,
                'PER': PER, 'LOC': LOC, 'ORG': ORG,
                'Doc': Doc
            }
        except ImportError:
            logger.warning("Natasha not available, falling back to regex-only mode")
            natasha = {}
    return natasha

def _import_spacy():
    """Lazy import for spacy"""
    global spacy
    if spacy is None:
        try:
            import spacy as sp
            spacy = sp
        except ImportError:
            logger.warning("spaCy not available, falling back to regex-only mode")
            spacy = {}
    return spacy

class FactExtractor:
    """Извлекатель ключевых фактов из текста"""
    
    def __init__(self):
        self.natasha_components = None
        self.spacy_en = None
        self._init_components()
    
    def _init_components(self):
        """Инициализация компонентов NER"""
        # Natasha для русского
        natasha_lib = _import_natasha()
        if natasha_lib:
            try:
                segmenter = natasha_lib['Segmenter']()
                morph_vocab = natasha_lib['MorphVocab']()
                emb = natasha_lib['NewsEmbedding']()
                morph_tagger = natasha_lib['NewsMorphTagger'](emb)
                syntax_parser = natasha_lib['NewsSyntaxParser'](emb)
                ner_tagger = natasha_lib['NewsNERTagger'](emb)
                
                self.natasha_components = {
                    'segmenter': segmenter,
                    'morph_vocab': morph_vocab,
                    'morph_tagger': morph_tagger,
                    'syntax_parser': syntax_parser,
                    'ner_tagger': ner_tagger,
                    'constants': natasha_lib
                }
                logger.info("Natasha components initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Natasha: {e}")
        
        # spaCy для английского
        spacy_lib = _import_spacy()
        if spacy_lib:
            try:
                self.spacy_en = spacy_lib.load("en_core_web_sm")
                logger.info("spaCy EN model loaded")
            except Exception as e:
                logger.warning(f"spaCy EN model not available: {e}")

    def extract_numbers(self, text: str) -> List[Dict]:
        """Извлечение чисел, валют, процентов, диапазонов"""
        numbers = []
        
        # Паттерны для различных типов чисел
        patterns = {
            'percentage': r'\b(\d+(?:[,.]?\d+)?)\s*%',
            'currency_rub': r'(\d+(?:\s?\d{3})*(?:[,.]?\d+)?)\s*(?:₽|руб\.?|рублей?)',
            'currency_usd': r'(?:\$|USD\s*)(\d+(?:\s?\d{3})*(?:[,.]?\d+)?)',
            'currency_eur': r'(?:€|EUR\s*)(\d+(?:\s?\d{3})*(?:[,.]?\d+)?)',
            'millions': r'(\d+(?:[,.]?\d+)?)\s*(?:млн\.?|миллион[ов]?)',
            'billions': r'(\d+(?:[,.]?\d+)?)\s*(?:млрд\.?|миллиард[ов]?)',
            'thousands': r'(\d+(?:[,.]?\d+)?)\s*(?:тыс\.?|тысяч[и]?)',
            'decimal': r'\b(\d+[,.]?\d+)\b',
            'range': r'(\d+(?:[,.]?\d+)?)\s*[-–—]\s*(\d+(?:[,.]?\d+)?)',
            'basis_points': r'([+-]?\d+(?:[,.]?\d+)?)\s*б\.п\.',
        }
        
        for number_type, pattern in patterns.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                raw_text = match.group(0)
                
                if number_type == 'percentage':
                    norm_value = float(match.group(1).replace(',', '.')) / 100
                    unit = '%'
                elif 'currency' in number_type:
                    raw_num = match.group(1).replace(' ', '').replace(',', '.')
                    norm_value = float(raw_num)
                    unit = 'RUB' if 'rub' in number_type else ('USD' if 'usd' in number_type else 'EUR')
                elif number_type in ['millions', 'billions', 'thousands']:
                    raw_num = match.group(1).replace(',', '.')
                    multiplier = 1000000 if 'millions' in number_type else (1000000000 if 'billions' in number_type else 1000)
                    norm_value = float(raw_num) * multiplier
                    unit = 'count'
                elif number_type == 'range':
                    start = float(match.group(1).replace(',', '.'))
                    end = float(match.group(2).replace(',', '.'))
                    norm_value = [start, end]
                    unit = 'range'
                elif number_type == 'basis_points':
                    norm_value = float(match.group(1).replace(',', '.')) / 10000
                    unit = 'bp'
                else:
                    norm_value = float(match.group(1).replace(',', '.'))
                    unit = None
                
                numbers.append({
                    'raw': raw_text,
                    'norm': norm_value,
                    'unit': unit,
                    'type': number_type,
                    'position': match.span()
                })
        
        return numbers

    def extract_dates(self, text: str, lang: str = 'ru') -> List[Dict]:
        """Извлечение дат и временных периодов"""
        dates = []
        
        # Паттерны для дат
        date_patterns = [
            r'\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})?\b',
            r'\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b',
            r'\b(к|до)\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b',
            r'\b(январ[ья]|феврал[ья]|март[ае]|апрел[ья]|ма[ея]|июн[ья]|июл[ья]|август[ае]|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])\s+(\d{4})?\b',
            r'\b(понедельник|вторник|среда|четверг|пятница|суббота|воскресенье)\b',
            r'\b(завтра|послезавтра|вчера|позавчера|сегодня)\b',
            r'\b(\d{1,2}):(\d{2})\b'
        ]
        
        for pattern in date_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                raw_text = match.group(0)
                
                # Пытаемся парсить дату через dateparser
                try:
                    parsed_date = dateparser.parse(
                        raw_text, 
                        languages=['ru', 'en'] if lang == 'ru' else ['en', 'ru']
                    )
                    norm_date = parsed_date.strftime('%Y-%m-%d') if parsed_date else None
                except:
                    norm_date = None
                
                dates.append({
                    'raw': raw_text,
                    'norm': norm_date,
                    'position': match.span()
                })
        
        return dates

    def extract_entities_natasha(self, text: str) -> Dict[str, List[str]]:
        """Извлечение именованных сущностей через Natasha (русский)"""
        if not self.natasha_components:
            return {'PERSON': [], 'ORG': [], 'GPE': []}
        
        try:
            doc = self.natasha_components['constants']['Doc'](text)
            doc.segment(self.natasha_components['segmenter'])
            doc.tag_morph(self.natasha_components['morph_tagger'])
            doc.parse_syntax(self.natasha_components['syntax_parser'])
            doc.tag_ner(self.natasha_components['ner_tagger'])
            
            entities = {'PERSON': [], 'ORG': [], 'GPE': []}
            
            for span in doc.spans:
                if span.type == self.natasha_components['constants']['PER'].name:
                    entities['PERSON'].append(span.text)
                elif span.type == self.natasha_components['constants']['ORG'].name:
                    entities['ORG'].append(span.text)
                elif span.type == self.natasha_components['constants']['LOC'].name:
                    entities['GPE'].append(span.text)
            
            # Убираем дубликаты
            for key in entities:
                entities[key] = list(set(entities[key]))
            
            return entities
        
        except Exception as e:
            logger.warning(f"Natasha NER failed: {e}")
            return {'PERSON': [], 'ORG': [], 'GPE': []}

    def extract_entities_spacy(self, text: str) -> Dict[str, List[str]]:
        """Извлечение именованных сущностей через spaCy (английский)"""
        if not self.spacy_en:
            return {'PERSON': [], 'ORG': [], 'GPE': []}
        
        try:
            doc = self.spacy_en(text)
            entities = {'PERSON': [], 'ORG': [], 'GPE': []}
            
            for ent in doc.ents:
                if ent.label_ == 'PERSON':
                    entities['PERSON'].append(ent.text)
                elif ent.label_ == 'ORG':
                    entities['ORG'].append(ent.text)
                elif ent.label_ in ['GPE', 'LOC']:
                    entities['GPE'].append(ent.text)
            
            # Убираем дубликаты
            for key in entities:
                entities[key] = list(set(entities[key]))
            
            return entities
        
        except Exception as e:
            logger.warning(f"spaCy NER failed: {e}")
            return {'PERSON': [], 'ORG': [], 'GPE': []}

    def extract_key_facts(self, text: str, lang: Literal["ru", "en"] = "ru") -> Dict:
        """
        Основная функция извлечения ключевых фактов
        
        Returns:
            {
                "sentences_with_numbers": [...],
                "money": [...],
                "dates": [...],
                "entities": {"ORG": [...], "PERSON": [...], "GPE": [...]}
            }
        """
        # Разбиваем на предложения
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Извлекаем числа и валюты
        numbers = self.extract_numbers(text)
        dates = self.extract_dates(text, lang)
        
        # NER в зависимости от языка
        if lang == 'ru':
            entities = self.extract_entities_natasha(text)
        else:
            entities = self.extract_entities_spacy(text)
        
        # Привязываем числа к предложениям
        sentences_with_numbers = []
        money_facts = []
        
        for i, sentence in enumerate(sentences):
            sentence_numbers = []
            sentence_money = []
            
            # Ищем числа в этом предложении
            for num in numbers:
                start_pos = sum(len(sentences[j]) + 1 for j in range(i))
                end_pos = start_pos + len(sentence)
                
                if start_pos <= num['position'][0] <= end_pos:
                    sentence_numbers.append(num)
                    
                    # Выделяем денежные суммы
                    if num['unit'] in ['RUB', 'USD', 'EUR']:
                        money_facts.append({
                            'raw': num['raw'],
                            'norm': num['norm'],
                            'currency': num['unit'],
                            'sentence_i': i
                        })
            
            if sentence_numbers:
                sentences_with_numbers.append({
                    'i': i,
                    'text': sentence,
                    'numbers': sentence_numbers
                })
        
        return {
            'sentences_with_numbers': sentences_with_numbers,
            'money': money_facts,
            'dates': dates,
            'entities': entities,
            'all_numbers': numbers
        }

    def select_must_keep_sentences(self, facts: Dict, min_facts_per_sentence: int = 1) -> Set[int]:
        """
        Выбирает индексы предложений, которые обязательно нужно сохранить
        """
        must_keep = set()
        
        # Предложения с числами
        for sent_data in facts['sentences_with_numbers']:
            if len(sent_data['numbers']) >= min_facts_per_sentence:
                must_keep.add(sent_data['i'])
        
        # Предложения с денежными суммами (высокий приоритет)
        for money in facts['money']:
            if money.get('sentence_i') is not None:
                must_keep.add(money['sentence_i'])
        
        return must_keep


def extract_key_facts(text: str, lang: Literal["ru", "en"] = "ru") -> Dict:
    """Функция-обертка для извлечения ключевых фактов"""
    extractor = FactExtractor()
    return extractor.extract_key_facts(text, lang)


def select_must_keep_sentences(facts: Dict, min_facts_per_sentence: int = 1) -> Set[int]:
    """Функция-обертка для выбора обязательных предложений"""
    extractor = FactExtractor()
    return extractor.select_must_keep_sentences(facts, min_facts_per_sentence)