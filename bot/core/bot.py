"""Главный класс рефакторенного бота"""

import asyncio
import logging
import aiohttp
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor

from bot.core.router import UpdateRouter
from bot.handlers.commands import CommandHandler
from bot.handlers.text_handler import TextHandler
from bot.handlers.document_handler import DocumentHandler
from bot.handlers.audio_handler import AudioHandler
from bot.handlers.callback_handler import CallbackHandler

logger = logging.getLogger(__name__)


class RefactoredBot:
    """Рефакторенный Telegram бот с модульной архитектурой"""

    def __init__(
        self,
        token: str,
        db,
        state_manager,
        groq_client=None,
        openrouter_client=None,
        audio_processor=None,
        file_processor=None,
        youtube_processor=None,
        url_processor=None,
        config=None,
    ):
        """
        Args:
            token: Telegram Bot API token
            db: Database instance
            state_manager: State manager for user states
            groq_client: Groq API client (optional)
            openrouter_client: OpenRouter API client (optional)
            audio_processor: Audio processor instance
            file_processor: File processor instance
            youtube_processor: YouTube processor instance
            url_processor: URL processor instance
            config: Configuration object
        """
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.db = db
        self.state_manager = state_manager
        self.groq_client = groq_client
        self.openrouter_client = openrouter_client
        self.audio_processor = audio_processor
        self.file_processor = file_processor
        self.youtube_processor = youtube_processor
        self.url_processor = url_processor
        self.config = config

        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None

        # Thread pool для блокирующих операций
        self.executor = ThreadPoolExecutor(max_workers=4)

        # Router для маршрутизации обновлений
        self.router = UpdateRouter()

        # Shared state dictionaries для handlers
        self.user_settings: Dict = {}
        self.user_states: Dict = {}
        self.user_messages_buffer: Dict = {}
        self.user_requests: Dict = {}
        self.processing_users: set = set()

        # Handlers будут инициализированы после создания session
        self.command_handler: Optional[CommandHandler] = None
        self.text_handler: Optional[TextHandler] = None
        self.document_handler: Optional[DocumentHandler] = None
        self.audio_handler: Optional[AudioHandler] = None
        self.callback_handler: Optional[CallbackHandler] = None

        # Offset для long polling
        self.update_offset = 0

        logger.info("RefactoredBot инициализирован")

    async def start(self):
        """Запуск бота и инициализация компонентов"""
        logger.info("Запуск RefactoredBot...")

        # Создаем aiohttp session
        self.session = aiohttp.ClientSession()

        # Инициализируем handlers
        self._initialize_handlers()

        # Получаем информацию о боте
        bot_info = await self._get_me()
        if bot_info:
            logger.info(f"✅ Бот запущен: @{bot_info.get('username', 'unknown')}")
        else:
            logger.error("❌ Не удалось получить информацию о боте")
            return

        # Запускаем long polling
        await self.run_polling()

    def _initialize_handlers(self):
        """Инициализация всех handlers"""
        logger.info("Инициализация handlers...")

        # CommandHandler
        self.command_handler = CommandHandler(
            session=self.session,
            base_url=self.base_url,
            db=self.db,
            state_manager=self.state_manager,
            user_settings=self.user_settings,
            user_states=self.user_states,
            user_messages_buffer=self.user_messages_buffer,
        )

        # TextHandler
        self.text_handler = TextHandler(
            session=self.session,
            base_url=self.base_url,
            db=self.db,
            state_manager=self.state_manager,
            groq_client=self.groq_client,
            openrouter_client=self.openrouter_client,
            smart_summarizer=None,  # TODO: создать если нужен
            user_requests=self.user_requests,
            processing_users=self.processing_users,
            user_states=self.user_states,
            user_settings=self.user_settings,
            user_messages_buffer=self.user_messages_buffer,
            db_executor=self.executor,
        )

        # DocumentHandler
        self.document_handler = DocumentHandler(
            session=self.session,
            base_url=self.base_url,
            db=self.db,
            state_manager=self.state_manager,
            file_processor=self.file_processor,
            groq_client=self.groq_client,
            user_requests=self.user_requests,
            processing_users=self.processing_users,
            db_executor=self.executor,
        )

        # AudioHandler
        self.audio_handler = AudioHandler(
            session=self.session,
            base_url=self.base_url,
            db=self.db,
            state_manager=self.state_manager,
            token=self.token,
            audio_processor=self.audio_processor,
            smart_summarizer=None,  # TODO: создать если нужен
            groq_client=self.groq_client,
            openrouter_client=self.openrouter_client,
            user_requests=self.user_requests,
            processing_users=self.processing_users,
        )

        # CallbackHandler
        self.callback_handler = CallbackHandler(
            session=self.session,
            base_url=self.base_url,
            db=self.db,
            state_manager=self.state_manager,
        )

        logger.info("✅ Все handlers инициализированы")

    async def run_polling(self):
        """Основной цикл long polling"""
        logger.info("Запуск long polling...")

        while True:
            try:
                updates = await self._get_updates()

                if updates:
                    for update in updates:
                        # Обрабатываем каждое обновление
                        asyncio.create_task(self.process_update(update))

                        # Обновляем offset
                        self.update_offset = update["update_id"] + 1

            except asyncio.CancelledError:
                logger.info("Long polling остановлен")
                break
            except Exception as e:
                logger.error(f"Ошибка в long polling: {e}", exc_info=True)
                await asyncio.sleep(3)

    async def process_update(self, update: dict):
        """
        Обработка одного обновления от Telegram

        Args:
            update: Telegram update object
        """
        try:
            # Роутинг обновления
            handler_type, extra_data = self.router.route(update)

            logger.info(f"Роутинг: {handler_type}, extra: {extra_data}")

            # Диспетчеризация к соответствующему handler
            if handler_type == "command":
                await self._handle_command(update, extra_data)
            elif handler_type == "text":
                await self.text_handler.handle_text_message(update)
            elif handler_type == "document":
                await self.document_handler.handle_document_message(update)
            elif handler_type == "audio":
                await self.audio_handler.handle_audio_message(update)
            elif handler_type == "callback":
                await self.callback_handler.handle_callback_query(update)
            elif handler_type == "youtube":
                await self.text_handler.handle_text_message(update)  # YouTube обрабатывается в TextHandler
            elif handler_type == "url":
                await self.text_handler.handle_text_message(update)  # URL обрабатывается в TextHandler
            elif handler_type == "unknown":
                logger.warning(f"Неизвестный тип обновления: {update.keys()}")
            else:
                logger.warning(f"Необработанный тип handler: {handler_type}")

        except Exception as e:
            logger.error(f"Ошибка обработки обновления: {e}", exc_info=True)

    async def _handle_command(self, update: dict, extra_data: Optional[Dict]):
        """Обработка команд через CommandHandler"""
        if not extra_data or "command" not in extra_data:
            logger.warning("Команда без данных")
            return

        command = extra_data["command"]

        # Маппинг команд на методы CommandHandler
        command_methods = {
            "start": self.command_handler.handle_start,
            "help": self.command_handler.handle_help,
            "stats": self.command_handler.handle_stats,
            "smart_mode": self.command_handler.handle_smart_mode,
            "audio_settings": self.command_handler.handle_audio_settings,
            "compression_10": lambda u: self.command_handler.handle_compression(u, 0.1),
            "compression_30": lambda u: self.command_handler.handle_compression(u, 0.3),
            "compression_60": lambda u: self.command_handler.handle_compression(u, 0.6),
            "direct_compression_10": lambda u: self.command_handler.handle_direct_compression(u, 0.1),
            "direct_compression_30": lambda u: self.command_handler.handle_direct_compression(u, 0.3),
            "direct_compression_50": lambda u: self.command_handler.handle_direct_compression(u, 0.5),
        }

        handler = command_methods.get(command)
        if handler:
            await handler(update)
        else:
            logger.warning(f"Неизвестная команда: {command}")

    async def _get_updates(self) -> list:
        """Получение обновлений от Telegram API"""
        url = f"{self.base_url}/getUpdates"
        params = {
            "offset": self.update_offset,
            "timeout": 30,
            "allowed_updates": ["message", "callback_query"],
        }

        try:
            async with self.session.get(url, params=params, timeout=35) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("result", [])
                else:
                    logger.error(f"Ошибка getUpdates: {response.status}")
                    return []
        except asyncio.TimeoutError:
            return []
        except Exception as e:
            logger.error(f"Ошибка запроса getUpdates: {e}")
            return []

    async def _get_me(self) -> Optional[dict]:
        """Получение информации о боте"""
        url = f"{self.base_url}/getMe"

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("result")
                else:
                    logger.error(f"Ошибка getMe: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Ошибка запроса getMe: {e}")
            return None

    async def stop(self):
        """Остановка бота и очистка ресурсов"""
        logger.info("Остановка RefactoredBot...")

        # Закрываем HTTP session
        if self.session:
            await self.session.close()

        # Закрываем thread pool
        if self.executor:
            self.executor.shutdown(wait=True)

        logger.info("✅ RefactoredBot остановлен")
