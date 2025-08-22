"""
Модуль двухпроходной суммаризации с сохранением фактов
"""

from .pipeline import SummarizationPipeline, summarize_text_pipeline
from .fact_extractor import FactExtractor, extract_key_facts, select_must_keep_sentences

__all__ = [
    'SummarizationPipeline',
    'summarize_text_pipeline', 
    'FactExtractor',
    'extract_key_facts',
    'select_must_keep_sentences'
]