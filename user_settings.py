#!/usr/bin/env python3
"""
Модуль для управления пользовательскими настройками
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class UserSettingsManager:
    """Управление пользовательскими настройками"""
    
    def __init__(self, database_manager=None):
        self.db = database_manager
        self.in_memory_cache: Dict[int, Dict[str, Any]] = {}
        
        # Настройки по умолчанию
        self.default_settings = {
            'compression_level': 30,
            'language': 'ru',
            'smart_mode': False,
            'first_interaction': True
        }
    
    def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        """Получить настройки пользователя"""
        
        # Сначала проверяем кэш
        if user_id in self.in_memory_cache:
            return self.in_memory_cache[user_id].copy()
        
        # Пытаемся получить из БД
        settings = self.default_settings.copy()
        
        try:
            if self.db:
                db_settings = self.db.get_user_settings(user_id)
                settings.update(db_settings)
                logger.debug(f"Загружены настройки из БД для пользователя {user_id}: {db_settings}")
        except Exception as e:
            logger.warning(f"Не удалось загрузить настройки из БД для пользователя {user_id}: {e}")
        
        # Кэшируем
        self.in_memory_cache[user_id] = settings.copy()
        
        return settings
    
    def update_user_setting(self, user_id: int, key: str, value: Any, username: str = "") -> bool:
        """Обновить конкретную настройку пользователя"""
        try:
            # Получаем текущие настройки
            settings = self.get_user_settings(user_id)
            settings[key] = value
            
            # Обновляем кэш
            self.in_memory_cache[user_id] = settings
            
            # Сохраняем в БД
            if self.db:
                if key == 'compression_level':
                    self.db.update_compression_level(user_id, value, username)
                else:
                    # Общий метод обновления настроек
                    self.db.save_user_setting(user_id, key, value, username)
                
                logger.info(f"Обновлена настройка {key}={value} для пользователя {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления настройки {key} для пользователя {user_id}: {e}")
            return False
    
    def toggle_language(self, user_id: int, username: str = "") -> str:
        """Переключить язык пользователя RU <-> EN"""
        settings = self.get_user_settings(user_id)
        current_lang = settings.get('language', 'ru').lower()
        
        new_lang = 'en' if current_lang == 'ru' else 'ru'
        
        self.update_user_setting(user_id, 'language', new_lang, username)
        
        return new_lang
    
    def toggle_smart_mode(self, user_id: int, username: str = "") -> bool:
        """Переключить режим умной суммаризации"""
        settings = self.get_user_settings(user_id)
        current_mode = settings.get('smart_mode', False)
        
        new_mode = not current_mode
        
        self.update_user_setting(user_id, 'smart_mode', new_mode, username)
        
        return new_mode
    
    def set_compression_level(self, user_id: int, level: int, username: str = "") -> bool:
        """Установить уровень сжатия"""
        if level not in [10, 30, 50]:
            logger.warning(f"Недопустимый уровень сжатия: {level}")
            return False
        
        return self.update_user_setting(user_id, 'compression_level', level, username)
    
    def mark_first_interaction_complete(self, user_id: int) -> None:
        """Отметить что пользователь завершил первое взаимодействие"""
        self.update_user_setting(user_id, 'first_interaction', False)
    
    def is_first_interaction(self, user_id: int) -> bool:
        """Проверить, первое ли это взаимодействие пользователя"""
        settings = self.get_user_settings(user_id)
        return settings.get('first_interaction', True)
    
    def get_user_language(self, user_id: int) -> str:
        """Получить язык пользователя"""
        settings = self.get_user_settings(user_id)
        return settings.get('language', 'ru').lower()
    
    def get_user_compression_level(self, user_id: int) -> int:
        """Получить уровень сжатия пользователя"""
        settings = self.get_user_settings(user_id)
        return settings.get('compression_level', 30)
    
    def is_smart_mode_enabled(self, user_id: int) -> bool:
        """Проверить включен ли режим умной суммаризации"""
        settings = self.get_user_settings(user_id)
        return settings.get('smart_mode', False)
    
    def clear_user_cache(self, user_id: int) -> None:
        """Очистить кэш настроек пользователя"""
        if user_id in self.in_memory_cache:
            del self.in_memory_cache[user_id]
            logger.debug(f"Очищен кэш настроек для пользователя {user_id}")
    
    def clear_all_cache(self) -> None:
        """Очистить весь кэш настроек"""
        self.in_memory_cache.clear()
        logger.info("Очищен весь кэш настроек пользователей")