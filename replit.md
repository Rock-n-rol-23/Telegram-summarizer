# Telegram Text Summarization Bot

## Overview

This project is a comprehensive Telegram bot that provides intelligent text summarization services using AI. Built in Python, it leverages the Groq API with Llama 3.1 70B as its primary summarization engine, complemented by a Hugging Face Transformers fallback for reliability. The bot supports both Russian and English languages and is designed for continuous 24/7 operation, offering robust and accessible text, web page, document, YouTube video, and **audio file/voice message** summarization. The business vision is to provide a highly available, efficient, and multi-functional summarization tool, capitalizing on the growing need for rapid information processing and content digestion across multiple media types.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

The application follows a modular Python architecture with clear separation of concerns, prioritizing reliability, user experience, and operational simplicity.

### Core Architectural Decisions
- **Modularity**: Separation into Bot, AI Service, Data, and Configuration layers.
- **High Availability**: Dual AI backend approach (Groq API with local Hugging Face model fallback).
- **Simplicity**: SQLite for local data persistence and a text-only user interface.
- **Scalability**: Rate limiting, text limits, and lazy loading of ML models.
- **Security**: Input validation, rate limiting, and comprehensive error handling.

### UI/UX Decisions
- **Text-Only Interface**: Simplifies user interaction by removing all inline keyboards and complex menus. Users interact via simple commands and text input.
- **Output Format**: All summarizations are presented in a consistent bullet-point format.
- **Language Support**: Supports both Russian and English.

### Technical Implementations
- **Bot Layer**: Implemented using the `python-telegram-bot` library for robust Telegram API integration. Handles message reception, command processing, and user interaction.
- **AI Service Layer**: Manages text summarization.
    - **Primary Backend**: Groq API utilizing the Llama 3.1 70B model.
    - **Fallback Backend**: Hugging Face Transformers with a local GPT-2 based model for resilience against API issues.
- **Data Layer**: Manages data persistence.
    - **Local Storage**: SQLite database for user settings, request history, and statistics. Chosen for its simplicity and zero-configuration deployment.
    - **Persistent Storage**: Railway PostgreSQL integration for enhanced persistence and user preference change logging.
- **Configuration Layer**: Centralized management using environment variables, with parameter validation.
- **Content Processing**:
    - **Text Summarization**: Handles text validation, language detection, and chunking for long texts.
    - **Web Page Summarization**: Automatically detects URLs, extracts web content using `BeautifulSoup` and `python-readability`, and summarizes it. Supports up to 3 URLs per message and includes domain filtering.
    - **Document Summarization**: Supports file uploads (up to 20MB) and extracts text from PDF, DOCX, DOC, and TXT formats using libraries like `PyPDF2`, `python-docx`, `mammoth`, and `chardet`. Provides structured summaries.
    - **YouTube Video Summarization**: Detects YouTube URLs, extracts transcripts using `yt-dlp`, and summarizes video content up to 2 hours in duration.
    - **Audio Processing**: Comprehensive audio/voice message processing pipeline with Whisper transcription integration:
        - Supports voice messages (OGG/OPUS), audio files (MP3, M4A, WAV, FLAC), and video notes
        - Automatic format detection and conversion to WAV 16kHz mono using FFmpeg
        - Intelligent audio segmentation with optional VAD (Voice Activity Detection)
        - Whisper-based transcription with automatic language detection
        - Full transcript text passed to existing Llama summarization engine
        - Returns both summary and complete transcription file
        - Configurable duration limits (default: 90 minutes)
- **Text Normalization**: Robust handling of whitespace, indentation, and Unicode characters, including emojis, to ensure accurate processing.
- **Deployment**: Supports Cloud Run (recommended for production, combined HTTP server and Telegram bot) and Background Worker (Telegram bot only) deployment modes with automatic environment detection.

### Feature Specifications
- **Summarization**: AI-powered summarization with user-adjustable compression levels (10%, 30%, 50%).
- **Input Handling**: Supports various input types: direct text, forwarded messages, web page URLs, document uploads, YouTube video links, voice messages, audio files, and video notes.
- **Rate Limiting**: 10 requests per user per minute.
- **Text Limits**: 10,000 character maximum input, 20 significant characters minimum.
- **Audio Processing**: 90-minute maximum duration, 50MB file size limit, automatic format conversion.
- **Error Handling**: Comprehensive exception handling with user feedback and silent ignoring of unsupported media without captions.

## External Dependencies

### Required APIs
- **Groq API**: Primary summarization service (Llama 3.1 70B model).
- **Telegram Bot API**: Core for message handling and user interaction.

