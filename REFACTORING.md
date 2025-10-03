# Рефакторинг Telegram Summarizer Bot

## 📋 Текущее состояние

### ✅ Выполнено

#### 1. Базовая архитектура
- ✅ Создана структура директорий `bot/core`, `bot/handlers`, `bot/middleware`
- ✅ Вынесен декоратор `retry_on_failure` → `bot/core/decorators.py`
- ✅ Вынесены константы (WELCOME_MESSAGE_HTML) → `bot/constants.py`
- ✅ Создан базовый класс `BaseHandler` для всех обработчиков

#### 2. Обработчики команд (/start, /help, /stats и др.)
- ✅ Создан `bot/handlers/commands.py` с классом `CommandHandler`
- ✅ Все методы команд вынесены и адаптированы под новую архитектуру
- ✅ Включены вспомогательные методы (send_text_request, get_compression_keyboard и др.)

#### 3. Извлечен код обработчиков
Агенты успешно извлекли полный код следующих обработчиков из `simple_bot.py`:
- ✅ **Текстовый обработчик** (handle_text_message, handle_custom_summarize_text и др.)
- ✅ **Обработчик документов** (handle_document_message, с поддержкой PDF, DOCX, EPUB, FB2 и др.)
- ✅ **Обработчик аудио** (handle_audio_message, с enhanced audio pipeline)

---

## 🎯 Архитектура после рефакторинга

```
bot/
├── __init__.py
├── constants.py                  # ✅ Константы (WELCOME_MESSAGE_HTML)
├── core/
│   ├── __init__.py              # ✅
│   ├── decorators.py            # ✅ retry_on_failure
│   ├── bot.py                   # 🔜 Главный класс бота
│   └── router.py                # 🔜 Маршрутизация обновлений
├── handlers/
│   ├── __init__.py              # ✅
│   ├── base.py                  # ✅ BaseHandler
│   ├── commands.py              # ✅ CommandHandler
│   ├── text_handler.py          # 🔜 TextHandler
│   ├── document_handler.py      # 🔜 DocumentHandler
│   ├── audio_handler.py         # 🔜 AudioHandler
│   ├── youtube_handler.py       # 🔜 YouTubeHandler
│   ├── url_handler.py           # 🔜 URLHandler
│   └── callback_handler.py      # 🔜 CallbackHandler
└── middleware/
    ├── __init__.py              # ✅
    ├── rate_limiter.py          # 🔜 Rate limiting
    └── metrics.py               # 🔜 Метрики и мониторинг
```

**Легенда:**
- ✅ = готово
- 🔜 = следующий шаг

---

## 📦 Основные компоненты

### BaseHandler
Базовый класс для всех обработчиков, предоставляющий:
- `send_message()` - отправка сообщений
- `send_chat_action()` - статус "печатает..."
- `edit_message_text()` - редактирование сообщений
- `get_user_id()`, `get_chat_id()` - извлечение ID из update

### CommandHandler
Обработчик команд:
- `/start` - приветствие
- `/help` - справка
- `/stats` - статистика
- `/smart` - переключение умного режима
- `/audio_settings` - настройки аудио
- Команды сжатия `/10`, `/30`, `/50`

---

## 🔄 Следующие шаги

### 1. Создать недостающие handlers (приоритет)
```bash
# Следующим будет создан:
bot/handlers/text_handler.py      # Обработка текстовых сообщений
bot/handlers/document_handler.py  # Обработка документов
bot/handlers/audio_handler.py     # Обработка аудио
```

### 2. Создать Router
```python
# bot/core/router.py
class UpdateRouter:
    def route(self, update: dict) -> Handler
    # Определяет какой handler использовать
```

### 3. Создать главный класс бота
```python
# bot/core/bot.py
class RefactoredBot:
    def __init__(self, ...):
        self.router = UpdateRouter()
        self.command_handler = CommandHandler(...)
        self.text_handler = TextHandler(...)
        # и т.д.
```

