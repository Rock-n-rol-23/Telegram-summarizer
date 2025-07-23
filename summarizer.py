"""
Модуль для суммаризации текста с использованием Groq API и Hugging Face fallback
"""

import asyncio
import logging
import re
from typing import Optional, List
from groq import Groq
import os

# Инициализация для локальной модели (lazy loading)
_local_tokenizer = None
_local_model = None
_transformers_available = False

try:
    from transformers import GPT2LMHeadModel, GPT2Tokenizer
    import torch
    _transformers_available = True
    logging.info("Transformers библиотека загружена успешно")
except ImportError:
    logging.warning("Transformers не установлен. Локальная модель недоступна. Используется только Groq API.")

logger = logging.getLogger(__name__)

class TextSummarizer:
    """Класс для суммаризации текста с множественными бэкендами"""
    
    def __init__(self, groq_api_key: str = None, use_local_fallback: bool = True):
        self.groq_api_key = groq_api_key
        self.use_local_fallback = use_local_fallback
        self.groq_client = None
        
        # Инициализация Groq API
        if self.groq_api_key:
            try:
                self.groq_client = Groq(api_key=self.groq_api_key)
                logger.info("Groq API клиент инициализирован")
            except Exception as e:
                logger.error(f"Ошибка инициализации Groq API: {e}")
                self.groq_client = None
        else:
            logger.warning("Groq API key не предоставлен")
        
        # Параметры для суммаризации
        self.groq_params = {
            "model": "llama-3.1-70b-versatile",
            "temperature": 0.3,
            "max_tokens": 2000,
            "top_p": 0.9,
            "stream": False
        }
        
        logger.info(f"TextSummarizer инициализирован. Groq: {bool(self.groq_client)}, Local: {use_local_fallback and _transformers_available}")
    
    def _split_text_into_chunks(self, text: str, max_chunk_size: int = 4000) -> List[str]:
        """Разбивает длинный текст на логические чанки"""
        if len(text) <= max_chunk_size:
            return [text]
        
        # Попробуем разбить по абзацам
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) + 2 <= max_chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                
                # Если абзац слишком длинный, разбиваем по предложениям
                if len(paragraph) > max_chunk_size:
                    sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                    temp_chunk = ""
                    
                    for sentence in sentences:
                        if len(temp_chunk) + len(sentence) + 1 <= max_chunk_size:
                            if temp_chunk:
                                temp_chunk += " " + sentence
                            else:
                                temp_chunk = sentence
                        else:
                            if temp_chunk:
                                chunks.append(temp_chunk)
                            temp_chunk = sentence
                    
                    current_chunk = temp_chunk
                else:
                    current_chunk = paragraph
        
        if current_chunk:
            chunks.append(current_chunk)
        
        logger.info(f"Текст разбит на {len(chunks)} чанков")
        return chunks
    
    def _create_summarization_prompt(self, text: str, target_ratio: float = 0.3) -> str:
        """Создает промпт для суммаризации"""
        target_length = int(len(text) * target_ratio)
        
        prompt = f"""Ты - эксперт по суммаризации текстов. Создай краткое саммари следующего текста на том же языке, что и исходный текст.

Требования:
- Саммари должно быть примерно {target_length} символов (целевое сжатие: {target_ratio:.0%})
- Сохрани все ключевые моменты и важную информацию
- Используй структурированный формат с bullet points (•)
- Пиши естественным языком, сохраняя стиль исходного текста
- Если текст на русском - отвечай на русском языке
- Начни ответ сразу с саммари, без вступлений

Текст для суммаризации:
{text}"""
        
        return prompt
    
    async def _summarize_with_groq(self, text: str, target_ratio: float = 0.3) -> Optional[str]:
        """Суммаризация с использованием Groq API"""
        if not self.groq_client:
            return None
        
        try:
            prompt = self._create_summarization_prompt(text, target_ratio)
            
            logger.info(f"Отправка запроса в Groq API, длина текста: {len(text)} символов")
            
            # Асинхронный вызов Groq API
            response = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    **self.groq_params
                )
            )
            
            summary = response.choices[0].message.content.strip()
            
            logger.info(f"Получен ответ от Groq API, длина саммари: {len(summary)} символов")
            
            # Проверяем качество саммари
            if self._validate_summary(text, summary, target_ratio):
                return summary
            else:
                logger.warning("Саммари не прошло валидацию")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при работе с Groq API: {e}")
            return None
    
    def _initialize_local_model(self):
        """Ленивая инициализация локальной модели"""
        global _local_tokenizer, _local_model
        
        if not _transformers_available:
            return False
        
        if _local_tokenizer is None or _local_model is None:
            try:
                logger.info("Инициализация локальной модели...")
                model_name = "ai-forever/rugpt3large_based_on_gpt2"
                
                _local_tokenizer = GPT2Tokenizer.from_pretrained(model_name)
                _local_model = GPT2LMHeadModel.from_pretrained(model_name)
                
                # Добавляем pad_token если его нет
                if _local_tokenizer.pad_token is None:
                    _local_tokenizer.pad_token = _local_tokenizer.eos_token
                
                logger.info("Локальная модель инициализирована")
                return True
                
            except Exception as e:
                logger.error(f"Ошибка инициализации локальной модели: {e}")
                return False
        
        return True
    
    async def _summarize_with_local_model(self, text: str, target_ratio: float = 0.3) -> Optional[str]:
        """Суммаризация с использованием локальной модели"""
        if not self._initialize_local_model():
            return None
        
        try:
            logger.info(f"Использование локальной модели для суммаризации, длина текста: {len(text)} символов")
            
            # Создаем простой промпт для суммаризации
            prompt = f"Саммари: {text[:1000]}..."  # Берем первые 1000 символов для локальной модели
            
            # Токенизация
            inputs = _local_tokenizer.encode(prompt, return_tensors="pt", max_length=512, truncation=True)
            
            # Генерация в отдельном потоке
            outputs = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _local_model.generate(
                    inputs,
                    max_length=inputs.shape[1] + 200,
                    num_return_sequences=1,
                    temperature=0.7,
                    do_sample=True,
                    pad_token_id=_local_tokenizer.eos_token_id
                )
            )
            
            # Декодирование результата
            generated_text = _local_tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Извлекаем только сгенерированную часть
            summary = generated_text[len(prompt):].strip()
            
            # Простая постобработка
            if summary and len(summary) > 20:
                # Берем только первые несколько предложений
                sentences = re.split(r'(?<=[.!?])\s+', summary)
                target_length = int(len(text) * target_ratio)
                
                result = ""
                for sentence in sentences:
                    if len(result) + len(sentence) > target_length:
                        break
                    result += sentence + " "
                
                summary = result.strip()
                
                if summary:
                    logger.info(f"Локальная модель создала саммари длиной: {len(summary)} символов")
                    return summary
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при работе с локальной моделью: {e}")
            return None
    
    def _validate_summary(self, original_text: str, summary: str, target_ratio: float) -> bool:
        """Валидация качества саммари"""
        if not summary or len(summary) < 10:
            return False
        
        # Проверяем соотношение длин
        actual_ratio = len(summary) / len(original_text)
        
        # Допускаем отклонение от целевого соотношения
        min_ratio = max(0.15, target_ratio - 0.2)  # Минимум 15%
        max_ratio = min(0.8, target_ratio + 0.3)   # Максимум 80%
        
        if not (min_ratio <= actual_ratio <= max_ratio):
            logger.warning(f"Неподходящее соотношение: {actual_ratio:.2%} (цель: {target_ratio:.2%})")
            return False
        
        # Проверяем, что саммари не является копией исходного текста
        if summary.lower().strip() == original_text.lower().strip():
            logger.warning("Саммари идентично исходному тексту")
            return False
        
        return True
    
    def _create_simple_summary(self, text: str, target_ratio: float = 0.3) -> str:
        """Создание простого саммари как последний резерв"""
        target_length = int(len(text) * target_ratio)
        
        # Разбиваем на предложения
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        if len(sentences) <= 3:
            # Если предложений мало, просто обрезаем текст
            return text[:target_length] + "..."
        
        # Берем первое, среднее и последнее предложения
        summary_sentences = [
            sentences[0],
            sentences[len(sentences) // 2],
            sentences[-1]
        ]
        
        summary = "• " + "\n• ".join(summary_sentences)
        
        # Обрезаем если слишком длинно
        if len(summary) > target_length:
            summary = summary[:target_length] + "..."
        
        return summary
    
    async def summarize_text(self, text: str, target_ratio: float = 0.3, language: str = 'auto') -> Optional[str]:
        """Основной метод суммаризации текста"""
        if len(text) < 50:
            logger.warning("Текст слишком короткий для суммаризации")
            return None
        
        logger.info(f"Начало суммаризации текста длиной {len(text)} символов, целевое соотношение: {target_ratio:.2%}")
        
        # Для очень длинных текстов разбиваем на чанки
        if len(text) > 5000:
            chunks = self._split_text_into_chunks(text, 4000)
            chunk_summaries = []
            
            for i, chunk in enumerate(chunks):
                logger.info(f"Обработка чанка {i+1}/{len(chunks)}")
                
                # Суммаризируем каждый чанк
                chunk_summary = await self._summarize_single_chunk(chunk, target_ratio)
                if chunk_summary:
                    chunk_summaries.append(chunk_summary)
            
            if chunk_summaries:
                # Объединяем саммари чанков
                combined_summary = "\n\n".join(chunk_summaries)
                
                # Если объединенное саммари слишком длинное, суммаризируем его еще раз
                if len(combined_summary) > len(text) * target_ratio * 1.5:
                    final_summary = await self._summarize_single_chunk(combined_summary, 0.7)
                    return final_summary or combined_summary
                
                return combined_summary
            
        else:
            # Обрабатываем весь текст сразу
            return await self._summarize_single_chunk(text, target_ratio)
        
        # Последний резерв - простое саммари
        logger.warning("Все методы суммаризации не сработали, создаем простое саммари")
        return self._create_simple_summary(text, target_ratio)
    
    async def _summarize_single_chunk(self, text: str, target_ratio: float) -> Optional[str]:
        """Суммаризация одного чанка текста"""
        # Пробуем Groq API
        if self.groq_client:
            summary = await self._summarize_with_groq(text, target_ratio)
            if summary:
                return summary
            
            logger.warning("Groq API не смог создать саммари, пробуем локальную модель")
        
        # Пробуем локальную модель
        if self.use_local_fallback:
            summary = await self._summarize_with_local_model(text, target_ratio)
            if summary:
                return summary
            
            logger.warning("Локальная модель не смогла создать саммари")
        
        return None
    
    def get_status(self) -> dict:
        """Получить статус доступности различных методов суммаризации"""
        return {
            'groq_available': bool(self.groq_client),
            'local_available': self.use_local_fallback and _transformers_available,
            'transformers_installed': _transformers_available
        }
