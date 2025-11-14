"""
Конфигурация и настройки для Telegram бота суммаризации
"""

import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

class Config:
    """Класс конфигурации с настройками бота"""
    
    def __init__(self):
        # Telegram Bot Token (обязательный)
        self.TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        
        # LLM Configuration (simplified, free models only)
        # Primary: Google Gemini 2.5 Flash (free, fast, 2M context, excellent Russian)
        self.GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
        self.GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
        self.GEMINI_VISION_MODEL = os.getenv('GEMINI_VISION_MODEL', 'gemini-2.5-flash')

        # Fallback: Groq with Llama 3.3 70B (fast, free, good quality)
        self.GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
        self.GROQ_LLM_MODEL = os.getenv('GROQ_LLM_MODEL', 'llama-3.3-70b-versatile')
        
        # База данных - приоритет Railway PostgreSQL
        self.DATABASE_URL = os.getenv('RAILWAY_DATABASE_URL') or os.getenv('DATABASE_URL', 'sqlite:///bot_database.db')
        
        # Настройки логирования
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        
        # Настройки суммаризации
        self.SUMMARIZATION_PARAMS = {
            'model': 'llama-3.3-70b-versatile',
            'temperature': 0.3,
            'max_tokens': 2000,
            'top_p': 0.9,
            'stream': False
        }
        
        # Настройки для локальной модели (fallback)
        self.LOCAL_MODEL_NAME = 'ai-forever/rugpt3large_based_on_gpt2'
        
        # Лимиты и ограничения
        self.MAX_TEXT_LENGTH = 10000  # Максимальная длина текста
        self.MIN_TEXT_LENGTH = 50     # Минимальная длина текста
        self.MAX_REQUESTS_PER_MINUTE = 10  # Лимит запросов на пользователя в минуту
        self.MAX_CHUNK_SIZE = 4000    # Размер чанка для длинных текстов
        
        # Промпт для суммаризации (улучшенный с few-shot примерами)
        self.SUMMARIZATION_PROMPT = """Ты - эксперт по суммаризации текстов. Создай краткое саммари следующего текста на том же языке, что и исходный текст.

📋 **Требования:**
- Саммари должно быть минимум 20% от длины исходного текста
- Сохрани ВСЕ ключевые моменты: цифры, даты, имена, факты, решения
- Используй структурированный формат с bullet points (•)
- Пиши естественным языком, сохраняя стиль исходного текста
- Если текст на русском - отвечай на русском языке
- Начни ответ сразу с саммари, без вступлений

🎯 **Пример (хорошее саммари):**
Исходный текст: "На встрече 15 января обсудили новый проект. Бюджет составляет 500 тысяч рублей. Ответственный - Иван Петров. Срок сдачи - 28 февраля."

Хорошее саммари:
• Встреча 15 января: обсужден новый проект
• Бюджет: 500 000 руб.
• Ответственный: Иван Петров
• Дедлайн: 28 февраля

❌ **Плохое саммари (без фактов):**
"Обсудили проект с бюджетом и назначили ответственного"

✅ **ВАЖНО - СОХРАНЯЙ ФАКТЫ:**
- Числа и цифры (точные значения!)
- Даты и время
- Имена людей и организаций
- Конкретные решения и договоренности

Текст для суммаризации:
{text}"""

        # Промпт для анализа изображений
        self.IMAGE_ANALYSIS_PROMPT = """Проанализируй это изображение и извлеки всю текстовую и визуальную информацию.

📋 **Задачи:**
1. Распознай весь текст на изображении
2. Опиши визуальный контекст (диаграммы, графики, таблицы)
3. Извлеки ключевые данные: цифры, даты, имена, факты
4. Сделай краткое резюме содержания

🎯 **Формат ответа:**
**Текст на изображении:**
[Весь распознанный текст]

**Визуальные элементы:**
[Описание графиков, таблиц, диаграмм, если есть]

**Ключевые данные:**
• [Важные цифры, даты, имена]

**Резюме:**
[Краткое саммари содержания в 2-3 предложениях]

Отвечай на том же языке, что и текст на изображении."""
        
        # Настройки по умолчанию для пользователей
        self.DEFAULT_SUMMARY_RATIO = 0.3
        self.DEFAULT_LANGUAGE = 'auto'
        
        # Настройки для локальной LLM (опционально)
        self.USE_LOCAL_LLM = os.getenv('USE_LOCAL_LLM', 'false').lower() == 'true'
        self.LOCAL_LLM_MODEL_PATH = os.getenv('LOCAL_LLM_MODEL_PATH', '')
        self.LOCAL_LLM_CTX = int(os.getenv('LOCAL_LLM_CTX', '4096'))
        self.LOCAL_LLM_THREADS = int(os.getenv('LOCAL_LLM_THREADS', '0'))
        
        # ASR Configuration (free-first)
        self.ASR_ENGINE = os.getenv('ASR_ENGINE', 'faster_whisper')
        self.FASTER_WHISPER_MODEL = os.getenv('FASTER_WHISPER_MODEL', 'large-v3')
        self.FASTER_WHISPER_COMPUTE = os.getenv('FASTER_WHISPER_COMPUTE', 'float16')
        
        # OCR Configuration
        self.OCR_USE_TESSERACT = os.getenv('OCR_USE_TESSERACT', 'true').lower() == 'true'
        self.OCR_USE_PADDLE = os.getenv('OCR_USE_PADDLE', 'true').lower() == 'true'
        self.OCR_LANGS = os.getenv('OCR_LANGS', 'rus+eng')
        self.PDF_OCR_DPI = int(os.getenv('PDF_OCR_DPI', '200'))
        self.MAX_PAGES_OCR = int(os.getenv('MAX_PAGES_OCR', '50'))
        
        # Summarization Behavior
        self.SUM_MAX_SENTENCES = int(os.getenv('SUM_MAX_SENTENCES', '10'))
        self.SUM_CHUNK_TOKENS = int(os.getenv('SUM_CHUNK_TOKENS', '3000'))
        self.SUM_OVERLAP_TOKENS = int(os.getenv('SUM_OVERLAP_TOKENS', '300'))
        
        # Новые флаги для улучшенной суммаризации
        self.ENABLE_LOCAL_FALLBACK = os.getenv('ENABLE_LOCAL_FALLBACK', 'false').lower() == 'true'
        self.YT_MAX_DURATION_SECONDS = int(os.getenv('YT_MAX_DURATION_SECONDS', '7200'))  # 2 часа
        self.FORCE_JSON_MODE = os.getenv('FORCE_JSON_MODE', 'true').lower() == 'true'
        
        # Валидация критически важных параметров
        self._validate_config()
    
    def _validate_config(self):
        """Валидация конфигурации"""
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("Telegram Bot Token обязателен")

        # Проверяем наличие хотя бы одного LLM провайдера
        has_provider = False
        if self.GEMINI_API_KEY:
            print(f"✅ Gemini API Key найден (основной провайдер)")
            print(f"   → Model: {self.GEMINI_MODEL} (Gemini 2.5 Flash)")
            print(f"   → Vision: {self.GEMINI_VISION_MODEL}")
            has_provider = True
        if self.GROQ_API_KEY:
            print(f"✅ Groq API Key найден (fallback провайдер)")
            print(f"   → Model: {self.GROQ_LLM_MODEL} (Llama 3.3 70B)")
            has_provider = True

        if not has_provider:
            print("⚠️  ВНИМАНИЕ: Ни один LLM провайдер не настроен!")
            print("   Установите хотя бы один из: GEMINI_API_KEY, GROQ_API_KEY")

        if self.MAX_REQUESTS_PER_MINUTE <= 0:
            raise ValueError("MAX_REQUESTS_PER_MINUTE должен быть больше 0")

        if self.MIN_TEXT_LENGTH >= self.MAX_TEXT_LENGTH:
            raise ValueError("MIN_TEXT_LENGTH должен быть меньше MAX_TEXT_LENGTH")
    
    def get_database_path(self) -> str:
        """Получить путь к файлу базы данных"""
        if self.DATABASE_URL.startswith('sqlite:///'):
            return self.DATABASE_URL[10:]  # Убираем 'sqlite:///'
        return 'bot_database.db'  # Fallback
    
    def is_groq_available(self) -> bool:
        """Проверить доступность Groq API"""
        return bool(self.GROQ_API_KEY)
    
    def get_model_config(self) -> dict:
        """Получить конфигурацию модели для суммаризации"""
        return self.SUMMARIZATION_PARAMS.copy()
    
    def get_chunk_size(self, text_length: int) -> int:
        """Вычислить размер чанка в зависимости от длины текста"""
        if text_length <= self.MAX_CHUNK_SIZE:
            return text_length
        
        # Для очень длинных текстов используем меньшие чанки
        if text_length > 20000:
            return self.MAX_CHUNK_SIZE // 2
        
        return self.MAX_CHUNK_SIZE
    
    def __str__(self) -> str:
        """Строковое представление конфигурации (без чувствительных данных)"""
        return f"""Configuration:
- Database: {self.DATABASE_URL}
- Log Level: {self.LOG_LEVEL}
- Groq Available: {self.is_groq_available()}
- Max Text Length: {self.MAX_TEXT_LENGTH}
- Min Text Length: {self.MIN_TEXT_LENGTH}
- Requests Per Minute: {self.MAX_REQUESTS_PER_MINUTE}
- Default Summary Ratio: {self.DEFAULT_SUMMARY_RATIO}"""

# Глобальный экземпляр конфигурации
config = Config()
