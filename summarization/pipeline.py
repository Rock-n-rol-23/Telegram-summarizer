"""
Двухпроходная система суммаризации с гарантированным сохранением фактов
"""

import json
import logging
import re
from typing import Dict, List, Optional, Literal, Union
from pathlib import Path

from .fact_extractor import extract_key_facts, select_must_keep_sentences
from quality.quality_checks import (
    validate_numbers_preserved, 
    check_summary_quality,
    validate_json_structure,
    trim_to_length
)

logger = logging.getLogger(__name__)

class SummarizationPipeline:
    """Двухфазная система суммаризации с контролем качества"""
    
    def __init__(self, groq_client, fallback_summarizer=None):
        self.groq_client = groq_client
        self.fallback_summarizer = fallback_summarizer
        self.prompts = self._load_prompts()
    
    def _load_prompts(self) -> Dict[str, str]:
        """Загрузка промптов из файла"""
        prompts_file = Path(__file__).parent.parent / "prompts" / "llm_summarize.txt"
        
        try:
            with open(prompts_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Парсим промпты
            prompts = {}
            current_key = None
            current_content = []
            
            for line in content.split('\n'):
                if line.startswith(('SYSTEM_PROMPT_', 'USER_PROMPT_', 'FIXUP_PROMPT:', 'FALLBACK_PROMPT:')):
                    if current_key:
                        prompts[current_key] = '\n'.join(current_content).strip()
                    current_key = line.rstrip(':')
                    current_content = []
                else:
                    current_content.append(line)
            
            if current_key:
                prompts[current_key] = '\n'.join(current_content).strip()
            
            logger.info(f"Loaded {len(prompts)} prompts")
            return prompts
        
        except Exception as e:
            logger.error(f"Failed to load prompts: {e}")
            return self._get_fallback_prompts()
    
    def _get_fallback_prompts(self) -> Dict[str, str]:
        """Промпты по умолчанию если файл не загрузился"""
        return {
            'SYSTEM_PROMPT_PHASE_A': """Ты — педантичный редактор-саммаризатор. Сохраняй все числа, даты, проценты, денежные суммы и имена. Отвечай только валидным JSON с полями: bullets, key_facts, entities, uncertainties.""",
            'USER_PROMPT_PHASE_A': """LANGUAGE={language}\nFORMAT={format}\nTEXT=<<<\n{text}\n>>>""",
            'SYSTEM_PROMPT_PHASE_B': """Создай финальное читабельное изложение. Включи все факты. В конце добавь блок "🔢 Цифры и факты".""",
            'USER_PROMPT_PHASE_B': """JSON_DATA=<<<\n{json_data}\n>>>\nFORMAT={format}\nLANGUAGE={language}""",
            'FALLBACK_PROMPT': """Создай краткое изложение с сохранением всех чисел и дат. В конце блок "🔢 Цифры и факты"."""
        }
    
    def _split_into_chunks(self, text: str, max_chars: int = 2800) -> List[str]:
        """Разбивка текста на чанки с сохранением структуры"""
        if len(text) <= max_chars:
            return [text]
        
        chunks = []
        
        # Сначала пробуем разбить по заголовкам
        header_pattern = r'\n\n(?=[А-ЯЁA-Z].*:|\d+\.|\*|#)'
        sections = re.split(header_pattern, text)
        
        current_chunk = ""
        for section in sections:
            if len(current_chunk + section) <= max_chars:
                current_chunk += section
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = section
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # Если чанки все еще слишком большие, разбиваем по предложениям
        final_chunks = []
        for chunk in chunks:
            if len(chunk) <= max_chars:
                final_chunks.append(chunk)
            else:
                sentences = re.split(r'[.!?]+', chunk)
                sub_chunk = ""
                for sentence in sentences:
                    if len(sub_chunk + sentence) <= max_chars:
                        sub_chunk += sentence + ". "
                    else:
                        if sub_chunk:
                            final_chunks.append(sub_chunk.strip())
                        sub_chunk = sentence + ". "
                
                if sub_chunk:
                    final_chunks.append(sub_chunk.strip())
        
        return final_chunks
    
    async def _llm_phase_a(self, text: str, language: str, format_type: str, 
                          target_chars: int, must_keep_indexes: List[int]) -> Optional[Dict]:
        """Первая фаза LLM - извлечение структурированных данных в JSON"""
        
        system_prompt = self.prompts.get('SYSTEM_PROMPT_PHASE_A', '')
        user_prompt = self.prompts.get('USER_PROMPT_PHASE_A', '').format(
            language=language,
            format=format_type,
            target_chars=target_chars,
            must_keep_indexes=must_keep_indexes,
            text=text
        )
        
        try:
            response = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            json_data = json.loads(result_text)
            
            # Валидация структуры
            is_valid, errors = validate_json_structure(json_data)
            if not is_valid:
                logger.warning(f"Invalid JSON structure: {errors}")
                return None
            
            return json_data
        
        except Exception as e:
            logger.error(f"Phase A failed: {e}")
            return None
    
    async def _llm_phase_b(self, json_data: Dict, language: str, 
                          format_type: str, target_chars: int) -> Optional[str]:
        """Вторая фаза LLM - генерация финального читабельного текста"""
        
        system_prompt = self.prompts.get('SYSTEM_PROMPT_PHASE_B', '').format(
            format=format_type, language=language, target_chars=target_chars
        )
        user_prompt = self.prompts.get('USER_PROMPT_PHASE_B', '').format(
            json_data=json.dumps(json_data, ensure_ascii=False, indent=2),
            target_chars=target_chars,
            format=format_type,
            language=language
        )
        
        try:
            response = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=3000
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"Phase B failed: {e}")
            return None
    
    def _merge_json_chunks(self, json_chunks: List[Dict]) -> Dict:
        """Объединение JSON данных из нескольких чанков"""
        merged = {
            'bullets': [],
            'key_facts': [],
            'entities': {'ORG': [], 'PERSON': [], 'GPE': []},
            'uncertainties': []
        }
        
        seen_facts = set()  # Для дедупликации
        
        for chunk_data in json_chunks:
            # Объединяем bullets
            merged['bullets'].extend(chunk_data.get('bullets', []))
            
            # Объединяем key_facts с дедупликацией
            for fact in chunk_data.get('key_facts', []):
                fact_key = fact.get('value_raw', '').strip().lower()
                if fact_key and fact_key not in seen_facts:
                    seen_facts.add(fact_key)
                    merged['key_facts'].append(fact)
            
            # Объединяем entities
            for entity_type in ['ORG', 'PERSON', 'GPE']:
                entities_list = chunk_data.get('entities', {}).get(entity_type, [])
                merged['entities'][entity_type].extend(entities_list)
            
            # Объединяем uncertainties
            merged['uncertainties'].extend(chunk_data.get('uncertainties', []))
        
        # Убираем дубликаты из entities
        for entity_type in merged['entities']:
            merged['entities'][entity_type] = list(set(merged['entities'][entity_type]))
        
        # Ограничиваем количество bullets до разумного
        if len(merged['bullets']) > 12:
            merged['bullets'] = merged['bullets'][:12]
        
        return merged
    
    def _create_fallback_summary(self, text: str, language: str, 
                                format_type: str, target_chars: int) -> str:
        """Создание суммари без LLM (fallback)"""
        logger.info("Creating fallback summary without LLM")
        
        # Извлекаем факты
        facts = extract_key_facts(text, language)
        
        # Создаем простое изложение через TextRank или первые предложения
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Берем первые предложения + обязательные
        must_keep = select_must_keep_sentences(facts)
        selected_sentences = []
        
        # Сначала обязательные предложения
        for i in must_keep:
            if i < len(sentences):
                selected_sentences.append(sentences[i])
        
        # Потом добавляем первые предложения до нужной длины
        current_length = sum(len(s) for s in selected_sentences)
        for i, sentence in enumerate(sentences):
            if i not in must_keep and current_length < target_chars * 0.7:
                selected_sentences.append(sentence)
                current_length += len(sentence)
        
        # Формируем основной текст
        if format_type == 'bullets':
            main_text = '\n'.join(f"• {s}" for s in selected_sentences[:8])
        else:
            main_text = '. '.join(selected_sentences) + '.'
        
        # Добавляем блок с цифрами
        facts_block = self._create_facts_block(facts)
        
        result = f"{main_text}\n\n{facts_block}"
        return trim_to_length(result, target_chars)
    
    def _create_facts_block(self, facts: Dict) -> str:
        """Создание блока с цифрами и фактами"""
        facts_lines = []
        
        # Денежные суммы
        for money in facts.get('money', []):
            facts_lines.append(f"— {money['raw']}")
        
        # Другие числа
        for sent_data in facts.get('sentences_with_numbers', []):
            for num in sent_data['numbers']:
                if num['unit'] not in ['RUB', 'USD', 'EUR']:  # Не дублируем валюты
                    facts_lines.append(f"— {num['raw']}")
        
        # Даты
        for date in facts.get('dates', []):
            facts_lines.append(f"— {date['raw']}")
        
        if facts_lines:
            return "🔢 Цифры и факты:\n" + '\n'.join(facts_lines[:10])
        else:
            return "🔢 Цифры и факты: не обнаружены"
    
    async def summarize_text_pipeline(self, text: str, lang: Literal["ru", "en"] = "ru", 
                                    target_chars: int = 1000, 
                                    format_type: Literal["bullets", "paragraph", "structured"] = "bullets") -> Dict:
        """
        Основная функция двухпроходной суммаризации
        
        Returns:
            {
                'success': bool,
                'summary': str,
                'quality_report': dict,
                'method': str  # 'llm_two_phase', 'fallback'
            }
        """
        logger.info(f"Starting summarization pipeline: {len(text)} chars, {lang}, {format_type}")
        
        # Извлекаем факты из исходного текста
        source_facts = extract_key_facts(text, lang)
        must_keep_sentences = list(select_must_keep_sentences(source_facts))
        
        # Если Groq недоступен, используем fallback
        if not self.groq_client:
            summary = self._create_fallback_summary(text, lang, format_type, target_chars)
            quality_report = check_summary_quality(text, summary, lang, target_chars)
            
            return {
                'success': True,
                'summary': summary,
                'quality_report': quality_report,
                'method': 'fallback'
            }
        
        try:
            # Разбиваем на чанки
            chunks = self._split_into_chunks(text, max_chars=2800)
            logger.info(f"Split into {len(chunks)} chunks")
            
            # Фаза A для каждого чанка
            json_chunks = []
            for i, chunk in enumerate(chunks):
                logger.info(f"Processing chunk {i+1}/{len(chunks)}")
                
                chunk_json = await self._llm_phase_a(
                    chunk, lang, format_type, target_chars // len(chunks), must_keep_sentences
                )
                
                if chunk_json:
                    json_chunks.append(chunk_json)
                else:
                    logger.warning(f"Chunk {i+1} failed, skipping")
            
            if not json_chunks:
                logger.error("All chunks failed, falling back")
                summary = self._create_fallback_summary(text, lang, format_type, target_chars)
                quality_report = check_summary_quality(text, summary, lang, target_chars)
                return {
                    'success': True,
                    'summary': summary,
                    'quality_report': quality_report,
                    'method': 'fallback_after_failure'
                }
            
            # Объединяем JSON данные
            merged_json = self._merge_json_chunks(json_chunks)
            
            # Фаза B - финальная сборка
            final_summary = await self._llm_phase_b(merged_json, lang, format_type, target_chars)
            
            if not final_summary:
                logger.error("Phase B failed, falling back")
                summary = self._create_fallback_summary(text, lang, format_type, target_chars)
            else:
                summary = final_summary
            
            # Проверка качества
            quality_report = check_summary_quality(text, summary, lang, target_chars)
            
            # Если важные числа потеряны, пытаемся их восстановить
            if not quality_report['numbers_preserved'] and quality_report['missing_numbers']:
                logger.info("Attempting to recover missing numbers")
                recovery_result = await self._recover_missing_facts(summary, quality_report['missing_numbers'])
                if recovery_result:
                    summary = recovery_result
                    quality_report = check_summary_quality(text, summary, lang, target_chars)
            
            return {
                'success': True,
                'summary': summary,
                'quality_report': quality_report,
                'method': 'llm_two_phase',
                'chunks_processed': len(json_chunks),
                'source_facts': len(source_facts.get('all_numbers', []))
            }
        
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            
            # Окончательный fallback
            summary = self._create_fallback_summary(text, lang, format_type, target_chars)
            quality_report = check_summary_quality(text, summary, lang, target_chars)
            
            return {
                'success': True,
                'summary': summary,
                'quality_report': quality_report,
                'method': 'fallback_on_error',
                'error': str(e)
            }
    
    async def _recover_missing_facts(self, summary: str, missing_facts: List[str]) -> Optional[str]:
        """Попытка восстановить потерянные факты"""
        
        if not missing_facts:
            return summary
        
        fixup_prompt = self.prompts.get('FIXUP_PROMPT', '').format(
            missing_facts=', '.join(missing_facts)
        )
        
        try:
            response = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": fixup_prompt},
                    {"role": "user", "content": summary}
                ],
                temperature=0.1,
                max_tokens=1500
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"Fact recovery failed: {e}")
            
            # Простое добавление в конец
            facts_addition = "\n\nДополнительные факты: " + ", ".join(missing_facts)
            return summary + facts_addition


def summarize_text_pipeline(text: str, groq_client, lang: Literal["ru", "en"] = "ru",
                           target_chars: int = 1000, 
                           format_type: Literal["bullets", "paragraph", "structured"] = "bullets") -> Dict:
    """
    Функция-обертка для использования в других модулях
    """
    pipeline = SummarizationPipeline(groq_client)
    import asyncio
    
    # Если уже в async контексте, используем существующий loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # В async контексте - возвращаем корутину
            return pipeline.summarize_text_pipeline(text, lang, target_chars, format_type)
        else:
            # Синхронный контекст
            return loop.run_until_complete(
                pipeline.summarize_text_pipeline(text, lang, target_chars, format_type)
            )
    except RuntimeError:
        # Нет активного loop
        return asyncio.run(pipeline.summarize_text_pipeline(text, lang, target_chars, format_type))