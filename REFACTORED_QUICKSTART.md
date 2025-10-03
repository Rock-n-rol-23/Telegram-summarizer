# 🚀 Быстрый старт с рефакторенной версией

## Что это?

Полностью рефакторенная версия Telegram Summarizer Bot с чистой модульной архитектурой.

**Исходный код:** `simple_bot.py` (3236 строк) → 11 модулей (2832 строки)

---

## 📦 Структура

```
bot/
├── core/
│   ├── decorators.py       # Retry decorator
│   ├── router.py           # UpdateRouter - маршрутизация обновлений
│   └── bot.py              # RefactoredBot - главный класс
├── handlers/
│   ├── base.py             # BaseHandler - базовый класс
│   ├── commands.py         # CommandHandler - /start, /help, /stats
│   ├── text_handler.py     # TextHandler - тексты, YouTube, URL
│   ├── document_handler.py # DocumentHandler - PDF, DOCX, EPUB, FB2
│   ├── audio_handler.py    # AudioHandler - голосовые, аудио
│   └── callback_handler.py # CallbackHandler - inline кнопки
└── constants.py            # Константы (приветствие)

refactored_main.py          # Точка входа
```

---

## 🎯 Запуск

### 1. Убедитесь, что .env настроен

```bash
# Обязательные переменные:
TELEGRAM_BOT_TOKEN=your_bot_token
OPENROUTER_API_KEY=your_openrouter_key  # или GROQ_API_KEY

# Опционально:
GROQ_API_KEY=your_groq_key
DATABASE_URL=sqlite:///bot_database.db
```

### 2. Запустите рефакторенную версию

```bash
python3 -u refactored_main.py
```

**Вы увидите:**
```
============================================================
Запуск Telegram Companion (Refactored Version)
============================================================
Инициализация базы данных...
Инициализация state manager...
✅ OpenRouter клиент инициализирован
Инициализация процессоров...
Создание RefactoredBot...
Запуск RefactoredBot...
✅ Все handlers инициализированы
✅ Бот запущен: @your_bot_username
Запуск long polling...
```

---

## 🧪 Тестирование

### Проверьте основные команды:
- `/start` - приветствие
- `/help` - справка
- `/stats` - статистика
- `/10`, `/30`, `/50` - уровни сжатия

### Проверьте обработку контента:
- Отправьте **текст** (> 50 символов) - получите саммари
- Отправьте **YouTube ссылку** - получите резюме видео
- Отправьте **документ** (PDF/DOCX/EPUB) - получите структурированное саммари
- Отправьте **голосовое сообщение** - получите транскрипт + саммари
- Отправьте **обычную ссылку** - получите резюме статьи

### Проверьте inline кнопки:
- Команды сжатия показывают inline клавиатуры
- Кнопки должны корректно обновлять настройки

---

## ✅ Преимущества новой архитектуры

| Аспект | Старая версия | Новая версия |
|--------|---------------|--------------|
| **Структура** | 1 файл (3236 строк) | 11 модулей (~260 строк каждый) |
| **Читаемость** | Сложно ориентироваться | Четкое разделение по функциям |
| **Тестирование** | Трудно изолировать логику | Каждый handler тестируется отдельно |
| **Поддержка** | Изменения затрагивают весь файл | Изменения локализованы в модулях |
| **Расширяемость** | Добавление фич усложняет код | Новые handlers добавляются легко |

---

## 🔄 Сравнение с оригинальной версией

Обе версии **идентичны** по функциональности:

```bash
# Старая версия (продолжает работать)
python3 -u main_entrypoint.py

# Новая версия (рефакторенная)
python3 -u refactored_main.py
```

**Можно запускать параллельно на разных Telegram ботах для A/B тестирования.**

---

## 🚨 Важно

- ✅ **simple_bot.py НЕ ТРОНУТ** - старая версия продолжает работать
- ✅ **База данных ОБЩАЯ** - оба бота используют одну БД
- ✅ **Процессоры ОБЩИЕ** - file_processor, audio_processor, youtube_processor
- ⚠️ **Не запускайте оба бота с одним токеном** - Telegram API не позволит

---

## 🐛 Траблшутинг

### Ошибка: "No module named 'bot'"

```bash
# Убедитесь, что bot/__init__.py существует:
touch bot/__init__.py
touch bot/core/__init__.py
touch bot/handlers/__init__.py
touch bot/middleware/__init__.py
```

### Ошибка: "TELEGRAM_BOT_TOKEN не найден"

```bash
# Проверьте .env файл:
cat .env | grep TELEGRAM_BOT_TOKEN
```

### Ошибка: "Не инициализирован ни один LLM клиент"

```bash
# Добавьте хотя бы один ключ в .env:
OPENROUTER_API_KEY=sk-or-v1-...
# или
GROQ_API_KEY=gsk_...
```

---

## 📝 Следующие шаги

### После успешного тестирования:

1. **Замена на Railway:**
   ```bash
   # Обновить команду запуска в Railway:
   python3 -u refactored_main.py
   ```

2. **Полная замена локально:**
   ```bash
   mv simple_bot.py simple_bot.py.old
   mv refactored_main.py main.py
   # Обновить main_entrypoint.py для использования новой архитектуры
   ```

3. **Добавить тесты** (опционально):
   ```bash
   # Создать tests/ директорию
   mkdir tests
   # Добавить unit тесты для каждого handler
   ```

---

## 📚 Дополнительная информация

- **Полная документация рефакторинга:** [REFACTORING.md](REFACTORING.md)
- **Основной README:** [README.md](README.md)
- **OpenRouter setup:** [OPENROUTER_SETUP.md](OPENROUTER_SETUP.md)

---

**Создано:** 2025-10-03
**Статус:** ✅ Готов к использованию
