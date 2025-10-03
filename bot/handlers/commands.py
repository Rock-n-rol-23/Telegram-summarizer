"""Обработчики команд бота"""

import logging
import sqlite3
from typing import Optional, Dict
from .base import BaseHandler
from bot.constants import WELCOME_MESSAGE_HTML

# Проверка доступности улучшенной аудио обработки
try:
    from bot.ui_settings import (
        get_settings_manager,
        generate_settings_keyboard,
        format_settings_message
    )
    ENHANCED_AUDIO_AVAILABLE = True
except ImportError:
    ENHANCED_AUDIO_AVAILABLE = False

logger = logging.getLogger(__name__)


class CommandHandler(BaseHandler):
    """Обработчик команд бота"""

    def __init__(self, session, base_url, db, state_manager, user_settings: Dict, user_states: Dict, user_messages_buffer: Dict):
        super().__init__(session, base_url, db, state_manager)
        self.user_settings = user_settings
        self.user_states = user_states
        self.user_messages_buffer = user_messages_buffer

    async def handle_start(self, update: dict):
        """Обработка команды /start"""
        chat_id = update["message"]["chat"]["id"]
        user = update["message"]["from"]

        logger.info(f"Обработка команды /start от пользователя {user.get('id')} в чате {chat_id}")

        # Очищаем любые пользовательские клавиатуры
        await self.clear_custom_keyboards(chat_id)

        await self.send_message(chat_id, WELCOME_MESSAGE_HTML, parse_mode="HTML")

    async def handle_help(self, update: dict):
        """Обработка команды /help"""
        chat_id = update["message"]["chat"]["id"]

        help_text = (
            "📖 **Полная справка**\n\n"
            "🎯 **КАК ПОЛЬЗОВАТЬСЯ:**\n"
            "Просто отправь текст, ссылку, документ или аудио — я автоматически подберу лучший формат саммари!\n\n"
            "📝 **ЧТО Я УМЕЮ:**\n"
            "• Тексты и статьи — выжимка с фактами\n"
            "• Веб-ссылки — адаптивное резюме\n"
            "• PDF, DOCX, TXT — структурированное саммари\n"
            "• Книги (EPUB, FB2) — сюжет и идеи\n"
            "• YouTube (до 2 часов) — резюме по субтитрам\n"
            "• Аудио/голосовые — транскрипция + саммари\n\n"
            "🎛 **УПРАВЛЕНИЕ ДЕТАЛЬНОСТЬЮ:**\n"
            "• <code>/short</code> — кратко (2-3 главные мысли)\n"
            "• <code>/balanced</code> — сбалансированно (рекомендуется) ✨\n"
            "• <code>/detailed</code> — подробно (всё важное)\n\n"
            "📊 **ДРУГИЕ КОМАНДЫ:**\n"
            "• <code>/stats</code> — твоя статистика\n"
            "• <code>/help</code> — эта справка\n"
            "• <code>/start</code> — перезапустить бота\n\n"
            "💡 **ЛИМИТЫ:**\n"
            "• 10 запросов в минуту\n"
            "• Документы до 20MB\n"
            "• Аудио до 50MB (~1 час)\n\n"
            "🔥 **Powered by Llama 3.3 70B + Whisper large v3**\n\n"
            "💬 Остались вопросы? Просто начни отправлять контент!"
        )

        await self.send_message(chat_id, help_text)

    async def handle_audio_settings(self, update: dict):
        """Обработка команды настроек аудио"""
        if not ENHANCED_AUDIO_AVAILABLE:
            await self.send_message(
                update["message"]["chat"]["id"],
                "❌ Улучшенные настройки аудио недоступны - обновите бота"
            )
            return

        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]

        try:
            settings_manager = get_settings_manager()
            if settings_manager:
                user_settings = settings_manager.get_user_settings(user_id)
                message_text = format_settings_message(user_settings)
                keyboard = generate_settings_keyboard()

                await self.send_message(chat_id, message_text, reply_markup=keyboard)
            else:
                await self.send_message(chat_id, "❌ Система настроек недоступна")

        except Exception as e:
            logger.error(f"Ошибка настроек аудио для пользователя {user_id}: {e}")
            await self.send_message(chat_id, "❌ Ошибка загрузки настроек")

    async def handle_smart_mode(self, update: dict):
        """Обработка команды /smart - переключение в режим умной суммаризации"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]

        # Используем StateManager для управления smart_mode
        state = self.state_manager.get_state(user_id)
        state.smart_mode = not state.smart_mode
        new_mode = state.smart_mode

        # Синхронизация с legacy словарем (временно для обратной совместимости)
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {}
        self.user_settings[user_id]["smart_mode"] = new_mode

        if new_mode:
            mode_text = ("🧠 **Умная суммаризация включена!**\n\n"
                        "Теперь бот создает концентрированные резюме с ключевыми инсайтами:\n\n"
                        "🎯 **Что получаете:**\n"
                        "• Только самые важные выводы и инсайты\n"
                        "• Автоматическое определение типа контента\n"
                        "• Извлечение критически важной информации\n\n"
                        "📊 **Управление детальностью:**\n"
                        "• /10 → 2 ключевых инсайта (максимальное сжатие)\n"
                        "• /30 → 3 ключевых инсайта (сбалансированно)\n"
                        "• /50 → 4 ключевых инсайта (подробно)\n\n"
                        "Отправьте любой текст, документ, аудио или ссылку для умной обработки!\n\n"
                        "_Чтобы вернуться к обычной суммаризации, снова нажмите /smart_")
        else:
            mode_text = ("📝 **Обычная суммаризация восстановлена**\n\n"
                        "Теперь бот использует стандартный режим суммаризации с настраиваемыми уровнями сжатия (10%, 30%, 50%).\n\n"
                        "Чтобы снова включить умную суммаризацию, нажмите /smart")

        await self.send_message(chat_id, mode_text)
        logger.info(f"Пользователь {user_id} {'включил' if new_mode else 'отключил'} умную суммаризацию")

    async def handle_stats(self, update: dict):
        """Обработка команды /stats"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]

        try:
            user_stats = self.db.get_user_stats(user_id)
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Ошибка получения статистики пользователя {user_id}: {e}")
            user_stats = {
                'total_requests': 0,
                'total_chars': 0,
                'total_summary_chars': 0,
                'avg_compression': 0,
                'first_request': None
            }

        stats_text = (
            f"📊 Ваша статистика:\n\n"
            f"• Обработано текстов: {user_stats['total_requests']}\n"
            f"• Символов обработано: {user_stats['total_chars']:,}\n"
            f"• Символов в саммари: {user_stats['total_summary_chars']:,}\n"
            f"• Среднее сжатие: {user_stats['avg_compression']:.1%}\n"
            f"• Первый запрос: {user_stats['first_request'] or 'Нет данных'}\n\n"
            f"📈 Используйте бота для обработки длинных текстов и статей!"
        )

        await self.send_message(chat_id, stats_text)

    async def handle_compression(self, update: dict, compression_level: int):
        """Обработка команд уровня детальности саммари"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]

        try:
            # Получаем username пользователя для логирования
            username = update["message"]["from"].get("username", "")

            # Сохраняем новый уровень сжатия в базе данных
            self.update_user_compression_level(user_id, compression_level, username)

            # Понятные названия уровней
            level_names = {
                10: "🔥 Кратко",
                30: "📊 Сбалансированно",
                60: "📖 Подробно"
            }
            level_name = level_names.get(compression_level, f"{compression_level}%")

            confirmation_text = (
                f"✅ Стиль саммаризации изменён: {level_name}\n\n"
                f"Теперь твои тексты будут обрабатываться в стиле \"{level_name}\".\n\n"
                f"📝 Просто отправь текст, статью или документ!"
            )

            await self.send_message(chat_id, confirmation_text)
            logger.info(f"Пользователь {user_id} изменил уровень сжатия на {compression_level}%")

        except Exception as e:
            logger.error(f"Ошибка обработки команды сжатия {compression_level}% для пользователя {user_id}: {e}")
            await self.send_message(chat_id, "❌ Произошла ошибка при изменении настроек. Попробуйте еще раз.")

    async def handle_direct_compression(self, update: dict, compression_level: str):
        """Обработка прямых команд сжатия /10, /30, /50"""
        chat_id = update["message"]["chat"]["id"]
        user_id = update["message"]["from"]["id"]

        logger.info(f"🚀 DIRECT COMPRESSION: Команда /{compression_level} от пользователя {user_id}")

        # Инициализируем состояние пользователя
        self.user_states[user_id] = {"step": "format_selection"}
        self.user_settings[user_id] = {"compression": compression_level if compression_level else 30}
        self.user_messages_buffer[user_id] = []

        # Устанавливаем состояние ожидания текста сразу с настройками по умолчанию
        self.user_states[user_id]["step"] = "waiting_text"
        self.user_settings[user_id]["format"] = "bullets"  # Всегда маркированный список

        await self.send_text_request(chat_id, user_id)

    # ============ Вспомогательные методы ============

    async def send_text_request(self, chat_id: int, user_id: int):
        """Запрос текста для суммаризации"""
        settings = self.user_settings[user_id]
        compression_text = {"10": "10%", "30": "30%", "50": "50%"}[settings["compression"]]
        format_text = {
            "bullets": "маркированный список",
            "paragraph": "связный абзац",
            "keywords": "ключевые слова"
        }[settings["format"]]

        text = f"""✅ Настройки применены:
