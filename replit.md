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
- **Web Page Summarization**: Automatically detects URLs, extracts content using BeautifulSoup and `python-readability`, and summarizes. Supports up to 3 URLs per message and includes domain filtering.
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
- **Forwarded Media Support**: Bot processes forwarded audio/voice messages and audio documents without requiring file downloads to user's device, maintaining backward compatibility with non-audio forwarded media handling.

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