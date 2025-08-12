"""
Модуль "умной" суммаризации с извлечением ключевых инсайтов
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from groq import Groq

logger = logging.getLogger(__name__)

class SmartSummarizer:
    """Класс для интеллектуальной суммаризации с извлечением ключевых моментов"""
    
    def __init__(self, groq_client: Groq):
        self.groq_client = groq_client
        
    def analyze_content_type(self, text: str, source_type: str = "text") -> str:
        """Анализирует тип контента для выбора подходящей стратегии суммаризации"""
        text_lower = text.lower()
        
        # Ключевые слова для определения типа контента
        content_patterns = {
            "meeting": ["встреча", "собрание", "обсуждали", "решили", "action item", "следующие шаги", "повестка"],
            "lecture": ["лекция", "урок", "объясню", "изучаем", "тема урока", "выводы", "материал"],
            "news": ["новости", "произошло", "сообщается", "по данным", "источники", "заявил"],
            "interview": ["интервью", "беседа", "вопрос", "ответ", "рассказал", "поделился"],
            "presentation": ["презентация", "доклад", "слайд", "покажу", "демонстрация"],
            "discussion": ["дискуссия", "обсуждение", "мнение", "точка зрения", "считаю", "согласен"],
            "instruction": ["инструкция", "как", "шаги", "сначала", "затем", "руководство"],
            "review": ["обзор", "рецензия", "оценка", "плюсы", "минусы", "рекомендую"]
        }
        
        scores = {}
        for content_type, keywords in content_patterns.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            if score > 0:
                scores[content_type] = score
        
        if scores:
            return max(scores.keys(), key=lambda x: scores[x])
        
        # Дефолтный тип в зависимости от источника
        if source_type == "audio":
            return "discussion"
        elif source_type == "document":
            return "instruction"
        else:
            return "general"
    
    def extract_key_entities(self, text: str) -> Dict[str, List[str]]:
        """Извлекает ключевые сущности из текста"""
        entities = {
            "dates": [],
            "numbers": [],
            "names": [],
            "actions": [],
            "decisions": []
        }
        
        # Извлечение дат
        date_patterns = [
            r'\d{1,2}\.\d{1,2}\.\d{4}',  # 01.01.2024
            r'\d{1,2}/\d{1,2}/\d{4}',   # 01/01/2024
            r'\d{1,2} [а-я]+ \d{4}',    # 1 января 2024
            r'[а-я]+ \d{4}',            # январь 2024
        ]
        
        for pattern in date_patterns:
            entities["dates"].extend(re.findall(pattern, text, re.IGNORECASE))
        
        # Извлечение чисел и процентов
        number_patterns = [
            r'\d+%',           # проценты
            r'\d+[\.,]\d+',    # десятичные числа
            r'\d{1,3}[,\s]?\d{3}',  # большие числа
            r'\$\d+',          # деньги
            r'\d+₽',           # рубли
        ]
        
        for pattern in number_patterns:
            entities["numbers"].extend(re.findall(pattern, text))
        
        # Извлечение имен (простая эвристика)
        name_pattern = r'\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\b'
        entities["names"] = re.findall(name_pattern, text)
        
        # Ключевые слова для действий
        action_keywords = ["решили", "планируем", "сделаем", "начнем", "запустим", "реализуем", "обсудим"]
        decision_keywords = ["решение", "вывод", "заключение", "итог", "результат", "договорились"]
        
        sentences = text.split('.')
        for sentence in sentences:
            sentence_lower = sentence.lower().strip()
            if any(keyword in sentence_lower for keyword in action_keywords):
                entities["actions"].append(sentence.strip())
            if any(keyword in sentence_lower for keyword in decision_keywords):
                entities["decisions"].append(sentence.strip())
        
        return entities
    
    async def smart_summarize(self, text: str, source_type: str = "text", 
                            source_name: str = "", compression_ratio: float = 0.3) -> Dict:
        """Создает умную суммаризацию с извлечением ключевых моментов"""
        try:
            # Анализируем тип контента
            content_type = self.analyze_content_type(text, source_type)
            logger.info(f"Определен тип контента: {content_type}")
            
            # Извлекаем ключевые сущности
            entities = self.extract_key_entities(text)
            
            # Создаем анализ ключевых инсайтов с учетом уровня сжатия
            insights_prompt = self._create_insights_prompt(text, entities, compression_ratio)
            
            insights_response = self.groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "Ты эксперт по извлечению ключевых инсайтов. Выдели самые важные факты, решения и выводы."
                    },
                    {
                        "role": "user",
                        "content": insights_prompt
                    }
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=500,
                temperature=0.1
            )
            
            key_insights = insights_response.choices[0].message.content.strip() if insights_response.choices[0].message.content else "Нет инсайтов"
            
            return {
                "content_type": content_type,
                "key_insights": key_insights,
                "entities": entities
            }
            
        except Exception as e:
            logger.error(f"Ошибка умной суммаризации: {e}")
            return {
                "content_type": "unknown",
                "key_insights": f"❌ Ошибка создания умного анализа: {str(e)}",
                "entities": {}
            }
    
    def _create_specialized_prompt(self, text: str, content_type: str, entities: Dict, compression_ratio: float) -> str:
        """Создает специализированный промпт в зависимости от типа контента"""
        
        base_requirements = f"""
