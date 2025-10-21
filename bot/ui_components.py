"""
UI компоненты и inline клавиатуры для Telegram бота
Все кнопки собраны в одном месте для удобства
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class UIComponents:
    """Класс для создания красивых inline клавиатур"""

    # Эмодзи для режимов
    EMOJI = {
        "short": "🔥",
        "balanced": "⚖️",
        "detailed": "📖",
        "settings": "⚙️",
        "stats": "📊",
        "help": "❓",
        "achievements": "🏆",
        "home": "🏠",
        "start": "⚡",
        "copy": "📋",
        "regenerate": "🔄",
        "pdf": "💾",
        "voice": "🗣️",
        "more": "📊",
        "back": "«",
        "fast": "⚡",
        "medium": "⚖️",
        "full": "📚",
        "confirm": "✅",
        "cancel": "❌"
    }

    @staticmethod
    def main_menu() -> Dict:
        """Главное меню бота"""
        keyboard = {
            "inline_keyboard": [
                [{"text": f"{UIComponents.EMOJI['start']} Начать работу", "callback_data": "main_start"}],
                [
                    {"text": f"{UIComponents.EMOJI['settings']} Настройки", "callback_data": "main_settings"},
                    {"text": f"{UIComponents.EMOJI['stats']} Статистика", "callback_data": "main_stats"}
                ],
                [
                    {"text": f"{UIComponents.EMOJI['help']} Справка", "callback_data": "main_help"},
                    {"text": f"{UIComponents.EMOJI['achievements']} Достижения", "callback_data": "main_achievements"}
                ]
            ]
        }
        return keyboard

    @staticmethod
    def settings_menu(current_level: str = "balanced") -> Dict:
        """Меню настроек с выбором уровня детализации"""
        levels = {
            "short": ("🔥 Кратко", "10"),
            "balanced": ("⚖️ Средний", "30"),
            "detailed": ("📖 Подробно", "60")
        }

        buttons = []
        for level_key, (label, _) in levels.items():
            checkmark = " ✓" if level_key == current_level else ""
            buttons.append([{
                "text": f"{label}{checkmark}",
                "callback_data": f"settings_level_{level_key}"
            }])

        # Кнопка назад
        buttons.append([{
            "text": f"{UIComponents.EMOJI['back']} Назад в меню",
            "callback_data": "main_menu"
        }])

        return {"inline_keyboard": buttons}

    @staticmethod
    def summary_actions(user_id: int, summary_id: Optional[str] = None) -> Dict:
        """Панель быстрых действий после саммари"""
        sid = summary_id or "current"

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": f"{UIComponents.EMOJI['copy']} Копировать", "callback_data": f"action_copy_{sid}"},
                    {"text": f"{UIComponents.EMOJI['regenerate']} Пересоздать", "callback_data": f"action_regen_{sid}"}
                ],
                [
                    {"text": f"{UIComponents.EMOJI['pdf']} PDF", "callback_data": f"action_pdf_{sid}"},
                    {"text": f"{UIComponents.EMOJI['voice']} Озвучить", "callback_data": f"action_voice_{sid}"},
                    {"text": f"{UIComponents.EMOJI['more']} Подробнее", "callback_data": f"action_more_{sid}"}
                ],
                [
                    {"text": f"{UIComponents.EMOJI['home']} Главное меню", "callback_data": "main_menu"}
                ]
            ]
        }
        return keyboard

    @staticmethod
    def compression_levels(current_level: int = 30, message_id: Optional[int] = None) -> Dict:
        """Кнопки выбора уровня сжатия (используется в текущей версии)"""
        suffix = f"_{message_id}" if message_id else ""

        levels = {
            10: "🔥 Кратко",
            30: "⚖️ Средний",
            60: "📖 Подробно"
        }

        buttons = []
        row = []
        for level, label in levels.items():
            checkmark = " ✓" if level == current_level else ""
            row.append({
                "text": f"{label}{checkmark}",
                "callback_data": f"compression_{level}{suffix}"
            })

        buttons.append(row)
        return {"inline_keyboard": buttons}

    @staticmethod
    def file_preview_actions(file_info: Dict) -> Dict:
        """Действия при превью файла перед обработкой"""
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": f"{UIComponents.EMOJI['fast']} Быстрый", "callback_data": "file_mode_fast"},
                    {"text": f"{UIComponents.EMOJI['medium']} Средний", "callback_data": "file_mode_medium"},
                    {"text": f"{UIComponents.EMOJI['full']} Полный", "callback_data": "file_mode_full"}
                ],
                [
                    {"text": f"{UIComponents.EMOJI['confirm']} Начать обработку", "callback_data": "file_process_confirm"},
                    {"text": f"{UIComponents.EMOJI['cancel']} Отмена", "callback_data": "file_process_cancel"}
                ]
            ]
        }
        return keyboard

    @staticmethod
    def welcome_quick_start() -> Dict:
        """Быстрый старт при приветствии"""
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🔥 Кратко", "callback_data": "welcome_short"},
                    {"text": "⚖️ Средний", "callback_data": "welcome_balanced"},
                    {"text": "📖 Подробно", "callback_data": "welcome_detailed"}
                ],
                [
                    {"text": "❓ Как пользоваться?", "callback_data": "main_help"}
                ]
            ]
        }
        return keyboard

    @staticmethod
    def achievements_menu(unlocked: List[str], locked: List[str]) -> Dict:
        """Меню достижений с разблокированными и заблокированными"""
        buttons = []

        # Показываем первые 3 заблокированных достижения (мотивация)
        for achievement in locked[:3]:
            buttons.append([{
                "text": f"🔒 {achievement}",
                "callback_data": "achievement_info"
            }])

        # Кнопка назад
        buttons.append([{
            "text": f"{UIComponents.EMOJI['back']} Назад в меню",
            "callback_data": "main_menu"
        }])

        return {"inline_keyboard": buttons}

    @staticmethod
    def back_to_menu() -> Dict:
        """Простая кнопка назад в меню"""
        return {
            "inline_keyboard": [
                [{
                    "text": f"{UIComponents.EMOJI['back']} Назад в меню",
                    "callback_data": "main_menu"
                }]
            ]
        }


class Messages:
    """Текстовые сообщения для UI"""

    @staticmethod
    def main_menu_text() -> str:
        """Текст главного меню"""
        return """🏠 <b>ГЛАВНОЕ МЕНЮ</b>

