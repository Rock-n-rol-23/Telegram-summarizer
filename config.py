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
        
        # Groq API Key (основной для суммаризации)
        self.GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
        
        # База данных - приоритет Railway PostgreSQL
        self.DATABASE_URL = os.getenv('RAILWAY_DATABASE_URL') or os.getenv('DATABASE_URL', 'sqlite:///bot_database.db')
        
        # Настройки логирования
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        
        # Настройки суммаризации
        self.SUMMARIZATION_PARAMS = {
            'model': 'llama-3.1-70b-versatile',
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
        
        # Промпт для суммаризации
        self.SUMMARIZATION_PROMPT = """Ты - эксперт по суммаризации текстов. Создай краткое саммари следующего текста на том же языке, что и исходный текст.

Требования:
- Саммари должно быть минимум 20% от длины исходного текста
- Сохрани все ключевые моменты и важную информацию
- Используй структурированный формат с bullet points (•)
- Пиши естественным языком, сохраняя стиль исходного текста
- Если текст на русском - отвечай на русском языке
- Начни ответ сразу с саммари, без вступлений

Текст для суммаризации:
{text}"""
        
        # Настройки по умолчанию для пользователей
        self.DEFAULT_SUMMARY_RATIO = 0.3
        self.DEFAULT_LANGUAGE = 'auto'
        
        # Валидация критически важных параметров
        self._validate_config()
    
    def _validate_config(self):
        """Валидация конфигурации"""
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("Telegram Bot Token обязателен")
        
        if not self.GROQ_API_KEY:
            print("⚠️  Предупреждение: GROQ_API_KEY не установлен. Будет использована только локальная модель.")
        
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
