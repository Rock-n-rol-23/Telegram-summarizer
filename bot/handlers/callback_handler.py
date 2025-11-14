"""Обработчик callback queries (нажатия на inline кнопки)"""

import logging
from .base import BaseHandler
from bot.ui_components import UIComponents, Messages, AchievementSystem
from bot.constants import MAIN_MENU_TEXT

logger = logging.getLogger(__name__)


class CallbackHandler(BaseHandler):
    """Обработчик callback queries от inline кнопок"""

    def __init__(self, session, base_url, db, state_manager, text_handler=None, audio_handler=None):
        super().__init__(session, base_url, db, state_manager)
        self.text_handler = text_handler
        self.audio_handler = audio_handler

    async def handle_callback_query(self, callback_query: dict):
        """Обработка callback query"""
        query_id = callback_query["id"]
        callback_data = callback_query.get("data", "")
        user_id = callback_query["from"]["id"]

        # Получаем chat_id из сообщения
        message = callback_query.get("message")
        if not message:
            await self.answer_callback_query(query_id, "❌ Ошибка: сообщение не найдено")
            return

        chat_id = message["chat"]["id"]
        message_id = message["message_id"]

        logger.info(f"Callback query от пользователя {user_id}: {callback_data}")

        try:
            # Обработка различных типов callback
            if callback_data.startswith("compression_"):
                await self.handle_compression_callback(
                    query_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("audio_format_"):
                await self.handle_audio_format_callback(
                    query_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("audio_verbosity_"):
                await self.handle_audio_verbosity_callback(
                    query_id, chat_id, message_id, user_id, callback_data
                )
            # Новые обработчики для улучшенного UI
            elif callback_data == "main_menu":
                await self.handle_main_menu(query_id, chat_id, message_id)
            elif callback_data == "main_settings":
                await self.handle_main_settings(query_id, chat_id, message_id, user_id)
            elif callback_data == "main_stats":
                await self.handle_main_stats(query_id, chat_id, message_id, user_id)
            elif callback_data == "main_help":
                await self.handle_main_help(query_id, chat_id, message_id)
            elif callback_data == "main_achievements":
                await self.handle_main_achievements(query_id, chat_id, message_id, user_id)
            elif callback_data.startswith("welcome_"):
                await self.handle_welcome_choice(query_id, chat_id, message_id, user_id, callback_data)
            elif callback_data.startswith("settings_level_"):
                await self.handle_settings_level(query_id, chat_id, message_id, user_id, callback_data)
            elif callback_data.startswith("action_"):
                await self.handle_summary_action(query_id, chat_id, message_id, user_id, callback_data)
            elif callback_data.startswith("audio_transcript_") or callback_data.startswith("audio_reasoning_"):
                # Передаём обработку audio handler'у
                if self.audio_handler:
                    await self.audio_handler.handle_audio_callback(callback_query)
                else:
                    await self.answer_callback_query(query_id, "❌ Audio handler недоступен")
                    logger.error("AudioHandler не инициализирован в CallbackHandler!")
            else:
                # Неизвестный callback
                await self.answer_callback_query(query_id, "⚠️ Неизвестная команда")
                logger.warning(f"Неизвестный callback_data: {callback_data}")

        except Exception as e:
            logger.error(f"Ошибка обработки callback query: {e}")
            await self.answer_callback_query(query_id, "❌ Произошла ошибка")

    async def handle_compression_callback(
        self, query_id: str, chat_id: int, message_id: int, user_id: int, callback_data: str
    ):
        """Обработка изменения уровня сжатия с пересозданием саммари"""
        try:
            # Извлекаем уровень из callback_data (например: "compression_30")
            parts = callback_data.split("_")
            compression_level = int(parts[1])

            # Сохраняем в БД
            try:
                self.db.update_compression_level(user_id, compression_level, "")
                logger.info(f"Обновлен уровень сжатия для пользователя {user_id}: {compression_level}%")
            except Exception as e:
                logger.error(f"Ошибка сохранения уровня сжатия: {e}")
                await self.answer_callback_query(query_id, "❌ Ошибка сохранения настроек")
                return

            # Показываем индикатор обработки
            await self.answer_callback_query(
                query_id,
                f"🔄 Пересоздаю саммари...",
                show_alert=False
            )

            # Пересоздаем саммари через TextHandler
            if self.text_handler:
                await self.text_handler.recreate_summary(user_id, chat_id, message_id, compression_level)
            else:
                logger.error("TextHandler не инициализирован в CallbackHandler!")
                await self.edit_message_text(
                    chat_id,
                    message_id,
                    "❌ Ошибка: TextHandler недоступен.\n\nОтправьте текст заново."
                )

        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка парсинга callback_data: {e}")
            await self.answer_callback_query(query_id, "❌ Неверный формат данных")

    async def handle_audio_format_callback(
        self, query_id: str, chat_id: int, message_id: int, user_id: int, callback_data: str
    ):
        """Обработка изменения формата аудио"""
        try:
            # Извлекаем формат из callback_data (например: "audio_format_detailed")
            format_type = callback_data.replace("audio_format_", "")

            # Проверяем доступность enhanced audio settings
            try:
                from bot.ui_settings import get_settings_manager

                settings_manager = get_settings_manager()
                if settings_manager:
                    settings_manager.update_user_format(user_id, format_type)
                    logger.info(
                        f"Обновлен формат аудио для пользователя {user_id}: {format_type}"
                    )

                    format_names = {
                        "detailed": "Подробный",
                        "concise": "Краткий",
                        "bullets": "Маркированный список"
                    }
                    format_name = format_names.get(format_type, format_type)

                    await self.answer_callback_query(
                        query_id, f"✅ Формат изменён: {format_name}"
                    )
                else:
                    await self.answer_callback_query(query_id, "❌ Настройки недоступны")
            except ImportError:
                await self.answer_callback_query(
                    query_id, "❌ Функция недоступна - обновите бота"
                )

        except Exception as e:
            logger.error(f"Ошибка обработки audio format callback: {e}")
            await self.answer_callback_query(query_id, "❌ Ошибка обработки")

    async def handle_audio_verbosity_callback(
        self, query_id: str, chat_id: int, message_id: int, user_id: int, callback_data: str
    ):
        """Обработка изменения детальности аудио"""
        try:
            # Извлекаем уровень verbosity
            verbosity_type = callback_data.replace("audio_verbosity_", "")

            try:
                from bot.ui_settings import get_settings_manager

                settings_manager = get_settings_manager()
                if settings_manager:
                    settings_manager.update_user_verbosity(user_id, verbosity_type)
                    logger.info(
                        f"Обновлена детальность аудио для пользователя {user_id}: {verbosity_type}"
                    )

                    verbosity_names = {
                        "high": "Высокая",
                        "medium": "Средняя",
                        "low": "Низкая"
                    }
                    verbosity_name = verbosity_names.get(verbosity_type, verbosity_type)

                    await self.answer_callback_query(
                        query_id, f"✅ Детальность изменена: {verbosity_name}"
                    )
                else:
                    await self.answer_callback_query(query_id, "❌ Настройки недоступны")
            except ImportError:
                await self.answer_callback_query(
                    query_id, "❌ Функция недоступна - обновите бота"
                )

        except Exception as e:
            logger.error(f"Ошибка обработки audio verbosity callback: {e}")
            await self.answer_callback_query(query_id, "❌ Ошибка обработки")

    async def answer_callback_query(
        self, query_id: str, text: str = "", show_alert: bool = False
    ):
        """Отправка ответа на callback query"""
        url = f"{self.base_url}/answerCallbackQuery"
        data = {"callback_query_id": query_id, "text": text, "show_alert": show_alert}

        async with self.session.post(url, json=data) as response:
            result = await response.json()
            if not result.get("ok"):
                logger.error(f"Ошибка answerCallbackQuery: {result}")
            return result

    # ============ Новые обработчики для улучшенного UI ============

    async def handle_main_menu(self, query_id: str, chat_id: int, message_id: int):
        """Показать главное меню"""
        keyboard = UIComponents.main_menu()
        await self.edit_message_text(chat_id, message_id, MAIN_MENU_TEXT, parse_mode="HTML", reply_markup=keyboard)
        await self.answer_callback_query(query_id, "🏠 Главное меню")

    async def handle_main_settings(self, query_id: str, chat_id: int, message_id: int, user_id: int):
        """Показать настройки"""
        # Получаем текущий уровень пользователя
        user_settings = self.db.get_user_settings(user_id)
        compression_level = user_settings.get('compression_level', 30)

        # Определяем текущий режим
        if compression_level <= 15:
            current_level = "short"
        elif compression_level <= 45:
            current_level = "balanced"
        else:
            current_level = "detailed"

        settings_text = Messages.settings_text(current_level)
        keyboard = UIComponents.settings_menu(current_level)

        await self.edit_message_text(chat_id, message_id, settings_text, parse_mode="HTML", reply_markup=keyboard)
        await self.answer_callback_query(query_id, "⚙️ Настройки")

    async def handle_main_stats(self, query_id: str, chat_id: int, message_id: int, user_id: int):
        """Показать статистику с достижениями"""
        import sqlite3

        try:
            user_stats = self.db.get_user_stats(user_id)
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Ошибка получения статистики: {e}")
            user_stats = {
                'total_requests': 0,
                'total_chars': 0,
                'total_summary_chars': 0,
                'avg_compression': 0
            }

        # Вычисляем метрики
        total_requests = user_stats['total_requests']
        total_chars = user_stats['total_chars']
        total_summary_chars = user_stats['total_summary_chars']
        avg_compression = user_stats['avg_compression']

        # Сэкономленное время
        avg_chars_per_word = 5
        words_saved = (total_chars - total_summary_chars) / avg_chars_per_word
        time_saved_hours = int((words_saved / 200) / 60)

        # Эквивалент книг
        books_equivalent = total_chars / 300000

        # Достижения
        unlocked, locked = AchievementSystem.check_unlocked(user_stats)

        stats_text = f"""🏆 <b>ТВОЯ СТАТИСТИКА</b>

📚 Обработано <b>{total_requests}</b> текстов"""

        if books_equivalent >= 1:
            stats_text += f" (как <b>{books_equivalent:.1f}</b> книг)"

        if time_saved_hours > 0:
            stats_text += f"\n⚡ Сэкономлено <b>~{time_saved_hours}</b> часов"

        stats_text += f"\n🎯 Сжато: {total_chars:,} → {total_summary_chars:,}"
        stats_text += f"\n\n{AchievementSystem.format_achievements_text(unlocked, locked)}"

        keyboard = UIComponents.back_to_menu()
        await self.edit_message_text(chat_id, message_id, stats_text, parse_mode="HTML", reply_markup=keyboard)
        await self.answer_callback_query(query_id, "📊 Статистика")

    async def handle_main_help(self, query_id: str, chat_id: int, message_id: int):
        """Показать справку"""
        help_text = """❓ <b>СПРАВКА</b>

<b>Что я умею:</b>
• 📝 Тексты — краткая выжимка
• 🌐 Веб-статьи — адаптивное саммари
• 📄 PDF, DOCX, TXT — структурированное резюме
• 📚 EPUB, FB2 — резюме книги
• ▶️ YouTube — саммари по субтитрам
• 🗣️ Аудио — транскрипция + саммари

<b>Уровни детализации:</b>
• 🔥 Кратко — только главное (10%)
• ⚖️ Средний — баланс (30%)
• 📖 Подробно — всё важное (60%)

<b>Лимиты:</b>
• 10 запросов/мин
• Документы до 20 MB
• Аудио до 50 MB

💡 Просто отправь контент — я сам выберу лучший формат!"""

        keyboard = UIComponents.back_to_menu()
        await self.edit_message_text(chat_id, message_id, help_text, parse_mode="HTML", reply_markup=keyboard)
        await self.answer_callback_query(query_id, "❓ Справка")

    async def handle_main_achievements(self, query_id: str, chat_id: int, message_id: int, user_id: int):
        """Показать достижения"""
        import sqlite3

        try:
            user_stats = self.db.get_user_stats(user_id)
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Ошибка получения статистики: {e}")
            user_stats = {'total_requests': 0}

        unlocked, locked = AchievementSystem.check_unlocked(user_stats)

        achievements_text = AchievementSystem.format_achievements_text(unlocked, locked)
        keyboard = UIComponents.back_to_menu()

        await self.edit_message_text(chat_id, message_id, achievements_text, parse_mode="HTML", reply_markup=keyboard)
        await self.answer_callback_query(query_id, "🏆 Достижения")

    async def handle_welcome_choice(self, query_id: str, chat_id: int, message_id: int, user_id: int, callback_data: str):
        """Обработка выбора режима при приветствии"""
        # Извлекаем режим (welcome_short, welcome_balanced, welcome_detailed)
        mode = callback_data.replace("welcome_", "")

        # Мапинг режимов на уровни сжатия
        mode_to_level = {
            "short": 10,
            "balanced": 30,
            "detailed": 60
        }

        compression_level = mode_to_level.get(mode, 30)

        # Сохраняем настройку
        try:
            self.db.update_compression_level(user_id, compression_level, "")

            mode_names = {
                "short": "🔥 Кратко",
                "balanced": "⚖️ Средний",
                "detailed": "📖 Подробно"
            }

            await self.answer_callback_query(query_id, f"✅ Выбран режим: {mode_names.get(mode, mode)}")

            # Обновляем сообщение
            response_text = f"""✅ <b>Режим установлен: {mode_names.get(mode, mode)}</b>

Теперь просто отправь:
• 📝 Текст или статью
• 🌐 Ссылку
• 📄 Документ
• 🗣️ Аудио

Я создам саммари в выбранном стиле!"""

            keyboard = UIComponents.main_menu()
            await self.edit_message_text(chat_id, message_id, response_text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Ошибка сохранения режима: {e}")
            await self.answer_callback_query(query_id, "❌ Ошибка сохранения")

    async def handle_settings_level(self, query_id: str, chat_id: int, message_id: int, user_id: int, callback_data: str):
        """Обработка изменения уровня детализации в настройках"""
        # Извлекаем уровень (settings_level_short, settings_level_balanced, settings_level_detailed)
        level = callback_data.replace("settings_level_", "")

        level_to_compression = {
            "short": 10,
            "balanced": 30,
            "detailed": 60
        }

        compression_level = level_to_compression.get(level, 30)

        try:
            self.db.update_compression_level(user_id, compression_level, "")

            # Обновляем меню настроек с новым выбранным уровнем
            settings_text = Messages.settings_text(level)
            keyboard = UIComponents.settings_menu(level)

            await self.edit_message_text(chat_id, message_id, settings_text, parse_mode="HTML", reply_markup=keyboard)
            await self.answer_callback_query(query_id, f"✅ Уровень изменён!")

        except Exception as e:
            logger.error(f"Ошибка сохранения уровня: {e}")
            await self.answer_callback_query(query_id, "❌ Ошибка сохранения")

    async def handle_summary_action(self, query_id: str, chat_id: int, message_id: int, user_id: int, callback_data: str):
        """Обработка быстрых действий после саммари"""
        # Извлекаем действие (action_copy, action_regen, action_pdf, action_voice, action_more)
        action = callback_data.split("_")[1]

        if action == "copy":
            await self.answer_callback_query(query_id, "📋 Скопируй текст саммари выше", show_alert=True)

        elif action == "regen":
            # Пересоздать саммари
            await self.answer_callback_query(query_id, "🔄 Пересоздаю саммари...")
            if self.text_handler:
                # Используем текущий уровень сжатия
                user_settings = self.db.get_user_settings(user_id)
                compression_level = user_settings.get('compression_level', 30)
                await self.text_handler.recreate_summary(user_id, chat_id, message_id, compression_level)
            else:
                await self.send_message(chat_id, "❌ Ошибка: отправьте текст заново")

        elif action == "pdf":
            await self.answer_callback_query(query_id, "💾 PDF генерация в разработке...", show_alert=True)
            # TODO: Реализовать генерацию PDF

        elif action == "voice":
            await self.answer_callback_query(query_id, "🗣️ Озвучивание в разработке...", show_alert=True)
            # TODO: Реализовать TTS

        elif action == "more":
            # Увеличить детальность на +20%
            user_settings = self.db.get_user_settings(user_id)
            current_level = user_settings.get('compression_level', 30)
            new_level = min(current_level + 20, 80)  # Максимум 80%

            await self.answer_callback_query(query_id, f"📊 Увеличиваю детальность до {new_level}%...")
            if self.text_handler:
                await self.text_handler.recreate_summary(user_id, chat_id, message_id, new_level)
            else:
                await self.send_message(chat_id, "❌ Ошибка: отправьте текст заново")
