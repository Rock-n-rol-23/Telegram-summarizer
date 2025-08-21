# Telegram Text Summarization Bot

## Overview
This project is a Telegram bot that provides intelligent text summarization services using AI. It leverages the Groq API with Llama 3.3 70B as the primary summarization engine, with audio transcription via Groq Whisper large v3. The bot supports both Russian and English languages and offers comprehensive summarization for text, web pages, various document types (DOC, DOCX, PDF, TXT), YouTube videos, and audio/voice messages. The project's vision is to offer a robust, always-on summarization tool accessible directly through Telegram with special emphasis on audio processing capabilities.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture
The application follows a modular Python architecture with clear separation of concerns, designed for 24/7 operation and scalability.

### Design Principles
- **Modularity**: Clear separation of layers (Bot, AI Service, Data, Configuration).
- **Redundancy**: Dual AI backend (Groq API and local Hugging Face) for high availability.
- **Simplicity**: SQLite for local data persistence, simplified text-only user interface.
- **Scalability**: Rate limiting, text limits, and efficient resource management for handling large volumes.
- **Robustness**: Comprehensive error handling, input validation, and graceful shutdown.

### Key Components & Features
- **Bot Layer**: Handles Telegram interactions, command processing, and message routing using `python-telegram-bot`.
- **AI Service Layer**: Performs text summarization.
    - **Primary Backend**: Groq API (Llama 3.3 70B Versatile).
    - **Smart Summarization**: Advanced AI analysis with content type detection, key insight extraction, and structured output formatting.
    - **Fallback Backend**: Local Hugging Face Transformers model (GPT-2 based) for API unavailability.
- **Data Layer**: Manages data persistence using SQLite (or Railway PostgreSQL for production). Stores user settings, request history, usage statistics, and detailed change logs.
- **Configuration Layer**: Centralized configuration management using environment variables.
- **Text Summarization**: Core functionality for arbitrary text input with both standard and smart modes.
- **Smart Analysis Features**: 
    - **Content Type Detection**: Automatically identifies meeting notes, lectures, news, interviews, presentations, discussions, instructions, and reviews.
    - **Entity Extraction**: Finds and highlights dates, numbers, names, actions, and decisions.
    - **Key Insights Only**: Focused output with only critical information, facts, and conclusions.
    - **Compression-Aware Analysis**: Adjusts insight count based on compression level (10%=2 insights, 30%=3 insights, 50%=4 insights).
- **Web Page Summarization**: Automatically detects URLs, extracts content using BeautifulSoup with intelligent content selectors, and summarizes. Supports up to 3 URLs per message with domain filtering and Cloudflare protection detection.
- **Document Summarization**: Supports uploading and summarizing PDF, DOCX, DOC, and TXT files (up to 20MB). Uses libraries like PyPDF2, pdfplumber, python-docx, mammoth, and chardet for text extraction.
- **YouTube Video Summarization**: Detects YouTube URLs, extracts transcripts using `yt-dlp`, and summarizes video content. Supports videos up to 2 hours.
- **Audio Processing & Summarization**: Complete audio file support (MP3, WAV, M4A, OGG, FLAC, AAC, OPUS) with automatic speech recognition and intelligent summarization.
- **Text Processing**: Robust handling of various text inputs, including Unicode, emoji, and varied formatting (whitespace, indents), with appropriate text normalization and validation.
- **User Interface**: Interactive button-based interface with comprehensive inline keyboards and reply keyboards. Features intuitive menu navigation, real-time setting updates, and multilingual support (Russian/English). Traditional slash commands remain available for compatibility.
- **Deployment**: Supports multiple deployment modes, including Cloud Run (HTTP server + Telegram bot) and background worker (Telegram bot only), with automatic environment detection.

### Core Architectural Decisions
- **Dual AI Backend**: Ensures continuous summarization capability even if one API is down or rate-limited.
- **SQLite/PostgreSQL for Data**: SQLite for simplicity in local deployments, with PostgreSQL option for robust production persistence and detailed logging.
- **Modular Python**: Promotes maintainability and scalability.
- **Simplified UI**: Focuses on core functionality without complex menus, ensuring ease of use.
- **Comprehensive Input Handling**: Designed to process diverse input types (raw text, URLs, documents, YouTube links) robustly.
- **Comprehensive Audio Support**: Bot processes all types of audio content including voice messages, audio files, video notes (круглые видео), and audio documents. Unified extraction system supports both direct and forwarded messages with detailed progress tracking.
- **Advanced Web Scraping**: Enhanced webpage content extraction with Cloudflare protection detection, intelligent content selectors, and improved error messages for blocked or problematic sites.

