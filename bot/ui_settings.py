"""
Настройки пользовательского интерфейса и пользовательские предпочтения
"""

import logging
from typing import Dict, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

class SummaryFormat(Enum):
    STRUCTURED = "structured"
    BULLETS = "bullets" 
    PARAGRAPH = "paragraph"

class SummaryVerbosity(Enum):
    SHORT = "short"
    NORMAL = "normal"
    DETAILED = "detailed"

# Описания для пользователя
FORMAT_DESCRIPTIONS = {
    SummaryFormat.STRUCTURED: "📋 Структурно (разделы с заголовками)",
    SummaryFormat.BULLETS: "🔹 Пункты (маркированный список)",
    SummaryFormat.PARAGRAPH: "📄 Абзац (связный текст)"
}

VERBOSITY_DESCRIPTIONS = {
    SummaryVerbosity.SHORT: "⚡ Кратко (основное)",
    SummaryVerbosity.NORMAL: "📖 Обычно (сбалансированно)", 
    SummaryVerbosity.DETAILED: "🔍 Подробно (все детали)"
}

class UserSettings:
    """Настройки пользователя"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.summary_format = SummaryFormat.STRUCTURED
        self.summary_verbosity = SummaryVerbosity.NORMAL
        
    def get_format_str(self) -> str:
        return self.summary_format.value
        
    def get_verbosity_str(self) -> str:
        return self.summary_verbosity.value
        
    def set_format(self, format_str: str) -> bool:
        try:
            self.summary_format = SummaryFormat(format_str)
            return True
        except ValueError:
            return False
            
    def set_verbosity(self, verbosity_str: str) -> bool:
        try:
            self.summary_verbosity = SummaryVerbosity(verbosity_str)
            return True
        except ValueError:
            return False
    
    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "format": self.summary_format.value,
            "verbosity": self.summary_verbosity.value
        }
        
    @classmethod
    def from_dict(cls, data: Dict) -> 'UserSettings':
        settings = cls(data["user_id"])
        settings.set_format(data.get("format", "structured"))
        settings.set_verbosity(data.get("verbosity", "normal"))
        return settings


class UserSettingsManager:
    """Менеджер пользовательских настроек"""
    
    def __init__(self, db_connection=None):
        self.db = db_connection
        self._cache = {}  # В памяти для быстрого доступа
        
    def get_user_settings(self, user_id: int) -> UserSettings:
        """Получает настройки пользователя"""
        
        # Проверяем кэш
        if user_id in self._cache:
            return self._cache[user_id]
        
        # Пытаемся загрузить из БД
        settings = self._load_from_db(user_id)
        if settings is None:
            # Создаем настройки по умолчанию
            settings = UserSettings(user_id)
            self._save_to_db(settings)
        
        # Кэшируем
        self._cache[user_id] = settings
        return settings
    
    def update_user_format(self, user_id: int, format_str: str) -> bool:
        """Обновляет формат саммари пользователя"""
        settings = self.get_user_settings(user_id)
        if settings.set_format(format_str):
            self._save_to_db(settings)
            return True
        return False
    
    def update_user_verbosity(self, user_id: int, verbosity_str: str) -> bool:
        """Обновляет подробность саммари пользователя"""
        settings = self.get_user_settings(user_id)
        if settings.set_verbosity(verbosity_str):
            self._save_to_db(settings)
            return True
        return False
    
    def _load_from_db(self, user_id: int) -> Optional[UserSettings]:
        """Загружает настройки из БД"""
        if not self.db:
            return None
            
        try:
            # Пытаемся загрузить из таблицы user_settings
            result = self.db.execute_query(
                "SELECT format, verbosity FROM user_settings WHERE user_id = %s",
                (user_id,)
            )
            
            if result:
                row = result[0]
                return UserSettings.from_dict({
                    "user_id": user_id,
                    "format": row[0],
                    "verbosity": row[1]
                })
                
        except Exception as e:
            logger.warning(f"Ошибка загрузки настроек пользователя {user_id}: {e}")
            
        return None
    
    def _save_to_db(self, settings: UserSettings):
        """Сохраняет настройки в БД"""
        if not self.db:
            return
            
        try:
            # Создаем таблицу если не существует
            self.db.execute_query("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id BIGINT PRIMARY KEY,
                    format VARCHAR(20) DEFAULT 'structured',
                    verbosity VARCHAR(20) DEFAULT 'normal',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Upsert настроек
            self.db.execute_query("""
                INSERT INTO user_settings (user_id, format, verbosity, updated_at) 
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE SET 
                    format = EXCLUDED.format,
                    verbosity = EXCLUDED.verbosity,
                    updated_at = CURRENT_TIMESTAMP
            """, (settings.user_id, settings.get_format_str(), settings.get_verbosity_str()))
            
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек пользователя {settings.user_id}: {e}")


def generate_format_keyboard() -> Dict:
    """Генерирует клавиатуру для выбора формата"""
    keyboard = []
    
    for format_type in SummaryFormat:
        keyboard.append([{
            "text": FORMAT_DESCRIPTIONS[format_type],
            "callback_data": f"set_format_{format_type.value}"
        }])
    
    keyboard.append([{
        "text": "◀️ Назад",
        "callback_data": "settings_menu"
    }])
    
    return {
        "inline_keyboard": keyboard
    }


def generate_verbosity_keyboard() -> Dict:
    """Генерирует клавиатуру для выбора подробности"""
    keyboard = []
    
    for verbosity_type in SummaryVerbosity:
        keyboard.append([{
            "text": VERBOSITY_DESCRIPTIONS[verbosity_type],
            "callback_data": f"set_verbosity_{verbosity_type.value}"
        }])
    
    keyboard.append([{
        "text": "◀️ Назад", 
        "callback_data": "settings_menu"
    }])
    
    return {
        "inline_keyboard": keyboard
    }


def generate_settings_keyboard() -> Dict:
    """Генерирует основную клавиатуру настроек"""
    keyboard = [
        [{
            "text": "📋 Формат саммари",
            "callback_data": "choose_format"
        }],
        [{
            "text": "🔍 Подробность", 
            "callback_data": "choose_verbosity"
        }],
        [{
            "text": "❌ Закрыть",
            "callback_data": "close_settings"
        }]
    ]
    
    return {
        "inline_keyboard": keyboard
    }


def format_settings_message(settings: UserSettings) -> str:
    """Форматирует сообщение с текущими настройками"""
    current_format = FORMAT_DESCRIPTIONS[settings.summary_format]
    current_verbosity = VERBOSITY_DESCRIPTIONS[settings.summary_verbosity]
    
    return f"""⚙️ **Настройки аудио саммари**

