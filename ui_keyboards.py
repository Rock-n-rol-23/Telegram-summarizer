#!/usr/bin/env python3
"""
Модуль для генерации inline-клавиатур и reply-клавиатур
"""

import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class TelegramKeyboards:
    """Генератор клавиатур для Telegram бота"""
    
    def __init__(self):
        # Тексты для разных языков
        self.texts = {
            'ru': {
                'smart_summary': '🧠 Умная суммаризация',
                'compression_10': '🔥 10%',
                'compression_30': '📝 30%', 
                'compression_50': '📄 50%',
                'language': '🌐 Язык: {}',
                'stats': '📊 Статистика',
                'help': '❓ Помощь',
                'back_to_menu': '◀️ Назад в меню',
                'menu_button': '📋 Меню',
                'menu_title': '📋 Главное меню',
                'processing': '⏳ Обрабатываю...',
                'ru': 'RU',
                'en': 'EN'
            },
            'en': {
                'smart_summary': '🧠 Smart Summary',
                'compression_10': '🔥 10%',
                'compression_30': '📝 30%',
                'compression_50': '📄 50%', 
                'language': '🌐 Language: {}',
                'stats': '📊 Statistics',
                'help': '❓ Help',
                'back_to_menu': '◀️ Back to menu',
                'menu_button': '📋 Menu',
                'menu_title': '📋 Main menu',
                'processing': '⏳ Processing...',
                'ru': 'RU', 
                'en': 'EN'
            }
        }
    
    def get_text(self, key: str, lang: str = 'ru', **kwargs) -> str:
        """Получить текст на нужном языке"""
        lang = lang.lower()
        if lang not in self.texts:
            lang = 'ru'
        
        text = self.texts[lang].get(key, self.texts['ru'].get(key, key))
        
        # Форматирование если нужно
        if '{}' in text and kwargs:
            return text.format(**kwargs)
        elif '{}' in text:
            return text
        return text
    
    def build_main_menu(self, user_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Создает главное inline-меню с учетом настроек пользователя"""
        
        # Получаем настройки пользователя
        compression = user_settings.get('compression_level', 30)
        lang = user_settings.get('language', 'ru').lower()
        smart_mode = user_settings.get('smart_mode', False)
        
        def mark_active(level: int) -> str:
            """Помечает активный уровень сжатия"""
            return '• ' if level == compression else ''
        
        # Язык для отображения
        lang_display = self.get_text('ru' if lang == 'ru' else 'en', lang)
        
        # Формируем клавиатуру
        keyboard = [
            # Умная суммаризация
            [{
                "text": self.get_text('smart_summary', lang) + (' ✓' if smart_mode else ''),
                "callback_data": "smart"
            }],
            
            # Уровни сжатия
            [
                {
                    "text": mark_active(10) + self.get_text('compression_10', lang),
                    "callback_data": "cmp:10"
                },
                {
                    "text": mark_active(30) + self.get_text('compression_30', lang), 
                    "callback_data": "cmp:30"
                },
                {
                    "text": mark_active(50) + self.get_text('compression_50', lang),
                    "callback_data": "cmp:50"
                }
            ],
            
            # Язык
            [{
                "text": self.get_text('language', lang).format(lang_display),
                "callback_data": "lang:toggle"
            }],
            
            # Статистика и помощь
            [
                {
                    "text": self.get_text('stats', lang),
                    "callback_data": "stats"
                },
                {
                    "text": self.get_text('help', lang),
                    "callback_data": "help"
                }
            ]
        ]
        
        return {
            "inline_keyboard": keyboard
        }
    
    def build_back_menu(self, lang: str = 'ru') -> Dict[str, Any]:
        """Создает клавиатуру только с кнопкой 'Назад в меню'"""
        return {
            "inline_keyboard": [
                [{
                    "text": self.get_text('back_to_menu', lang),
                    "callback_data": "menu"
                }]
            ]
        }
    
    def build_reply_keyboard(self, lang: str = 'ru') -> Dict[str, Any]:
        """Создает reply-клавиатуру с кнопкой меню"""
        menu_text = self.get_text('menu_button', lang)
        
        return {
            "keyboard": [[menu_text]],
            "resize_keyboard": True,
            "one_time_keyboard": False
        }
    
    def build_processing_menu(self, user_settings: Dict[str, Any], processing_text: str = None) -> tuple[str, Dict[str, Any]]:
        """Создает сообщение с индикатором обработки и текущим меню"""
        lang = user_settings.get('language', 'ru').lower()
        
        if not processing_text:
            processing_text = self.get_text('processing', lang)
        
        menu = self.build_main_menu(user_settings)
        
        return processing_text, menu


class CallbackDataParser:
    """Парсер callback_data для inline-кнопок"""
    
    @staticmethod
    def parse(callback_data: str) -> Dict[str, Any]:
        """
        Парсит callback_data в структуру
        Формат: action[:sub[:value]]
        Примеры:
        - 'smart' -> {'action': 'smart'}
        - 'cmp:30' -> {'action': 'cmp', 'sub': '30'}
        - 'lang:toggle' -> {'action': 'lang', 'sub': 'toggle'}
        """
        if not callback_data:
            return {'action': 'unknown'}
        
        parts = callback_data.split(':')
        
        result = {
            'action': parts[0] if parts else 'unknown'
        }
        
        if len(parts) > 1:
            result['sub'] = parts[1]
        
        if len(parts) > 2:
            result['value'] = parts[2]
        
        return result
    
    @staticmethod
    def build(action: str, sub: str = None, value: str = None) -> str:
        """
        Строит callback_data из компонентов
        Обеспечивает лимит в 64 байта
        """
        parts = [action]
        
        if sub:
            parts.append(sub)
        
        if value:
            parts.append(value)
        
        callback_data = ':'.join(parts)
        
        # Проверяем лимит 64 байта
        if len(callback_data.encode('utf-8')) > 64:
            logger.warning(f"Callback data слишком длинный: {callback_data}")
            # Обрезаем если нужно
            callback_data = callback_data[:60] + '...'
        
        return callback_data


# Глобальная единственная инстанция
keyboards = TelegramKeyboards()
callback_parser = CallbackDataParser()