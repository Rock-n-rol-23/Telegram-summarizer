# Telegram Companion — бот-саммаризатор

Экономит время: превращает длинные тексты, веб-страницы, видео и **даже голосовые/аудио** в короткие понятные выжимки.  
🔥 Работает на **Llama 3.3 70B (Groq)** для саммари и **Whisper large v3 (Groq)** для распознавания речи.

---

## 🚀 Возможности

- **Тексты и пересланные сообщения** — выделение сути и ключевых пунктов.
- **Статьи по ссылке** — извлекаем контент с веб-страницы и суммируем.
- **YouTube (до ~2 часов)** — саммари по субтитрам и описанию.
- **Документы**: PDF, DOCX, DOC, TXT *(до ~20 MB)* — структурированное резюме.
- **Аудио и голосовые** — авто-транскрипция + краткое саммари.
  - Поддерживаемые форматы: MP3, WAV, M4A, OGG, FLAC, AAC, OPUS
  - Лимиты по умолчанию: до **50 MB** и ориентир **~1 час** аудио
- **Гибкая длина саммари**: команды `/10`, `/30`, `/50` для 10% / 30% / 50%.
- **Статистика**: `/stats`
- **Справка**: `/help`
- **Языки**: русский 🇷🇺 и английский 🇬🇧

---

## ⚙️ Требования

- **Python 3.10+**
- **FFmpeg** (скачивается автоматически через `imageio-ffmpeg`)
- Аккаунт в **Groq** и ключ API для:
  - `llama-3.3-70b-versatile` (саммаризация)
  - `whisper-large-v3` (транскрипция аудио)

---

## 🔑 Переменные окружения

Файл: `.env` (пример уже есть в репозитории)

```dotenv
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
GROQ_API_KEY=your_groq_api_key_here
DATABASE_URL=postgresql://...  # или sqlite:///bot_database.db (по умолчанию)
LOG_LEVEL=INFO
MAX_REQUESTS_PER_MINUTE=10
MAX_TEXT_LENGTH=10000
MIN_TEXT_LENGTH=50
```

База данных: автоматически работает с PostgreSQL (например, Railway через DATABASE_URL) или SQLite (файл bot_database.db) — см. database.py.

---

## 🧪 Быстрый старт (локально)

1. Склонируйте репозиторий и перейдите в папку TelegramCompanion/.

2. Создайте `.env` (или отредактируйте существующий) и заполните переменные.

3. Установите зависимости (минимальный набор):
```bash
pip install -U groq python-dotenv aiohttp aiofiles pydub imageio-ffmpeg validators beautifulsoup4 yt-dlp pdfplumber PyPDF2 python-docx chardet flask
```

4. Запустите:
```bash
python3 -u main_entrypoint.py
```

5. Отправьте боту `/start` в Telegram.

6. HTTP-проверка работоспособности (локально): `GET /healthz` вернёт статус сервиса.

---

## 🔧 Настройка YouTube обработки (обязательно!)

⚠️ **Для стабильной работы с YouTube видео необходимо настроить cookies браузера**

### Шаг 1: Установка расширения
Установите расширение **Get cookies.txt** для вашего браузера:
- **Chrome**: [Get cookies.txt](https://chrome.google.com/webstore/detail/get-cookiestxt/njabckikapfpffapmjgojcnbfjonfjfg)
- **Firefox**: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

### Шаг 2: Экспорт cookies
1. Откройте [youtube.com](https://youtube.com) в браузере
2. Войдите в ваш YouTube/Google аккаунт
3. Нажмите на иконку расширения **Get cookies.txt**
4. Выберите опцию "Export" или "Download"
5. Сохраните файл как `cookies.txt`

### Шаг 3: Размещение файла
Поместите файл `cookies.txt` в корневую папку проекта (рядом с `main.py`).

**Структура должна быть такой:**
```
project_root/
├── cookies.txt          ← Ваш файл с cookies
├── main.py
├── youtube_processor.py
└── ...
```

### ⚠️ Важные примечания
- **Только настоящие cookies**: Тестовые или поддельные cookies не работают - YouTube блокирует такие запросы
- **Обновление cookies**: Если бот выдает ошибки "429 Too Many Requests" или "Cookies истекли", повторите экспорт из браузера
- **Войдите в YouTube**: Обязательно войдите в ваш YouTube/Google аккаунт перед экспортом cookies
- **Безопасность**: Файл `cookies.txt` содержит данные авторизации - не передавайте его третьим лицам
- **Без cookies**: YouTube ссылки будут возвращать ошибку "❌ Необходимо добавить cookies для обработки YouTube ссылок"

---

## 🧭 Как пользоваться

- **Текст** → пришлите сообщение — получите выжимку.
- **Ссылка на статью** → вернём краткое резюме.
- **YouTube-ссылка** → краткое содержание по субтитрам.
- **Документ (PDF/DOCX/DOC/TXT)** → структурированное саммари.
- **Голосовое/аудио** → транскрипт + краткое саммари.

### Команды

- `/10`, `/30`, `/50` — уровень сжатия 10% / 30% / 50%
- `/help` — подробная справка
- `/stats` — ваша статистика

---

## 🛡️ Лимиты по умолчанию

- **Текст**: до 10 000 символов
- **Аудио**: до 50 MB, ориентир ~1 час
- **Документы**: до ~20 MB
- **YouTube**: рекомендовано до ~2 часов
- **Рейт-лимит**: 10 запросов/мин на пользователя

(Параметры задаются через конфиг/ENV, см. config.py.)

---

## 🧱 Архитектура (файлы)

- `simple_bot.py` — основной бот, Telegram Bot API, парсинг апдейтов.
- `smart_summarizer.py` — логика саммаризации (Llama 3.3 70B).
- `audio_processor.py` — загрузка/нормализация/чтение аудио + Whisper.
- `file_processor.py` — парсинг документов (PDF/DOCX/DOC/TXT).
- `youtube_processor.py` — извлечение субтитров/метаданных (yt-dlp).
- `database.py` — PostgreSQL/SQLite, статистика и логирование событий.
- `main_entrypoint.py` — запуск бота и HTTP-health эндпоинтов.

---

## ❓ Траблшутинг

- **Аудио не обрабатывается**: проверьте GROQ_API_KEY и доступность ffmpeg (автоматически подтягивается через imageio-ffmpeg).
- **Пустой результат**: убедитесь, что файл читаемый (PDF не картинка без текста).
- **Лимиты**: снизьте длительность/размер или разбейте на части.

---

## 🔥 Технологии

- **Groq Llama 3.3 70B** — `llama-3.3-70b-versatile`
- **Groq Whisper large v3** — `whisper-large-v3`
- Telegram Bot API (long polling), aiohttp, yt-dlp, pdfplumber, PyPDF2, beautifulsoup4, pydub, imageio-ffmpeg.