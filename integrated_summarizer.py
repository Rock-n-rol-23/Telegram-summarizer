"""
Интегрированная система суммаризации для Telegram бота
Объединяет новую двухфазную систему с существующими возможностями
"""

import logging
import json
import asyncio
from typing import Dict, List, Optional, Union
from datetime import datetime

logger = logging.getLogger(__name__)

class IntegratedSummarizer:
    """Интегрированная система суммаризации с поддержкой новых возможностей"""
    
    def __init__(self, groq_client, fallback_enabled=True):
        self.groq_client = groq_client
        self.fallback_enabled = fallback_enabled
        
        # Пытаемся загрузить новые модули
        try:
            from summarization.fact_extractor import extract_key_facts, select_must_keep_sentences
            from quality.quality_checks import validate_numbers_preserved, extract_critical_numbers, calculate_quality_score
            from content_extraction.web_extractor import extract_page_content, extract_tables_as_markdown
            
            self.extract_key_facts = extract_key_facts
            self.select_must_keep_sentences = select_must_keep_sentences
            self.validate_numbers_preserved = validate_numbers_preserved
            self.extract_critical_numbers = extract_critical_numbers
            self.calculate_quality_score = calculate_quality_score
            self.extract_page_content = extract_page_content
            self.extract_tables_as_markdown = extract_tables_as_markdown
            
            self.advanced_features = True
            logger.info("Интегрированная система суммаризации загружена с расширенными возможностями")
            
        except ImportError as e:
            self.advanced_features = False
            logger.warning(f"Расширенные возможности недоступны, используется базовая система: {e}")
    
    async def summarize_text_enhanced(self, 
                                    text: str, 
                                    lang: str = "ru",
                                    target_ratio: float = 0.3,
                                    format_type: str = "bullets",
                                    preserve_tables: bool = True) -> Dict[str, any]:
        """
        Расширенная суммаризация с сохранением фактов
        """
        
        if not self.advanced_features or not self.groq_client:
            # Fallback к стандартной суммаризации
            return await self._fallback_summarize(text, target_ratio, format_type)
        
        try:
            # Фаза 1: Извлечение фактов
            logger.info("📊 Phase 1: Извлечение ключевых фактов")
            facts = self.extract_key_facts(text, lang)
            
            # Фаза 2: Создание структурированного JSON резюме
            logger.info("🔍 Phase 2: Создание JSON структуры")
            json_summary = await self._create_json_summary(text, facts, lang, target_ratio, format_type)
            
            if not json_summary.get('success'):
                logger.warning("JSON суммаризация не удалась, используем fallback")
                return await self._fallback_summarize(text, target_ratio, format_type)
            
            # Фаза 3: Создание финального текста
            logger.info("✍️ Phase 3: Создание финального резюме")
            final_summary = await self._create_final_summary(json_summary['content'], text, format_type, lang)
            
            # Проверка качества
            quality_report = self._assess_quality(text, final_summary)
            
            return {
                'success': True,
                'summary': final_summary,
                'method': 'enhanced_pipeline',
                'quality_report': quality_report,
                'facts_extracted': len(facts.get('all_numbers', [])),
                'compression_ratio': len(final_summary) / len(text) if text else 0
            }
            
        except Exception as e:
            logger.error(f"Ошибка расширенной суммаризации: {e}")
            return await self._fallback_summarize(text, target_ratio, format_type)
    
    async def _create_json_summary(self, text: str, facts: Dict, lang: str, target_ratio: float, format_type: str) -> Dict:
        """Создание структурированного JSON резюме"""
        
        try:
            # Определяем целевую длину
            target_length = max(100, int(len(text) * target_ratio))
            
            # Промпт для JSON создания
            prompt = f"""Создай структурированное резюме на {lang} языке в JSON формате.

ИСХОДНЫЙ ТЕКСТ ({len(text)} символов):
{text}

ТРЕБОВАНИЯ:
- Целевая длина: {target_length} символов
- Формат: {format_type}
- Обязательно сохрани все числа, проценты, валюты, даты
- Структура JSON:
{{
  "bullets": ["пункт 1", "пункт 2", "пункт 3"],
  "key_facts": [
    {{"value_raw": "25%", "value_norm": 0.25, "unit": "%"}},
    {{"value_raw": "3 млрд рублей", "value_norm": 3000000000, "unit": "RUB"}}
  ],
  "entities": {{"ORG": [], "PERSON": [], "GPE": []}},
  "main_topics": ["тема 1", "тема 2"]
}}

ВАЖНО: Ответь только валидным JSON, без дополнительного текста."""

            logger.info("🤖 Отправка запроса для JSON суммаризации")
            response = self.groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Ты эксперт по анализу текста. Создавай только валидный JSON."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.2,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            json_data = json.loads(result_text)
            
            logger.info(f"✅ JSON суммаризация успешна: {len(json_data.get('bullets', []))} bullets")
            return {'success': True, 'content': json_data}
            
        except Exception as e:
            logger.error(f"Ошибка JSON суммаризации: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _create_final_summary(self, json_data: Dict, original_text: str, format_type: str, lang: str) -> str:
        """Создание финального текстового резюме"""
        
        try:
            # Извлекаем элементы из JSON
            bullets = json_data.get('bullets', [])
            key_facts = json_data.get('key_facts', [])
            main_topics = json_data.get('main_topics', [])
            
            # Создаем блок фактов
            facts_block = self._create_facts_block(key_facts)
            
            # Формируем финальное резюме
            if format_type == 'bullets':
                summary_parts = []
                
                # Основные пункты
                if bullets:
                    for bullet in bullets[:5]:  # Максимум 5 bullets
                        summary_parts.append(f"• {bullet}")
                
                # Блок с фактами
                if facts_block:
                    summary_parts.append(f"\n🔢 Цифры и факты:\n{facts_block}")
                
                return '\n'.join(summary_parts)
                
            elif format_type == 'paragraph':
                # Параграфный формат
                main_text = '. '.join(bullets) if bullets else ""
                if facts_block:
                    return f"{main_text}\n\n🔢 Цифры и факты:\n{facts_block}"
                return main_text
                
            elif format_type == 'structured':
                # Структурированный формат
                sections = []
                
                if main_topics:
                    sections.append(f"📋 Основные темы: {', '.join(main_topics[:3])}")
                
                if bullets:
                    sections.append("📝 Ключевые моменты:")
                    for bullet in bullets[:4]:
                        sections.append(f"• {bullet}")
                
                if facts_block:
                    sections.append(f"🔢 Цифры и факты:\n{facts_block}")
                
                return '\n'.join(sections)
            
            # По умолчанию bullets
            return '\n'.join(f"• {bullet}" for bullet in bullets[:5])
            
        except Exception as e:
            logger.error(f"Ошибка создания финального резюме: {e}")
            # Простое fallback
            bullets = json_data.get('bullets', [])
            return '\n'.join(f"• {bullet}" for bullet in bullets[:3]) if bullets else "Резюме недоступно"
    
    def _create_facts_block(self, key_facts: List[Dict]) -> str:
        """Создание блока с ключевыми фактами"""
        
        if not key_facts:
            return ""
        
        facts_lines = []
        for fact in key_facts[:8]:  # Максимум 8 фактов
            raw_value = fact.get('value_raw', '')
            if raw_value:
                facts_lines.append(f"— {raw_value}")
        
        return '\n'.join(facts_lines) if facts_lines else ""
    
    def _assess_quality(self, original_text: str, summary: str) -> Dict:
        """Оценка качества резюме"""
        
        if not self.advanced_features:
            return {
                'quality_score': 0.7,
                'numbers_preserved': True,
                'missing_numbers': [],
                'language_correct': True,
                'compression_ratio': len(summary) / len(original_text) if original_text else 0
            }
        
        try:
            # Проверка сохранности чисел
            is_preserved, missing = self.validate_numbers_preserved(original_text, summary)
            
            # Общая оценка качества
            quality_score = self.calculate_quality_score(original_text, summary)
            
            return {
                'quality_score': quality_score,
                'numbers_preserved': is_preserved,
                'missing_numbers': missing,
                'language_correct': True,
                'compression_ratio': len(summary) / len(original_text) if original_text else 0
            }
            
        except Exception as e:
            logger.error(f"Ошибка оценки качества: {e}")
            return {
                'quality_score': 0.6,
                'numbers_preserved': False,
                'missing_numbers': [],
                'language_correct': True,
                'compression_ratio': 0.3
            }
    
    async def _fallback_summarize(self, text: str, target_ratio: float, format_type: str) -> Dict:
        """Fallback суммаризация при недоступности расширенных возможностей"""
        
        try:
            if self.groq_client:
                # Используем базовую Groq суммаризацию
                summary = await self._basic_groq_summarize(text, target_ratio, format_type)
            else:
                # Простейший fallback
                summary = self._simple_text_summary(text, target_ratio)
            
            # Добавляем блок фактов если возможно
            if self.advanced_features:
                numbers = self.extract_critical_numbers(text)
                if numbers:
                    facts_block = '\n'.join(f"— {num}" for num in numbers[:6])
                    summary += f"\n\n🔢 Цифры и факты:\n{facts_block}"
            
            return {
                'success': True,
                'summary': summary,
                'method': 'fallback',
                'quality_report': {
                    'quality_score': 0.6,
                    'numbers_preserved': False,
                    'missing_numbers': [],
                    'language_correct': True,
                    'compression_ratio': target_ratio
                }
            }
            
        except Exception as e:
            logger.error(f"Ошибка fallback суммаризации: {e}")
            return {
                'success': False,
                'error': str(e),
                'method': 'failed'
            }
    
    async def _basic_groq_summarize(self, text: str, target_ratio: float, format_type: str) -> str:
        """Базовая суммаризация через Groq"""
        
        target_length = int(len(text) * target_ratio)
        
        prompt = f"""Создай краткое резюме текста на том же языке.

Требования:
- Длина: примерно {target_length} символов
- Формат: {"маркированный список" if format_type == "bullets" else "структурированный текст"}
- Сохрани важные числа, проценты, даты
- Используй понятный язык

ТЕКСТ:
{text[:3000]}

РЕЗЮМЕ:"""
        
        response = self.groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=800
        )
        
        return response.choices[0].message.content.strip()
    
    def _simple_text_summary(self, text: str, target_ratio: float) -> str:
        """Простейшая суммаризация без AI"""
        
        import re
        
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        
        # Берем первые предложения
        target_sentences = max(1, int(len(sentences) * target_ratio))
        summary_sentences = sentences[:target_sentences]
        
        summary = '. '.join(summary_sentences)
        if len(summary) > 800:
            summary = summary[:800] + "..."
        
        return summary
    
    async def extract_web_content_enhanced(self, url: str) -> Dict:
        """Расширенное извлечение веб-контента с таблицами"""
        
        if not self.advanced_features:
            return {'success': False, 'error': 'Расширенные возможности недоступны'}
        
        try:
            # Используем новый экстрактор
            page = self.extract_page_content(url)
            
            if not page:
                return {'success': False, 'error': 'Не удалось извлечь контент страницы'}
            
            # Добавляем извлечение таблиц если есть
            tables_info = ""
            if hasattr(page, 'raw_html'):
                tables_markdown = self.extract_tables_as_markdown(page.raw_html)
                if tables_markdown:
                    tables_info = f"\n\n[ТАБЛИЦЫ НА СТРАНИЦЕ]\n{tables_markdown}"
            
            return {
                'success': True,
                'title': page.title,
                'content': page.text + tables_info,
                'url': page.final_url,
                'word_count': page.word_count,
                'has_tables': bool(tables_info),
                'links': page.links[:5]  # Первые 5 ссылок
            }
            
        except Exception as e:
            logger.error(f"Ошибка расширенного извлечения веб-контента: {e}")
            return {'success': False, 'error': str(e)}

# Создание глобального экземпляра для использования в боте
integrated_summarizer = None

def get_integrated_summarizer(groq_client):
    """Получение экземпляра интегрированной системы суммаризации"""
    global integrated_summarizer
    
    if integrated_summarizer is None:
        integrated_summarizer = IntegratedSummarizer(groq_client)
    
    return integrated_summarizer