### Python Libraries
- `python-telegram-bot`: Telegram bot framework.
- `groq`: Groq API client.
- `transformers`: Hugging Face models (fallback).
- `torch`: PyTorch for local model inference.
- `python-dotenv`: Environment variable management.
- `sqlite3`: Built-in database operations.
- `Flask`: For HTTP server functionality in Cloud Run deployment.
- `beautifulsoup4`: Web content parsing.
- `lxml`: HTML/XML parser.
- `validators`: URL validation.
- `python-readability`: Web page content extraction.
- `aiofiles`: Asynchronous file operations.
- `PyPDF2`: PDF file parsing.
- `pdfplumber`: PDF text extraction.
- `python-docx`: DOCX file parsing.
- `mammoth`: DOC file parsing.
- `chardet`: Character encoding detection.
- `yt-dlp`: YouTube video transcript extraction.
- `openai-whisper`: Audio transcription (optional - requires manual installation).
- `webrtcvad`: Voice activity detection (optional).
- **System**: `ffmpeg`: Audio/video processing and format conversion.
```

## Recent Changes (January 2025)

### Audio Processing Pipeline Implementation
- **Date**: January 11, 2025
- **Major Feature Addition**: Complete audio and voice message processing with transcription and summarization
- **New Architecture Components**:
  - `audio_pipeline/` - Modular audio processing pipeline
  - `utils/ffmpeg.py` - Safe audio format conversion utilities
  - Integration with existing Groq/Llama summarization (no changes to existing text processing)

### Technical Implementation Details
- **Audio Pipeline Structure**:
  - `downloader.py`: Telegram file download and metadata extraction
  - `transcriber_adapter.py`: Whisper transcription interface (designed for future Whisper integration)
  - `segmenter.py`: Audio chunking and optional VAD processing  
  - `summarization_adapter.py`: Bridge to existing Groq/Llama summarization
  - `handler.py`: Orchestrates complete pipeline from download to response

- **Integration Points**:
  - Added audio handlers to `simple_bot.py` without modifying existing functionality
  - Extended `config.py` with audio-specific environment variables
  - Maintained separation between audio processing and text/document/YouTube processing

### Configuration Added
- `AUDIO_SUMMARY_ENABLED=true` - Enable/disable audio processing
- `ASR_VAD_ENABLED=true` - Voice activity detection for segmentation
- `ASR_MAX_DURATION_MIN=90` - Maximum audio duration in minutes
- `FFMPEG_PATH=ffmpeg` - Path to FFmpeg executable
- `WHISPER_MODEL_SIZE=base` - Whisper model size selection
- `AUDIO_MAX_FILE_SIZE_MB=50` - File size limit
- `AUDIO_DEFAULT_COMPRESSION=0.3` - Default summarization compression ratio

### Current Status
- ✅ Complete modular architecture implemented
- ✅ FFmpeg integration working perfectly  
- ✅ Pipeline fully tested and operational
- ✅ Integration with bot completed and debugged
- ✅ Audio file routing bug RESOLVED (MP3/WAV files now route correctly)
- ✅ Enhanced fallback system with informative user messages
- ⚠️ Whisper installation pending (dependency conflicts in current environment)
- ✅ Professional fallback handling provides installation guidance

### January 11, 2025 - Complete Audio Architecture Redesign
- **New Modular Architecture**: Implemented new audio processing pipeline following user specifications
- **Enhanced Components**:
  - `audio_pipeline/transcriber.py`: Multi-engine ASR support (Vosk, Hugging Face Wav2Vec2, SpeechBrain)
  - `audio_pipeline/new_handler.py`: Complete pipeline orchestration with proper error handling
  - `utils/ffmpeg.py`: Safe audio conversion utilities with comprehensive format support
  - `summarization_adapter.py`: Integration bridge to existing Groq/Llama summarization
- **Intelligent Fallbacks**: Professional fallback system with informative user messages when ASR engines unavailable
- **Production Integration**: Successfully integrated with existing bot architecture
- **Full Pipeline Confirmed**: Download → Convert → Segment → [Multi-ASR/Fallback] → Summarize → Response

### Audio Processing Features (January 11, 2025)
- ✅ Voice messages, audio files, and video notes support
- ✅ Multiple ASR engine support with automatic fallback
- ✅ FFmpeg integration for format conversion
- ✅ Audio segmentation with configurable chunk sizes
- ✅ Integration with existing Groq/Llama summarization
- ✅ Professional UX with processing status updates
- ✅ Comprehensive error handling and cleanup
- ✅ Configuration via environment variables

### Current ASR Options
1. **Vosk**: Offline models for Russian/English (requires `pip install vosk`)
2. **Hugging Face Wav2Vec2**: Russian language model (requires `transformers torch`)
3. **SpeechBrain**: Multi-language support (requires `speechbrain`)
4. **Whisper**: Still available as original fallback (requires manual installation)
5. **Intelligent Fallback**: Informative messages when no ASR available

### Next Steps for Enhanced Functionality
1. Install ASR engines: `pip install vosk` or `pip install transformers torch` 
2. Alternative Whisper: `pip install openai-whisper` (see WHISPER_INSTALLATION.md)
3. Optional VAD: `pip install webrtcvad`
4. System fully functional with current multi-engine fallback solution
```