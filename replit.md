# Telegram Text Summarization Bot

## Overview

This project is a Telegram bot that provides intelligent text summarization services using AI. The bot is built in Python and leverages Groq API with Llama 3.1 70B model as the primary summarization engine, with a Hugging Face Transformers fallback for reliability. It supports both Russian and English languages and is designed for 24/7 operation.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

The application follows a modular Python architecture with clear separation of concerns:

- **Bot Layer**: Telegram bot interface using python-telegram-bot library
- **AI Service Layer**: Text summarization using Groq API with local model fallback
- **Data Layer**: SQLite database for user settings, request history, and statistics
- **Configuration Layer**: Environment-based configuration management

## Key Components

### 1. Main Bot Handler (`main.py`)
- **Purpose**: Entry point and Telegram bot message handling
- **Responsibilities**: Command processing, message routing, user interaction
- **Architecture Decision**: Uses python-telegram-bot for robust Telegram API integration

### 2. Text Summarizer (`summarizer.py`)
- **Purpose**: AI-powered text summarization with multiple backends
- **Primary Backend**: Groq API with Llama 3.1 70B model
- **Fallback Backend**: Hugging Face Transformers with local GPT-2 based model
- **Architecture Decision**: Dual-backend approach ensures high availability and cost optimization

### 3. Database Manager (`database.py`)
- **Purpose**: Data persistence and user management
- **Technology**: SQLite with thread-safe connection management
- **Schema**: User settings, request history, usage statistics
- **Architecture Decision**: SQLite chosen for simplicity and zero-configuration deployment

### 4. Configuration (`config.py`)
- **Purpose**: Centralized configuration management
- **Features**: Environment variable loading, parameter validation
- **Settings**: API keys, limits, summarization parameters, database URL

## Data Flow

1. **Message Reception**: User sends text message to Telegram bot
2. **Preprocessing**: Text validation, length checks, language detection
3. **Chunking**: Long texts are split into manageable chunks
4. **Summarization**: 
   - Primary: Groq API with Llama 3.1 70B
   - Fallback: Local Hugging Face model if API unavailable
5. **Response**: Formatted summary sent back to user
6. **Logging**: Request details and statistics stored in database

## External Dependencies

### Required APIs
- **Groq API**: Primary summarization service (Llama 3.1 70B model)
- **Telegram Bot API**: Message handling and user interaction

### Python Libraries
- `python-telegram-bot`: Telegram bot framework
- `groq`: Groq API client
- `transformers`: Hugging Face models (fallback)
- `torch`: PyTorch for local model inference
- `python-dotenv`: Environment variable management
- `sqlite3`: Database operations (built-in)

### Fallback Strategy
- **Problem**: API rate limits or service unavailability
- **Solution**: Local Hugging Face model (`ai-forever/rugpt3large_based_on_gpt2`)
- **Trade-offs**: Lower quality but guaranteed availability

## Deployment Strategy

### Platform Support
- **Primary Target**: Replit with Cloud Run deployment (ready for deployment)
- **Alternative**: Any Python hosting platform with HTTP server support

### Deployment Architecture
- **HTTP Server**: Runs on port 5000 with health check endpoints
- **Telegram Bot**: Runs concurrently with HTTP server for 24/7 operation
- **Health Checks**: Available at `/` and `/health` endpoints
- **Status Information**: Available at `/status` endpoint

### Main Entry Points
- **main_server.py**: Combined HTTP server and Telegram bot (for Cloud Run)
- **simple_bot.py**: Standalone Telegram bot (for Background Worker)
- **deploy.py**: Alternative deployment entry point

### Configuration Requirements
- `TELEGRAM_BOT_TOKEN`: Telegram bot authentication
- `GROQ_API_KEY`: Groq API access (optional, enables primary backend)
- `PORT`: HTTP server port (defaults to 5000)
- `DATABASE_URL`: SQLite database path (defaults to local file)

### Scalability Considerations
- **Rate Limiting**: 10 requests per user per minute
- **Text Limits**: 10,000 character maximum input, 50 character minimum
- **Database**: Thread-safe SQLite with connection pooling
- **Memory Management**: Lazy loading of ML models

### Security Features
- **Input Validation**: Text length and format validation
- **Rate Limiting**: Per-user request throttling
- **Error Handling**: Comprehensive exception handling with user feedback
- **Data Privacy**: Local database storage, no external data sharing

### Performance Optimizations
- **Chunking Strategy**: Large texts split into 4,000 character chunks
- **Caching**: Database stores user preferences to avoid repeated API calls
- **Async Operations**: Non-blocking message processing
- **Resource Management**: Lazy loading of heavy ML models

The architecture prioritizes reliability, user experience, and operational simplicity while maintaining high-quality summarization capabilities through the dual-backend approach.

## Recent Changes

### 2025-07-23: Deployment Ready - All Fixes Applied ✅
- **Fixed all Cloud Run deployment issues** with enhanced HTTP health check system
- **Applied all suggested deployment fixes**:
  ✅ Updated run command to explicitly specify main application file (python main_server.py)
  ✅ Added comprehensive health check endpoints (/, /health, /ready, /ping, /status) for Cloud Run
  ✅ Flask dependency already present in pyproject.toml
  ✅ Configured for Cloud Run deployment with HTTP server + Telegram bot
  ✅ Proper polling loop implemented in main execution block with graceful shutdown
- **Created comprehensive deployment entry points**:
  - main_server.py: Primary Cloud Run mode with HTTP server + bot
  - simple_bot.py: Background Worker mode (bot only)
  - deploy.py: Auto-detection deployment script
  - run.py: Enhanced startup script
  - healthcheck.py: Deployment verification tool
- **Enhanced deployment files**:
  - Dockerfile: Optimized for Cloud Run with health checks
  - .dockerignore: Clean deployment images
  - start.sh: Multi-mode startup script
- **Verified deployment readiness**:
  ✅ All health check endpoints returning status 200 with proper JSON
  ✅ HTTP server running on port 5000 with 0.0.0.0 binding
  ✅ Telegram bot active and processing messages successfully
  ✅ LSP errors fixed with proper type annotations
- **Real user test passed**: Bot successfully processed 2220-character text with 47.3% compression

### 2025-07-22: Enhanced Forwarded Message Support
- Fixed KeyError when processing forwarded messages with captions
- Added universal text extraction from both 'text' and 'caption' fields  
- Enhanced `handle_text_message` to accept extracted text parameter
- Resolved 409 conflict errors with automatic webhook clearing
- Bot now handles all media types with text content (images with captions, etc.)
- Improved error handling for robust forwarded message processing