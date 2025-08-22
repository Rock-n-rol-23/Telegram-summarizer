# Telegram Text Summarization Bot

## Overview
This project is a Telegram bot that provides intelligent text summarization services using advanced AI with guaranteed fact preservation. It leverages the Groq API with Llama 3.3 70B as the primary engine, implementing a sophisticated two-phase summarization system that prioritizes preserving critical information (numbers, dates, currencies, names) over compression ratio. The bot supports both Russian and English languages and offers comprehensive summarization for text, web pages (with table extraction), various document types (DOC, DOCX, PDF, TXT, PPTX), YouTube videos (up to 2 hours), and audio/voice messages. The project's vision is to offer a robust, quality-first summarization tool that never loses important facts, accessible directly through Telegram with enterprise-grade reliability.

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
- **Advanced Audio Processing**: Multi-stage audio pipeline with intelligent summarization, configurable verbosity, and structured output formatting.

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
- **User Interface**: Simplified, text-only interaction via Telegram commands (`/help`, `/stats`, `/smart`, `/10`, `/30`, `/50`). Supports both bullet-point summaries and structured smart analysis.
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

### OCR and PPTX Integration (2025-08-19)
- **PDF OCR Support**: Added `content_extraction/pdf_ocr.py` with PyMuPDF + Tesseract OCR for scanned documents (ru+en languages).
- **PPTX Presentations**: New `content_extraction/pptx_extractor.py` extracts slides, speaker notes, and presentation structure.
- **Enhanced File Processor**: Extended support for `.pptx`, `.png`, `.jpg`, `.jpeg` formats with intelligent routing.
- **Progressive UI Feedback**: File-type specific progress messages (PDF→OCR, PPTX→slides, Image→OCR) with extraction statistics.
- **OCR Configuration**: Added `OCR_LANGS`, `PDF_OCR_DPI`, `MAX_PAGES_OCR` environment variables with safe defaults.
- **Comprehensive Testing**: Created test suites for PDF OCR and PPTX extraction with programmatic test file generation.
- **Production Ready**: Code prepared for full OCR functionality when Tesseract is available in production environment.

### Enhanced Audio Summarization System (2025-08-21)
- **Advanced Transcription**: New `asr/transcribe.py` module with faster-whisper for CPU-based ASR, automatic fallback to smaller models on OOM.
- **Smart Text Analysis**: `summarizers/text_summarizer.py` provides multi-stage extractive summarization with sentence categorization (agreements, deadlines, actions, conditions).
- **Audio Pipeline**: `summarizers/audio_pipeline.py` combines transcription and smart summarization with progress tracking and performance monitoring.
- **User Settings System**: `bot/ui_settings.py` manages persistent user preferences for format (structured/bullets/paragraph) and verbosity (short/normal/detailed).
- **Intelligent Processing**: Automatic verbosity adjustment for short audio (<2min → detailed), key fact preservation, and structured output with sections.
- **Bot Integration**: Enhanced commands `/audio_settings` for user configuration, inline keyboards for settings management, and improved progress reporting.
- **Comprehensive Testing**: Test suite `tests/test_audio_summary.py` validates sentence extraction, categorization, formatting, and settings management.
- **Audio Processing Fixes (2025-08-21)**: Fixed filename handling for voice/forwarded messages, added robust extension fallback (.ogg default), added .opus support, and improved error handling for unsupported formats.

### Two-Phase Quality-First Summarization System (2025-08-22)
- **Fact Preservation Pipeline**: New `summarization/pipeline.py` implements two-phase approach: Phase A (JSON fact extraction), Phase B (text generation) with guaranteed preservation of numbers, dates, currencies, and names.
- **Advanced Quality Checks**: `quality/quality_checks.py` provides comprehensive validation including number preservation tracking, language detection, and quality scoring algorithms.
- **Enhanced Web Extraction**: `content_extraction/web_extractor.py` upgraded with table extraction to Markdown format, improved content selectors, and better error handling for protected sites.
- **YouTube 2-Hour Support**: Updated `youtube_processor.py` to support videos up to 2 hours (previously 1 hour), with enhanced transcript processing and timestamp preservation.
- **Lightweight Dependencies**: Created `simple_deps/` directory with fallback implementations for failed package installations (dateparser, lingua, natasha).
- **Comprehensive Test Suite**: New test files validate number preservation (`test_numbers_preserved.py`), web table extraction (`test_web_tables_extraction.py`), YouTube processing (`test_youtube_transcript.py`), and fallback scenarios (`test_fallback_no_groq.py`).
- **Integrated Summarizer**: `integrated_summarizer.py` provides unified interface with graceful degradation - advanced features when available, reliable fallback when not.
- **Production Ready**: All components successfully integrated and tested, bot running with 100% component availability and enhanced quality assurance.

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