🎯 **Текущие настройки:**
• Формат: {current_format}
• Подробность: {current_verbosity}

📝 **Описание режимов:**

**Формат вывода:**
• Структурно - разделы с заголовками (договоренности, сроки, действия)
• Пункты - маркированный список основных моментов
• Абзац - связный текст в виде абзацев

**Уровень подробности:**
• Кратко - только главное (4-6 предложений)
• Обычно - сбалансированно (8-10 предложений)
• Подробно - все детали (12-15 предложений)

Выберите параметр для изменения:"""


def get_format_confirmation_message(format_type: SummaryFormat) -> str:
    """Возвращает сообщение подтверждения смены формата"""
    description = FORMAT_DESCRIPTIONS[format_type]
    return f"✅ Формат саммари изменен на: {description}"


def get_verbosity_confirmation_message(verbosity_type: SummaryVerbosity) -> str:
    """Возвращает сообщение подтверждения смены подробности"""
    description = VERBOSITY_DESCRIPTIONS[verbosity_type]
    return f"✅ Подробность саммари изменена на: {description}"


# Глобальный менеджер настроек (будет инициализирован в боте)
_settings_manager = None

def init_settings_manager(db_connection=None):
    """Инициализирует глобальный менеджер настроек"""
    global _settings_manager
    _settings_manager = UserSettingsManager(db_connection)

def get_settings_manager() -> Optional[UserSettingsManager]:
    """Получает глобальный менеджер настроек"""
    return _settings_manager

def get_user_audio_settings(user_id: int) -> Tuple[str, str]:
    """Получает настройки аудио для пользователя"""
    if _settings_manager:
        settings = _settings_manager.get_user_settings(user_id)
        return settings.get_format_str(), settings.get_verbosity_str()
    else:
        # Настройки по умолчанию
        return "structured", "normal"