### 4. Тестирование
- Создать тестовый скрипт для проверки новой версии
- Убедиться, что все команды работают
- Проверить обработку текста, документов, аудио
- Сравнить поведение со старой версией

---

## ⚠️ Важно

### Безопасность рефакторинга
1. **Старый код не трогаем**: `simple_bot.py` остается неизменным
2. **Параллельная разработка**: Новая версия создается отдельно
3. **Постепенная миграция**: После тестирования можно переключиться
4. **Railway deployment**: Текущая версия на Railway продолжит работать

### Что НЕ изменилось
- База данных (`database.py`)
- Процессоры (`file_processor.py`, `audio_processor.py`, `youtube_processor.py`)
- Суммаризаторы (`smart_summarizer.py`, `integrated_summarizer.py`)
- Утилиты (`utils/`, `bot/text_utils.py`, `bot/state_manager.py`)

---

## 📝 Извлеченный код обработчиков

### Зависимости text_handler.py
```python
# Основные методы
- handle_text_message
- handle_custom_summarize_text
- process_custom_summarization

# Вспомогательные методы
- summarize_text
- custom_summarize_text
- check_user_rate_limit
- get_user_compression_level
- _run_in_executor

# Используемые атрибуты
- self.processing_users (Set[int])
- self.user_requests (Dict[int, list])
- self.user_states (Dict[int, dict])
- self.user_settings (Dict[int, dict])
- self.user_messages_buffer (Dict[int, list])
- self.db (DatabaseManager)
- self.groq_client
- self.openrouter_client
```

### Зависимости document_handler.py
```python
# Основные методы
- handle_document_message

# Вспомогательные методы
- _detect_document_type
- summarize_book_content (с чанкингом для длинных книг)
- summarize_file_content
- get_file_info

# Используется
- self.file_processor (FileProcessor)
- Поддержка: PDF, DOCX, DOC, TXT, EPUB, FB2, PPTX, PNG, JPG
- OCR для изображений и сканов
```

### Зависимости audio_handler.py
```python
# Основные методы
- handle_audio_message

# Вспомогательные методы
- _get_file_url
- get_file_info

# Утилиты из utils/tg_audio.py
- extract_audio_descriptor
- get_audio_info_text
- format_duration
- format_file_size
- is_audio_document

# Используется
- self.audio_processor (AudioProcessor)
- self.smart_summarizer (SmartSummarizer)
- Поддержка: voice, audio, video_note, audio documents
```

---

## 🚀 План завершения рефакторинга

1. **Фаза 1** (текущая): Создание handlers
   - [x] CommandHandler
   - [ ] TextHandler
   - [ ] DocumentHandler
   - [ ] AudioHandler
   - [ ] YouTubeHandler
   - [ ] URLHandler
   - [ ] CallbackHandler

2. **Фаза 2**: Router и главный бот
   - [ ] UpdateRouter
   - [ ] RefactoredBot
   - [ ] Интеграция всех handlers

3. **Фаза 3**: Тестирование
   - [ ] Unit тесты для handlers
   - [ ] Интеграционное тестирование
   - [ ] Сравнение с оригинальной версией

4. **Фаза 4**: Деплой
   - [ ] Обновить main_entrypoint.py
   - [ ] Протестировать на Railway
   - [ ] Полная замена старой версии

---

## 📊 Статистика

- **Исходный файл**: `simple_bot.py` - **3236 строк**
- **Цель**: Разбить на ~8-10 модулей по 200-400 строк
- **Текущий прогресс**: ~15% (базовая структура + CommandHandler)

---

## 🔗 Связанные файлы

- `simple_bot.py` - оригинальный код (не трогаем)
- `bot/` - новая архитектура
- Все процессоры и утилиты остаются без изменений

---

**Последнее обновление**: 2025-10-03
**Статус**: В процессе рефакторинга ✨