Создай структурированное резюме следующего текста (сжатие: {compression_ratio:.0%}).
Сохрани все ключевые моменты и важную информацию.
Отвечай на том же языке, что и исходный текст.
"""
        
        type_specific_formats = {
            "meeting": """
📋 **ОСНОВНЫЕ ВЫВОДЫ:**
• Главные решения и договоренности (3-4 пункта)
• Конкретные следующие шаги и задачи (2-3 пункта)
""",
            
            "lecture": """
💡 **ОСНОВНЫЕ ВЫВОДЫ:**
• Ключевые концепции и определения (3-4 пункта)
• Главные принципы и заключения (2-3 пункта)
""",
            
            "news": """
📰 **ОСНОВНЫЕ ВЫВОДЫ:**
• Суть события и ключевые факты (2-3 пункта)
• Участники и важные данные (2-3 пункта)
""",
            
            "discussion": """
💬 **ОСНОВНЫЕ ВЫВОДЫ:**
• Главные темы и мнения (3-4 пункта) 
• Области согласия и спорные вопросы (2-3 пункта)
""",
            
            "interview": """
🎤 **ОСНОВНЫЕ ВЫВОДЫ:**
• Ключевые ответы и позиция собеседника (3-4 пункта)
• Важные откровения и факты (2-3 пункта)
""",
            
            "presentation": """
📊 **ОСНОВНЫЕ ВЫВОДЫ:**
• Главные тезисы презентации (3-4 пункта)
• Ключевые данные и рекомендации (2-3 пункта)
""",
            
            "instruction": """
📖 **ОСНОВНЫЕ ВЫВОДЫ:**
• Ключевые шаги и действия (3-4 пункта)
• Важные требования и ограничения (2-3 пункта)
""",
            
            "review": """
⭐ **ОСНОВНЫЕ ВЫВОДЫ:**
• Главные оценки и мнения (3-4 пункта)
• Плюсы, минусы и рекомендации (2-3 пункта)
""",
            
            "general": """
📋 **ОСНОВНЫЕ ВЫВОДЫ:**
• Главные темы и идеи (3-4 пункта)
• Важные факты и заключения (2-3 пункта)
"""
        }
        
        format_instruction = type_specific_formats.get(content_type, type_specific_formats["general"])
        
        prompt = f"""{base_requirements}

{format_instruction}

Начни ответ сразу с резюме, без вступлений.

ИСХОДНЫЙ ТЕКСТ:
{text}"""
        
        return prompt
    
    def _create_insights_prompt(self, text: str, entities: Dict, compression_ratio: float = 0.3) -> str:
        """Создает промпт для извлечения ключевых инсайтов с учетом уровня сжатия"""
        
        entities_context = ""
        if entities["dates"]:
            entities_context += f"Найденные даты: {', '.join(entities['dates'][:3])}\n"
        if entities["numbers"]:
            entities_context += f"Важные цифры: {', '.join(entities['numbers'][:5])}\n"
        if entities["names"]:
            entities_context += f"Упомянутые имена: {', '.join(entities['names'][:3])}\n"
        
        # Определяем количество инсайтов в зависимости от уровня сжатия
        if compression_ratio <= 0.1:  # 10% - максимальное сжатие
            max_insights = 2
            detail_level = "самые критически важные"
        elif compression_ratio <= 0.3:  # 30% - сбалансированное
            max_insights = 3
            detail_level = "ключевые"
        else:  # 50% - подробное
            max_insights = 4
            detail_level = "важные"
        
        prompt = f"""Проанализируй следующий текст и выдели ТОЛЬКО {detail_level} инсайты.

{entities_context}

Формат ответа:
🎯 **КЛЮЧЕВЫЕ ИНСАЙТЫ:**
• Самый важный факт или вывод
• Критически важная информация или решение
• Главное открытие или заключение
{"• Дополнительный значимый инсайт" if max_insights >= 4 else ""}

Максимум {max_insights} пунктов. Каждый пункт должен быть конкретным и значимым.
Отвечай на том же языке, что и исходный текст.

ТЕКСТ ДЛЯ АНАЛИЗА:
{text}"""
        
        return prompt
    
    def format_smart_response(self, result: Dict, source_info: str, original_length: int, 
                            processing_time: float = 0) -> str:
        """Форматирует финальный ответ с умной суммаризацией"""
        
        content_type_names = {
            "meeting": "встречи/собрания",
            "lecture": "лекции/урока", 
            "news": "новостей",
            "interview": "интервью",
            "presentation": "презентации",
            "discussion": "обсуждения/дискуссии",
            "instruction": "инструкции/руководства",
            "review": "обзора/рецензии",
            "general": "общего текста"
        }
        
        content_type_display = content_type_names.get(result["content_type"], "текста")
        
        # Максимально упрощенный формат: только ключевые инсайты
        response = f"""🧠 **Умное резюме {content_type_display}**

{result["key_insights"]}"""
        
        # Только статистика анализа
        summary_length = len(result["key_insights"])
        compression_ratio = summary_length / original_length if original_length > 0 else 0
        
        response += f"""

📈 **Статистика анализа:**
• Исходный текст: {original_length:,} символов
• Умное резюме: {summary_length:,} символов
• Интеллектуальное сжатие: {compression_ratio:.1%}"""
        
        if processing_time > 0:
            response += f"\n• Время обработки: {processing_time:.1f}с"
            
        return response