• Сжатие: {compression_text}
• Формат: {format_text}

📝 Теперь отправьте текст для суммаризации любым способом:

1️⃣ Напишите или вставьте текст прямо в чат
2️⃣ Перешлите одно или несколько сообщений
3️⃣ Отправьте несколько сообщений подряд - я их объединю

Минимум: 100 символов
Максимум: 10,000 символов

💡 Для отмены используйте команду /start"""

        await self.send_message(chat_id, text)

        # Устанавливаем состояние ожидания текста
        self.user_states[user_id]["step"] = "waiting_text"

    def update_user_compression_level(self, user_id: int, compression_level: int, username: str = ""):
        """Обновление уровня сжатия пользователя в базе данных"""
        try:
            logger.info(f"Обновление уровня сжатия для пользователя {user_id}: {compression_level}%")
            self.db.update_compression_level(user_id, compression_level, username)
            logger.info(f"Уровень сжатия для пользователя {user_id} успешно обновлен: {compression_level}%")
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Ошибка обновления уровня сжатия для пользователя {user_id}: {e}")
            raise

    async def clear_custom_keyboards(self, chat_id: int):
        """Очистка пользовательских клавиатур"""
        import json
        import asyncio

        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": "🔄 Обновляю интерфейс...",
                "reply_markup": json.dumps({"remove_keyboard": True})
            }

            async with self.session.post(url, data=data) as response:
                result = await response.json()
                if result.get("ok"):
                    # Удаляем сообщение об обновлении после короткой задержки
                    message_id = result["result"]["message_id"]
                    await asyncio.sleep(1)
                    await self.delete_message(chat_id, message_id)
                    logger.info(f"Пользовательские клавиатуры очищены для чата {chat_id}")

        except Exception as e:
            logger.error(f"Ошибка при очистке клавиатур: {e}")

    async def delete_message(self, chat_id: int, message_id: int):
        """Удаление сообщения"""
        try:
            url = f"{self.base_url}/deleteMessage"
            data = {
                "chat_id": chat_id,
                "message_id": message_id
            }

            async with self.session.post(url, json=data) as response:
                result = await response.json()
                return result.get("ok", False)
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
            return False

    def get_compression_keyboard(self, current_level: int = None, message_id: int = None) -> dict:
        """Создание inline клавиатуры для выбора уровня сжатия"""
        suffix = f"_{message_id}" if message_id else ""

        buttons = [
            [
                {"text": "🔥 Кратко" + (" ✓" if current_level == 10 else ""), "callback_data": f"compression_10{suffix}"},
                {"text": "📊 Сбалансированно" + (" ✓" if current_level == 30 else ""), "callback_data": f"compression_30{suffix}"},
                {"text": "📖 Подробно" + (" ✓" if current_level == 60 else ""), "callback_data": f"compression_60{suffix}"}
            ]
        ]
        return {"inline_keyboard": buttons}