Выбери действие ниже или просто отправь:
• 📝 Текст или статью
• 🌐 Ссылку на веб-страницу
• 📄 Документ (PDF, DOCX, TXT)
• 📚 Книгу (EPUB, FB2)
• ▶️ YouTube видео
• 🗣️ Аудио или голосовое

Я автоматически обработаю и создам саммари!"""

    @staticmethod
    def settings_text(current_level: str = "balanced") -> str:
        """Текст меню настроек"""
        level_descriptions = {
            "short": "🔥 <b>Кратко</b> — 2-3 главные мысли (10% от текста)",
            "balanced": "⚖️ <b>Средний</b> — Сбалансированное саммари (30% от текста)",
            "detailed": "📖 <b>Подробно</b> — Всё важное с деталями (60% от текста)"
        }

        current_desc = level_descriptions.get(current_level, level_descriptions["balanced"])

        return f"""⚙️ <b>НАСТРОЙКИ САММАРИЗАЦИИ</b>

<b>Текущий режим:</b>
{current_desc}

Выбери уровень детализации для всех будущих саммари:

• <b>Кратко</b> → Только самое главное
• <b>Средний</b> → Баланс объёма и деталей (рекомендуется)
• <b>Подробно</b> → Максимум полезной информации"""

    @staticmethod
    def welcome_text() -> str:
        """Улучшенное приветственное сообщение"""
        return """👋 <b>Привет!</b> Я превращаю длинные тексты в короткие выжимки.

🎯 <b>Выбери режим работы:</b>

<i>Или просто отправь текст/ссылку/файл — я подберу лучший формат!</i>"""

    @staticmethod
    def file_preview_text(file_info: Dict) -> str:
        """Превью файла перед обработкой"""
        name = file_info.get('name', 'Неизвестный файл')
        pages = file_info.get('pages', 0)
        size_mb = file_info.get('size_mb', 0)
        est_time = file_info.get('estimated_time', '1-2')

        return f"""📄 <b>Обнаружен файл:</b>

📖 <b>{name}</b>
📊 {pages} страниц | {size_mb:.1f} MB
⏱️ Примерное время: {est_time} мин

<b>Выбери режим обработки:</b>

• <b>Быстрый</b> — Основные главы (~1 мин)
• <b>Средний</b> — Все главы (~{est_time} мин)
• <b>Полный</b> — Каждая страница (~{int(est_time.split('-')[1]) + 2} мин)"""


class AchievementSystem:
    """Система достижений для геймификации"""

    ACHIEVEMENTS = {
        "first_step": {
            "name": "Первый шаг",
            "description": "Обработай свой первый текст",
            "icon": "✅",
            "requirement": 1
        },
        "active_reader": {
            "name": "Активный читатель",
            "description": "Обработай 10 текстов",
            "icon": "📚",
            "requirement": 10
        },
        "bookworm": {
            "name": "Книжный червь",
            "description": "Обработай 100 текстов",
            "icon": "🐛",
            "requirement": 100
        },
        "speed_demon": {
            "name": "Скоростной демон",
            "description": "Обработай 10 текстов за один день",
            "icon": "⚡",
            "requirement": 10
        },
        "time_saver": {
            "name": "Спаситель времени",
            "description": "Сэкономь 10 часов времени на чтение",
            "icon": "⏰",
            "requirement": 36000  # 10 часов в секундах
        }
    }

    @staticmethod
    def check_unlocked(user_stats: Dict) -> tuple[List[str], List[str]]:
        """Проверяет разблокированные и заблокированные достижения"""
        total_requests = user_stats.get('total_requests', 0)

        unlocked = []
        locked = []

        for key, achievement in AchievementSystem.ACHIEVEMENTS.items():
            if total_requests >= achievement['requirement']:
                unlocked.append(f"{achievement['icon']} {achievement['name']}")
            else:
                progress = total_requests
                required = achievement['requirement']
                locked.append(
                    f"{achievement['name']} ({progress}/{required})"
                )

        return unlocked, locked

    @staticmethod
    def format_achievements_text(unlocked: List[str], locked: List[str]) -> str:
        """Форматирует текст с достижениями"""
        text = "🏆 <b>ДОСТИЖЕНИЯ</b>\n\n"

        if unlocked:
            text += "<b>Разблокировано:</b>\n"
            for achievement in unlocked:
                text += f"✅ {achievement}\n"
            text += "\n"

        if locked:
            text += "<b>Ближайшие цели:</b>\n"
            for achievement in locked[:3]:  # Показываем только 3 ближайших
                text += f"🔒 {achievement}\n"

        return text