### Audio Processing Enhancements (2025-08-19)
- **Unified Audio Descriptor System**: New `utils/tg_audio.py` module provides standardized extraction of audio metadata from all message types.
- **Enhanced Forwarded Message Support**: Improved handling of forwarded voice messages, audio files, video notes, and audio documents with automatic type detection.
- **Progressive User Feedback**: Step-by-step progress messages (downloading → converting → transcribing → summarizing) with detailed audio information display.
- **Robust Error Handling**: User-friendly error messages for common issues (file too large, no speech detected, unsupported format) with actionable recommendations.
- **Universal File Support**: Added support for video notes (круглые видео) and improved detection of audio documents by both MIME type and file extension.
- **Duration Formatting Fix**: Resolved "Unknown format code 'd' for object of type 'float'" error with safe duration formatting helpers.

### Web Content Extraction Enhancements (2025-08-19)
- **Multi-Stage Pipeline**: Implemented trafilatura → readability-lxml → bs4-heuristics extraction pipeline for robust web content processing.
- **Enhanced Content Quality**: Better text extraction with intelligent content selectors, noise removal, and metadata preservation.
- **SQLite Caching**: 72-hour TTL cache for repeated URL requests, significantly improving response times.
- **Link Extraction**: Automatic extraction and normalization of links from articles, displayed to users (up to 5 links).
- **Improved Error Handling**: User-friendly messages for blocked sites, timeouts, and content extraction failures.
- **Backward Compatibility**: New extractor with fallback to legacy method ensures no functionality breaks.

### Interactive UI System Enhancement (2025-08-21)
- **Button-Based Interface**: Complete replacement of slash commands with interactive inline keyboards for improved user experience.
- **Modular UI Architecture**: Created `ui_keyboards.py` for keyboard generation and `user_settings.py` for settings management.
- **Enhanced Database Schema**: Extended user settings table to support language preference, smart mode, and first interaction tracking.
- **Real-Time Settings Updates**: Instant visual feedback when changing compression levels, language, or smart mode through buttons.
- **Multilingual Support**: Dynamic keyboard localization between Russian and English with user preference persistence.
- **Context-Aware Navigation**: Smart menu system with back buttons and contextual help information.
- **Callback Query Integration**: Comprehensive callback handlers for all user interactions with proper error handling and logging.

### OCR and PPTX Integration (2025-08-19)
- **PDF OCR Support**: Added `content_extraction/pdf_ocr.py` with PyMuPDF + Tesseract OCR for scanned documents (ru+en languages).
- **PPTX Presentations**: New `content_extraction/pptx_extractor.py` extracts slides, speaker notes, and presentation structure.
- **Enhanced File Processor**: Extended support for `.pptx`, `.png`, `.jpg`, `.jpeg` formats with intelligent routing.
- **Progressive UI Feedback**: File-type specific progress messages (PDF→OCR, PPTX→slides, Image→OCR) with extraction statistics.
- **OCR Configuration**: Added `OCR_LANGS`, `PDF_OCR_DPI`, `MAX_PAGES_OCR` environment variables with safe defaults.
- **Comprehensive Testing**: Created test suites for PDF OCR and PPTX extraction with programmatic test file generation.
- **Production Ready**: Code prepared for full OCR functionality when Tesseract is available in production environment.

## External Dependencies

### APIs
- **Groq API**: Primary summarization service, utilizing the Llama 3.3 70B Versatile model.
- **Telegram Bot API**: For all bot interactions and message handling.

### Python Libraries
- `python-telegram-bot`: Framework for Telegram bot development.
- `groq`: Client for interacting with the Groq API.
- `transformers`: Hugging Face library for the local fallback summarization model.
- `torch`: PyTorch for local machine learning model inference.
- `python-dotenv`: For loading environment variables.
- `sqlite3`: Built-in Python library for SQLite database operations.
- `beautifulsoup4`: For web content parsing.
- `lxml`: High-performance XML and HTML parser (used by BeautifulSoup).
- `validators`: For URL validation.
- `python-readability`: For extracting main content from web pages.
- `aiofiles`: Asynchronous file operations (for document processing).
- `PyPDF2`: For PDF text extraction.
- `pdfplumber`: For more advanced PDF text and layout extraction.
- `python-docx`: For DOCX file parsing.
- `mammoth`: For DOC (Microsoft Word 97-2003) file conversion to HTML.
- `chardet`: For character encoding detection in text files.
- `yt-dlp`: For YouTube video metadata and transcript extraction.