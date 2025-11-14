"""Обработчик документов и файлов"""

import logging
import time
import sqlite3
from typing import Dict, Set, Optional
from .base import BaseHandler
from bot.core.decorators import retry_on_failure
from llm.provider_router import groq_compatible_client

logger = logging.getLogger(__name__)


class DocumentHandler(BaseHandler):
    """Обработчик документов (PDF, DOCX, EPUB, FB2 и др.)"""

    def __init__(
        self,
        session,
        base_url,
        db,
        state_manager,
        file_processor,
        groq_client,
        user_requests: Dict,
        processing_users: Set,
        db_executor
    ):
        super().__init__(session, base_url, db, state_manager)
        self.file_processor = file_processor
        # Используем Groq-совместимый wrapper с LLM Router (Gemini → OpenRouter → Groq)
        self.groq_client = groq_compatible_client
        self.user_requests = user_requests
        self.processing_users = processing_users
        self.db_executor = db_executor

    async def handle_document_message(self, update: dict):
        """Обработка документов (PDF, DOCX, DOC, TXT, EPUB, FB2 и др.)"""
        try:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            username = message["from"].get("username", "")
            document = message["document"]

            # Проверка лимита запросов
            if not self.check_user_rate_limit(user_id):
                await self.send_message(
                    chat_id,
                    "⏰ Превышен лимит запросов!\n\n"
                    "Пожалуйста, подождите минуту перед отправкой нового файла. "
                    "Лимит: 10 запросов в минуту."
                )
                return

            # Проверка на повторную обработку
            if user_id in self.processing_users:
                await self.send_message(
                    chat_id,
                    "⚠️ Обработка в процессе!\n\n"
                    "Пожалуйста, дождитесь завершения предыдущего запроса."
                )
                return

            # Добавляем пользователя в список обрабатываемых
            self.processing_users.add(user_id)

            # Проверяем информацию о файле
            file_name = document.get("file_name", "unknown")
            file_size = document.get("file_size", 0)

            logger.info(
                f"Получен документ от пользователя {user_id}: {file_name} ({file_size} байт)"
            )

            # Проверка размера файла (максимум 20 MB = 20,971,520 байт)
            MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB в байтах
            if file_size > MAX_FILE_SIZE:
                size_mb = file_size / (1024 * 1024)
                max_size_mb = MAX_FILE_SIZE / (1024 * 1024)

                await self.send_message(
                    chat_id,
                    f"❌ <b>Файл слишком большой!</b>\n\n"
                    f"📄 Файл: <code>{file_name}</code>\n"
                    f"📊 Размер: <b>{size_mb:.1f} MB</b>\n"
                    f"⚠️ Максимум: <b>{max_size_mb:.0f} MB</b>\n\n"
                    f"💡 <b>Решение:</b>\n"
                    f"• Разбейте файл на части\n"
                    f"• Сожмите PDF (используйте онлайн-сервисы)\n"
                    f"• Удалите изображения из документа",
                    parse_mode="HTML"
                )

                # Удаляем пользователя из списка обрабатываемых
                self.processing_users.discard(user_id)
                return

            # Отправляем сообщение о начале обработки
            processing_message = await self.send_message(
                chat_id,
                f"📄 Обрабатываю документ: {file_name}\n\n⏳ Извлекаю текст..."
            )
            processing_message_id = (
                processing_message.get("result", {}).get("message_id")
                if processing_message and processing_message.get("ok")
                else None
            )

            try:
                # Получаем информацию о файле от Telegram
                file_info_response = await self.get_file_info(document["file_id"])
                if not file_info_response or not file_info_response.get("ok"):
                    await self.send_message(chat_id, "❌ Не удалось получить информацию о файле")
                    return

                file_info = file_info_response["result"]
                file_path = f"https://api.telegram.org/file/bot{self.base_url.split('/bot')[1].split('/')[0]}/{file_info['file_path']}"

                # Обновляем сообщение о прогрессе
                if processing_message_id:
                    await self.edit_message_text(
                        chat_id,
                        processing_message_id,
                        f"📄 Обрабатываю документ: {file_name}\n\n📥 Скачиваю файл..."
                    )

                # Используем file_processor для скачивания и обработки
                download_result = await self.file_processor.download_telegram_file(
                    {"file_path": file_path}, file_name, file_size, self.session
                )

                if not download_result["success"]:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, f"❌ {download_result['error']}")
                    return

                # Определяем прогресс сообщение в зависимости от типа файла
                extension = download_result["file_extension"].lower()
                if extension == '.pdf':
                    progress_text = (
                        f"📄 Обрабатываю документ: {file_name}\n\n"
                        f"🔍 Извлекаю текст (PDF → текстовый слой + OCR)..."
                    )
                elif extension == '.pptx':
                    progress_text = (
                        f"📊 Обрабатываю презентацию: {file_name}\n\n"
                        f"🎯 Извлекаю слайды и заметки..."
                    )
                elif extension in ('.png', '.jpg', '.jpeg'):
                    progress_text = (
                        f"🖼️ Обрабатываю изображение: {file_name}\n\n"
                        f"👁️ Распознаю текст (OCR)..."
                    )
                elif extension in ('.epub', '.fb2'):
                    progress_text = (
                        f"📚 Обрабатываю книгу: {file_name}\n\n"
                        f"📖 Извлекаю текст и метаданные..."
                    )
                else:
                    progress_text = (
                        f"📄 Обрабатываю документ: {file_name}\n\n"
                        f"📝 Извлекаю текст..."
                    )

                if processing_message_id:
                    await self.edit_message_text(chat_id, processing_message_id, progress_text)

                # Извлекаем текст из файла
                text_result = self.file_processor.extract_text_from_file(
                    download_result["file_path"],
                    download_result["file_extension"]
                )

                # Очищаем временные файлы
                self.file_processor.cleanup_temp_file(download_result["temp_dir"])

                if not text_result["success"]:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(chat_id, f"❌ {text_result['error']}")
                    return

                extracted_text = text_result["text"]
                extraction_method = text_result.get("method", "unknown")
                extraction_meta = text_result.get("meta", {})

                # Проверяем длину извлеченного текста
                if len(extracted_text) < 100:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(
                        chat_id,
                        f"📝 Текст слишком короткий!\n\n"
                        f"Из документа извлечено {len(extracted_text)} символов. "
                        f"Для качественной суммаризации нужно минимум 100 символов."
                    )
                    return

                # Показываем информацию о методе извлечения
                if "ocr" in extraction_method and extraction_meta.get("ocr_pages"):
                    ocr_info = (
                        f"🔎 Режим: PDF → OCR "
                        f"(страницы: {','.join(map(str, extraction_meta['ocr_pages']))})"
                    )
                elif extraction_method == "python-pptx" and extraction_meta.get("slides"):
                    slides_count = extraction_meta.get(
                        "total_slides",
                        len(extraction_meta["slides"])
                    )
                    ocr_info = f"📊 Обнаружена презентация: {slides_count} слайдов"
                elif "ocr" in extraction_method:
                    ocr_info = "👁️ Режим: OCR (распознавание текста)"
                else:
                    ocr_info = f"📝 Режим: {extraction_method}"

                if processing_message_id:
                    await self.edit_message_text(
                        chat_id,
                        processing_message_id,
                        f"📄 Обрабатываю документ: {file_name}\n\n{ocr_info}\n\n🤖 Создаю резюме..."
                    )

                # Получаем уровень сжатия пользователя
                compression_ratio = await self.get_user_compression_level(user_id)

                # Определяем тип документа
                doc_type = self._detect_document_type(
                    extracted_text,
                    file_name,
                    download_result["file_extension"],
                    extraction_meta
                )

                # Саммаризируем с учетом типа документа
                if doc_type == 'book':
                    logger.info("📚 Обнаружена книга, используем специализированную саммаризацию")
                    summary = await self.summarize_book_content(
                        extracted_text,
                        metadata=extraction_meta,
                        compression_ratio=compression_ratio
                    )
                else:
                    summary = await self.summarize_file_content(
                        extracted_text,
                        file_name,
                        download_result["file_extension"],
                        compression_ratio
                    )

                if summary:
                    # Определяем иконку и заголовок по типу файла/документа
                    if doc_type == 'book':
                        icon = "📚"
                        display_type = "книги"
                        # Добавляем метаданные книги если есть
                        if extraction_meta.get('title') and extraction_meta.get('author'):
                            file_name = (
                                f"{extraction_meta['title']} ({extraction_meta['author']})"
                            )
                    elif extension == '.pptx':
                        icon = "📊"
                        display_type = "презентации"
                    elif extension in ('.png', '.jpg', '.jpeg'):
                        icon = "🖼️"
                        display_type = "изображения"
                    elif extension in ['.epub', '.fb2']:
                        icon = "📖"
                        display_type = "книги"
                    else:
                        icon = "📄"
                        display_type = "документа"

                    # Формируем дополнительную информацию
                    extra_info = ""
                    if extraction_meta.get("ocr_pages"):
                        extra_info = (
                            f"\n• OCR страницы: "
                            f"{', '.join(map(str, extraction_meta['ocr_pages']))}"
                        )
                    elif extraction_meta.get("total_slides"):
                        extra_info = (
                            f"\n• Слайды обработаны: "
                            f"{extraction_meta['slides_with_content']}/"
                            f"{extraction_meta['total_slides']}"
                        )
                    elif doc_type == 'book' and extraction_meta.get('author'):
                        extra_info = f"\n• Автор: {extraction_meta['author']}"
                        if extraction_meta.get('language'):
                            extra_info += f"\n• Язык: {extraction_meta['language']}"

                    # Формируем итоговый ответ
                    response_text = f"""{icon} **Резюме {display_type}: {file_name}**

{summary}

📊 **Статистика:**
• Исходный текст: {len(extracted_text):,} символов
• Резюме: {len(summary):,} символов
• Сжатие: {compression_ratio:.0%}
• Метод извлечения: {extraction_method}{extra_info}"""

                    # Удаляем сообщение о обработке
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)

                    await self.send_message(chat_id, response_text)

                    # Сохраняем в базу данных (неблокирующая запись)
                    try:
                        await self._run_in_executor(
                            self.db.save_user_request,
                            user_id,
                            f"document:{file_name}",
                            len(extracted_text),
                            len(summary),
                            0.0,
                            'groq_document'
                        )
                    except (OSError, sqlite3.Error) as save_error:
                        logger.error(f"Ошибка сохранения запроса в БД: {save_error}")

                    logger.info(f"Успешно обработан документ {file_name} пользователя {user_id}")

                else:
                    if processing_message_id:
                        await self.delete_message(chat_id, processing_message_id)
                    await self.send_message(
                        chat_id,
                        "❌ Ошибка при создании резюме документа!\n\n"
                        "Попробуйте позже или обратитесь к администратору."
                    )

            except (sqlite3.Error, ValueError) as e:
                logger.error(f"Ошибка при обработке документа: {e}")
                if processing_message_id:
                    await self.delete_message(chat_id, processing_message_id)
                await self.send_message(
                    chat_id,
                    "❌ Произошла ошибка при обработке документа!\n\n"
                    "Пожалуйста, попробуйте позже."
                )

        except Exception as e:
            logger.error(f"Общая ошибка при обработке документа: {e}")
            await self.send_message(
                chat_id,
                "❌ Произошла ошибка!\n\nПожалуйста, попробуйте позже."
            )

        finally:
            # Удаляем пользователя из списка обрабатываемых
            self.processing_users.discard(user_id)

    # ============ Вспомогательные методы ============

    async def get_file_info(self, file_id: str):
        """Получает информацию о файле от Telegram API"""
        try:
            url = f"{self.base_url}/getFile"
            params = {"file_id": file_id}

            async with self.session.get(url, params=params) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Ошибка получения информации о файле: {e}")
            return None

    def _detect_document_type(
        self,
        text: str,
        file_name: str = "",
        file_extension: str = "",
        metadata: dict = None
    ) -> str:
        """Определяет тип документа для адаптивной саммаризации"""
        # Книжные форматы имеют приоритет
        if file_extension.lower() in ['.epub', '.fb2']:
            return 'book'

        # Проверяем метаданные из EPUB/FB2
        if metadata and ('author' in metadata or 'title' in metadata):
            # Если есть метаданные автора/названия - скорее всего книга
            return 'book'

        # Для PDF проверяем длину - книги обычно длиннее
        if file_extension.lower() == '.pdf' and len(text) > 50000:
            # Дополнительная проверка на характерные признаки книги
            lower_text = text[:5000].lower()
            book_indicators = [
                'глава', 'chapter', 'содержание', 'table of contents',
                'предисловие', 'preface', 'введение', 'introduction',
                'часть', 'part', 'эпилог', 'epilogue'
            ]
            if any(indicator in lower_text for indicator in book_indicators):
                return 'book'

        # Презентации
        if file_extension.lower() == '.pptx':
            return 'presentation'

        # По умолчанию - документ
        return 'document'

    async def summarize_book_content(
        self,
        text: str,
        metadata: dict = None,
        compression_ratio: float = 0.3
    ) -> str:
        """Специализированная саммаризация для книг с чанкингом"""
        try:
            if not self.groq_client:
                return "❌ Groq API недоступен"

            # Извлекаем метаданные если есть
            book_title = metadata.get('title', 'Книга') if metadata else 'Книга'
            book_author = (
                metadata.get('author', 'Неизвестный автор')
                if metadata
                else 'Неизвестный автор'
            )

            original_length = len(text)
            logger.info(
                f"📚 Начинаю саммаризацию книги: {book_title}, "
                f"длина: {original_length} символов"
            )

            # Для очень длинных книг применяем чанкинг
            if original_length > 30000:
                logger.info(
                    f"📚 Книга длинная ({original_length} символов), "
                    f"применяю чанк-саммаризацию"
                )

                # Разбиваем на чанки по ~15000 символов
                chunk_size = 15000
                chunks = []
                for i in range(0, len(text), chunk_size):
                    chunk = text[i:i + chunk_size]
                    if len(chunk) > 1000:  # Пропускаем слишком короткие чанки
                        chunks.append(chunk)

                logger.info(f"📚 Разбито на {len(chunks)} чанков")

                # Саммаризируем каждый чанк отдельно
                chunk_summaries = []
                # Максимум 5 чанков чтобы не превысить лимиты API
                for idx, chunk in enumerate(chunks[:5]):
                    logger.info(
                        f"📚 Обработка чанка {idx + 1}/{min(len(chunks), 5)}"
                    )

                    chunk_prompt = f"""Создай краткое резюме этой части книги "{book_title}" (автор: {book_author}).
Выдели ключевые события, идеи и важную информацию. Ответ на том же языке, что и текст.

Формат (150-200 слов):
• **Ключевые моменты:** [2-3 пункта]
• **Важные детали:** [имена, факты, цифры если есть]

Часть книги:
{chunk}"""

                    @retry_on_failure(max_retries=2, delay=1.0, backoff=2.0)
                    def call_groq_for_chunk():
                        return self.groq_client.chat.completions.create(
                            messages=[{"role": "user", "content": chunk_prompt}],
                            model="llama-3.3-70b-versatile",
                            temperature=0.3,
                            max_tokens=300,
                            top_p=0.9
                        )

                    try:
                        response = call_groq_for_chunk()
                        if response.choices and response.choices[0].message:
                            chunk_summaries.append(
                                response.choices[0].message.content.strip()
                            )
                    except Exception as e:
                        logger.error(f"📚 Ошибка обработки чанка {idx + 1}: {e}")
                        continue

                # Объединяем резюме чанков в финальное резюме
                if chunk_summaries:
                    combined_summaries = "\n\n".join([
                        f"**Часть {i+1}:**\n{s}"
                        for i, s in enumerate(chunk_summaries)
                    ])

                    final_prompt = f"""На основе резюме отдельных частей книги "{book_title}" (автор: {book_author}), создай единое структурированное резюме всей книги.

Структура резюме (400-600 слов):
📖 **О книге:** [1-2 предложения - главная тема]
📚 **Сюжет/Содержание:** [Основная линия повествования или ключевые идеи - 3-5 пунктов]
👥 **Персонажи/Действующие лица:** [Если применимо - основные персонажи]
💡 **Ключевые идеи и темы:** [Главные мысли автора - 2-4 пункта]
🎯 **Выводы:** [Основное заключение - 1-2 пункта]

Резюме частей книги:
{combined_summaries}"""

                    @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
                    def call_groq_for_final():
                        return self.groq_client.chat.completions.create(
                            messages=[{"role": "user", "content": final_prompt}],
                            model="llama-3.3-70b-versatile",
                            temperature=0.3,
                            max_tokens=700,
                            top_p=0.9
                        )

                    response = call_groq_for_final()
                    if response.choices and response.choices[0].message:
                        return response.choices[0].message.content.strip()

            else:
                # Для книг средней длины - одна саммаризация
                logger.info("📚 Книга средней длины, одна саммаризация")
                max_chars = 25000  # Для книг увеличиваем лимит
                if len(text) > max_chars:
                    text = text[:max_chars] + "...\n[Текст обрезан для обработки]"

                book_prompt = f"""Проанализируй книгу и создай структурированное резюме на том же языке, что и текст.

📖 **Информация о книге:**
Название: {book_title}
Автор: {book_author}

📋 **Структура резюме (400-600 слов):**
• **О книге:** [1-2 предложения - главная тема или жанр]
• **Сюжет/Содержание:** [Основная линия повествования или ключевые идеи - 3-5 пунктов]
• **Персонажи:** [Если художественная литература - основные персонажи]
• **Ключевые идеи:** [Главные мысли, темы, концепции - 2-4 пункта]
• **Стиль и особенности:** [Отличительные черты книги]
• **Выводы:** [Основное заключение или мораль]

ВАЖНО:
- Сохраняй ключевые факты, имена, события
- Для нон-фикшн акцентируй идеи и аргументы
- Для художественной литературы - сюжет и персонажей
- Не добавляй спойлеры к концовке, если это художественное произведение

Текст книги:
{text}"""

                @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
                def call_groq_api():
                    return self.groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": book_prompt}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.3,
                        max_tokens=750,
                        top_p=0.9
                    )

                response = call_groq_api()
                if response.choices and response.choices[0].message:
                    return response.choices[0].message.content.strip()

            return "❌ Не удалось получить ответ от модели"

        except Exception as e:
            logger.error(f"📚 Ошибка при саммаризации книги: {e}")
            return f"❌ Ошибка при обработке книги: {str(e)[:100]}"

    async def summarize_file_content(
        self,
        text: str,
        file_name: str = "",
        file_type: str = "",
        compression_ratio: float = 0.3
    ) -> str:
        """Создает резюме содержимого файла через Groq API"""
        try:
            if not self.groq_client:
                return "❌ Groq API недоступен"

            # Ограничиваем длину текста
            max_chars = 15000  # Увеличиваем лимит для документов
            original_length = len(text)

            if len(text) > max_chars:
                text = text[:max_chars] + "...\n[Текст обрезан для обработки]"

            # Определяем длину резюме в зависимости от размера документа и уровня сжатия
            target_length = int(original_length * compression_ratio)

            if target_length < 200:  # Минимальная длина резюме
                summary_length = "100-200 слов"
                max_tokens = 250
            elif target_length < 800:  # Средняя длина
                summary_length = "200-500 слов"
                max_tokens = 550
            else:  # Длинное резюме
                summary_length = "400-800 слов"
                max_tokens = 850

            # Определяем тип документа для лучшего промпта
            file_type_desc = {
                '.pdf': 'PDF документа',
                '.docx': 'Word документа',
                '.doc': 'Word документа',
                '.txt': 'текстового файла',
                '.pptx': 'презентации PowerPoint'
            }.get(file_type, 'документа')

            prompt = f"""Ты - эксперт по анализу документов. Создай подробное структурированное резюме {file_type_desc} на том же языке, что и исходный текст.

📋 **Требования к резюме:**
- Длина: {summary_length} (сжатие {compression_ratio:.0%})
- Структурированный формат с заголовками
- Обязательно извлекай КЛЮЧЕВЫЕ ФАКТЫ: имена, даты, цифры, события, решения
- Если документ на русском - отвечай на русском языке

📝 **Формат резюме:**

**Основное содержание:**
• Ключевые темы и идеи документа (2-3 пункта)

**Ключевые факты:**
• Важные данные: цифры, статистика, даты, имена, места
• Конкретные решения, выводы, рекомендации
• Упоминаемые источники, ссылки, документы (если есть)

**Детали и контекст:**
• Дополнительная важная информация
• Методология или процессы (если применимо)

**Выводы:**
• Основные заключения и их практическое значение

ВАЖНО:
- Сохраняй все точные цифры, даты, имена собственные
- Приоритет - извлечению фактической информации
- Избегай общих фраз, фокусируйся на конкретике

Начни ответ сразу с резюме, без вступлений.

Содержимое документа:
{text}"""

            @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
            def call_groq_api():
                return self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.3,
                    max_tokens=max_tokens,
                    top_p=0.9,
                    stream=False
                )

            response = call_groq_api()

            if response.choices and response.choices[0].message:
                summary = response.choices[0].message.content
                if summary:
                    return summary.strip()
            return "❌ Не удалось получить ответ от модели"

        except Exception as e:
            logger.error(f"Ошибка при суммаризации файла: {e}")
            return f"❌ Ошибка при обработке: {str(e)[:100]}"

    def check_user_rate_limit(self, user_id: int) -> bool:
        """Проверка лимита запросов пользователя (10 запросов в минуту)"""
        now = time.time()
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []

        # Удаляем запросы старше 1 минуты
        self.user_requests[user_id] = [
            req_time
            for req_time in self.user_requests[user_id]
            if now - req_time < 60
        ]

        # Проверяем лимит (10 запросов в минуту)
        if len(self.user_requests[user_id]) >= 10:
            return False

        self.user_requests[user_id].append(now)
        return True

    async def get_user_compression_level(self, user_id: int) -> float:
        """Получение уровня сжатия пользователя из базы данных"""
        try:
            settings = await self._run_in_executor(self.db.get_user_settings, user_id)
            compression_level = settings.get("compression_level", 30)
            return compression_level / 100.0  # Конвертируем процент в decimal
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Ошибка получения настроек пользователя {user_id}: {e}")
            return 0.3  # Возвращаем 30% по умолчанию

    async def _run_in_executor(self, func, *args):
        """Запуск синхронной функции в executor"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.db_executor, func, *args)

    async def delete_message(self, chat_id: int, message_id: int):
        """Удаление сообщения"""
        try:
            url = f"{self.base_url}/deleteMessage"
            data = {"chat_id": chat_id, "message_id": message_id}

            async with self.session.post(url, json=data) as response:
                result = await response.json()
                return result.get("ok", False)
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
            return False
