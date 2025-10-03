"""
Точка входа для рефакторенного бота
"""

import asyncio
import logging
import os
from pathlib import Path

from bot.core.bot import RefactoredBot
from bot.state_manager import StateManager
from config import config
from database import Database
from audio_processor import AudioProcessor
from file_processor import FileProcessor
from youtube_processor import YouTubeProcessor
from url_processor import URLProcessor

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Главная функция запуска рефакторенного бота"""
    logger.info("=" * 60)
    logger.info("Запуск Telegram Companion (Refactored Version)")
    logger.info("=" * 60)

    # Инициализация базы данных
    logger.info("Инициализация базы данных...")
    db = Database(config.DATABASE_URL)
    db.init_db()

    # Инициализация state manager
    logger.info("Инициализация state manager...")
    state_manager = StateManager()

    # Инициализация Groq клиента (если доступен)
    groq_client = None
    if config.GROQ_API_KEY and config.ENABLE_GROQ_FALLBACK:
        try:
            from groq import Groq
            groq_client = Groq(api_key=config.GROQ_API_KEY)
            logger.info("✅ Groq клиент инициализирован")
        except Exception as e:
            logger.warning(f"⚠️  Не удалось инициализировать Groq: {e}")

    # Инициализация OpenRouter клиента (если доступен)
    openrouter_client = None
    if config.OPENROUTER_API_KEY:
        try:
            from openai import AsyncOpenAI
            openrouter_client = AsyncOpenAI(
                api_key=config.OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1"
            )
            logger.info("✅ OpenRouter клиент инициализирован")
        except Exception as e:
            logger.warning(f"⚠️  Не удалось инициализировать OpenRouter: {e}")

    # Проверка наличия хотя бы одного LLM клиента
    if not groq_client and not openrouter_client:
        logger.error("❌ Не инициализирован ни один LLM клиент (Groq/OpenRouter)")
        logger.error("❌ Установите GROQ_API_KEY или OPENROUTER_API_KEY в .env")
        return

    # Инициализация процессоров
    logger.info("Инициализация процессоров...")

    audio_processor = AudioProcessor(
        groq_client=groq_client,
        config=config
    )

    file_processor = FileProcessor(
        config=config
    )

    # Проверка cookies.txt для YouTube
    cookies_path = Path("cookies.txt")
    if not cookies_path.exists():
        logger.warning("⚠️  cookies.txt не найден - YouTube обработка может не работать")
        logger.warning("⚠️  См. README.md для инструкций по настройке cookies")

    youtube_processor = YouTubeProcessor(
        cookies_path=str(cookies_path) if cookies_path.exists() else None
    )

    url_processor = URLProcessor()

    # Создание и запуск бота
    logger.info("Создание RefactoredBot...")
    bot = RefactoredBot(
        token=config.TELEGRAM_BOT_TOKEN,
        db=db,
        state_manager=state_manager,
        groq_client=groq_client,
        openrouter_client=openrouter_client,
        audio_processor=audio_processor,
        file_processor=file_processor,
        youtube_processor=youtube_processor,
        url_processor=url_processor,
        config=config,
    )

    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
    finally:
        await bot.stop()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа прервана пользователем")
