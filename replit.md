# Telegram Text Summarization Bot

## Overview
This project is a Telegram bot designed to provide intelligent text summarization services with guaranteed fact preservation. It utilizes advanced AI, primarily the Groq API with Llama 3.3 70B, implementing a sophisticated two-phase summarization system that prioritizes critical information (numbers, dates, currencies, names). The bot supports both Russian and English languages and offers comprehensive summarization for various content types: text, web pages (with table extraction), documents (DOC, DOCX, PDF, TXT, PPTX), YouTube videos (up to 2 hours), and audio/voice messages. The core vision is to deliver a robust, quality-first summarization tool that ensures no important facts are lost, accessible directly via Telegram with enterprise-grade reliability and scalability.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture
The application follows a modular Python architecture with clear separation of concerns, designed for 24/7 operation and scalability. Key design principles include modularity, redundancy (dual AI backend), simplicity, scalability, and robustness.

### Core Architectural Decisions
- **Dual AI Backend**: Ensures continuous summarization capability with Groq API (Llama 3.3 70B Versatile) as primary and a local Hugging Face model as fallback.
- **Fact Preservation Pipeline**: Implements a two-phase summarization system (JSON fact extraction then text generation) to guarantee preservation of numbers, dates, currencies, and names.
- **Data Persistence**: Uses SQLite for local data persistence with an option for PostgreSQL in production, storing user settings, request history, and usage statistics.
- **Modular Python Design**: Promotes maintainability, scalability, and clear separation of layers (Bot, AI Service, Data, Configuration).
- **Simplified UI/UX**: Focuses on a text-only interface via Telegram commands (`/help`, `/stats`, `/smart`, `/10`, `/30`, `/50`) for ease of use.
- **Comprehensive Input Handling**: Robustly processes diverse input types including raw text, URLs, documents (PDF, DOCX, DOC, TXT, PPTX), YouTube links, and various audio formats.
- **Advanced Audio Processing**: Multi-stage audio pipeline supporting all audio content types (voice messages, audio files, video notes) with intelligent summarization, progress tracking, and configurable verbosity. Includes advanced transcription via `faster-whisper`.
- **Enhanced Web Scraping**: Utilizes a multi-stage pipeline (trafilatura → readability-lxml → bs4-heuristics) for robust web content extraction, including table extraction, intelligent content selectors, and Cloudflare protection detection.
- **OCR Integration**: Supports OCR for scanned PDF documents and image files (PNG, JPG) using PyMuPDF + Tesseract.
- **Production Readiness**: Incorporates features like network security (SSRF protection, `aiohttp`), database enhancements (PostgreSQL connection pooling, SQLite WAL mode), message chunking, centralized configuration, structured logging, advanced rate limiting, and comprehensive testing.

### Key Features
- **Smart Summarization**: Advanced AI analysis with content type detection (meeting notes, lectures, news, etc.), entity extraction (dates, numbers, names), and focus on key insights.
- **Web Page Summarization**: Automatic URL detection, content extraction, and summarization, supporting up to 3 URLs per message.
- **Document Summarization**: Handles PDF, DOCX, DOC, TXT, and PPTX files (up to 20MB) with text and structural element extraction.
- **YouTube Video Summarization**: Extracts and summarizes transcripts for videos up to 2 hours.
- **User Settings**: Persistent user preferences for summary format (structured/bullets/paragraph) and verbosity (short/normal/detailed).

## External Dependencies

### APIs
- **Groq API**: Primary AI summarization service.
- **Telegram Bot API**: For all bot interactions.

### Python Libraries
- `python-telegram-bot`: Telegram bot framework.
- `groq`: Groq API client.
- `transformers`: Hugging Face library for local fallback model.
- `torch`: PyTorch for local model inference.
- `python-dotenv`: Environment variable management.
- `beautifulsoup4`, `lxml`, `validators`, `python-readability`: For web content parsing and validation.
- `aiofiles`: Asynchronous file operations.
- `PyPDF2`, `pdfplumber`: PDF text extraction.
- `python-docx`, `mammoth`: DOCX and DOC file parsing.
- `chardet`: Character encoding detection.
- `yt-dlp`: YouTube video and transcript extraction.
- `faster-whisper`: CPU-based ASR for audio transcription.
- `aiolimiter`: For rate limiting.
- `PyMuPDF`, `Pillow`, `pytesseract`: For PDF OCR and image processing.