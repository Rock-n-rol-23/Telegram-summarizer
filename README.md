# Telegram Summarization Bot v2.0

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Advanced AI-powered Telegram bot for multilingual text summarization with production-grade infrastructure.

## Features

### 🤖 AI Summarization
- **Groq API Integration**: Llama 3.3 70B model for high-quality summaries
- **Two-Phase Quality Pipeline**: Fact preservation with numbers, dates, currencies
- **Language Detection**: Automatic Russian/English detection with appropriate processing
- **Map-Reduce Processing**: Handles long texts with intelligent chunking
- **Numeric Consistency**: Preserves critical numbers and data points

### 📄 Content Processing
- **Text Summarization**: Direct text input with configurable compression (10%, 30%, 50%)
- **Web Page Extraction**: Enhanced content extraction with table support
- **Document Processing**: PDF, DOCX, DOC, TXT, PPTX with OCR support
- **YouTube Videos**: Transcript extraction and summarization (up to 2 hours)
- **Audio Processing**: Voice messages, audio files with speech recognition

### 🔒 Security & Production Features
- **SSRF Protection**: Blocks private networks and localhost access
- **File Validation**: MIME type checking and size limits
- **Rate Limiting**: Per-user and global QPS limits with circuit breakers
- **Input Sanitization**: Secure filename and content handling
- **Webhook Security**: HMAC signature verification

### 🏗️ Infrastructure
- **Structured Logging**: JSON logs with request tracking and duration metrics
- **Background Tasks**: Async processing with progress updates
- **Database Support**: PostgreSQL with connection pooling, SQLite with WAL mode
- **Temp File Management**: Automatic cleanup with configurable retention
- **Health Monitoring**: Comprehensive health checks and metrics

## Quick Start

### Prerequisites
- Python 3.11+
- Telegram Bot Token ([get from @BotFather](https://t.me/botfather))
- Groq API Key ([get from Groq Console](https://console.groq.com))
- PostgreSQL database (optional, SQLite works for development)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd telegram-summarization-bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   # or use the new pyproject.toml
   pip install -e .
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

4. **Initialize database (PostgreSQL only)**
   ```bash
   alembic upgrade head
   ```

5. **Run the bot**
   ```bash
   python main.py
   ```

## Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | `123456789:ABC...` |
| `GROQ_API_KEY` | Groq API key | `gsk_...` |
| `DATABASE_URL` | Database connection string | `postgresql://user:pass@host/db` |

### Optional Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_REQUESTS_PER_MINUTE` | `20` | Rate limit per user |
| `MAX_FILE_SIZE_MB` | `25` | Maximum file size |
| `ENABLE_OCR` | `1` | Enable OCR processing |
| `ENABLE_YOUTUBE` | `1` | Enable YouTube processing |
| `STRUCTURED_LOGGING` | `1` | JSON structured logs |
| `USE_WEBHOOK` | `0` | Use webhook instead of polling |

See `.env.example` for complete configuration options.

## Feature Flags

Control features without code changes:

```bash
# Disable heavy features
ENABLE_OCR=0
ENABLE_YOUTUBE=0
ENABLE_PDF_PROCESSING=0

# Enable webhook mode
USE_WEBHOOK=1
WEBHOOK_URL=https://your-domain.com/webhook
WEBHOOK_SECRET_TOKEN=your-secret
```

## Bot Commands

- `/help` - Show help message
- `/stats` - Show usage statistics
- `/10` - Set 10% compression (brief summary)
- `/30` - Set 30% compression (balanced)
- `/50` - Set 50% compression (detailed)

## Deployment

### Cloud Run (Recommended)

1. **Build and deploy**
   ```bash
   # Using Cloud Build
   gcloud builds submit --tag gcr.io/PROJECT_ID/telegram-bot
   gcloud run deploy --image gcr.io/PROJECT_ID/telegram-bot --platform managed
   ```

2. **Set environment variables**
   ```bash
   gcloud run services update telegram-bot \
     --set-env-vars="TELEGRAM_BOT_TOKEN=your-token,GROQ_API_KEY=your-key"
   ```

### Docker

```bash
# Build image
docker build -t telegram-summarizer .

# Run with environment file
docker run --env-file .env -p 5000:5000 telegram-summarizer
```

### Traditional Hosting

```bash
# With gunicorn
gunicorn main:application --workers 2 --bind 0.0.0.0:5000

# Development
python main.py
```

## Rate Limits & Performance

### Default Limits
- **Per User**: 20 requests/minute
- **Global**: 10 QPS
- **File Size**: 25MB general, 2MB images
- **Text Length**: 50,000 characters (with chunking)

### Performance Optimizations
- Connection pooling for PostgreSQL
- SQLite WAL mode for better concurrency
- Async request processing
- Background task queuing
- Circuit breakers for external services

## Monitoring & Observability

### Health Endpoints
- `GET /health` - Comprehensive health check
- `GET /ready` - Readiness probe
- `GET /live` - Liveness probe

### Structured Logging
```json
{
  "timestamp": "2025-08-22T08:00:00Z",
  "level": "INFO",
  "message": "Request processed",
  "request_id": "abc123",
  "user_id": 12345,
  "duration": 1.5,
  "external_service": "groq",
  "external_duration": 0.8
}
```

### Metrics Tracked
- Request processing times
- External API call durations
- Compression ratios
- Error rates by service
- User activity patterns

## Security

### Implemented Protections
- **SSRF Protection**: Blocks internal network access
- **File Validation**: MIME type and size checking
- **Input Sanitization**: Prevents path traversal and injection
- **Rate Limiting**: Prevents abuse and DoS
- **Webhook Validation**: HMAC signature verification

### Security Best Practices
- Keep API keys in environment variables
- Use webhook mode with secret token in production
- Enable file validation and size limits
- Monitor rate limit violations
- Regular security updates

## Development

### Code Quality
```bash
# Install pre-commit hooks
pre-commit install

# Run linting
ruff check .
black .

# Run tests
python tests/test_comprehensive.py
```

### Database Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Troubleshooting

### Common Issues

**Bot not responding**
- Check `TELEGRAM_BOT_TOKEN` is correct
- Verify network connectivity
- Check logs for error messages

**Summarization failing**
- Verify `GROQ_API_KEY` is valid
- Check Groq API rate limits
- Review input text length

**Database errors**
- Ensure PostgreSQL is running
- Check `DATABASE_URL` format
- Run database migrations

**File processing issues**
- Check file size limits
- Verify OCR dependencies (tesseract)
- Review file type allowlist

### Debug Mode
```bash
DEBUG=1 LOG_LEVEL=DEBUG python main.py
```

## Architecture

### Core Components
- **Bot Layer**: Telegram interaction handling
- **AI Service**: Groq API integration with fallbacks
- **Processing Pipeline**: Language detection → chunking → summarization
- **Security Layer**: SSRF protection, validation, rate limiting
- **Infrastructure**: Logging, monitoring, background tasks

### Database Schema
- `user_requests`: Request history and analytics
- `user_settings`: User preferences and configuration
- `web_cache`: Cached web content (72h TTL)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run quality checks: `pre-commit run --all-files`
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

- **Issues**: GitHub Issues
- **Documentation**: This README
- **Security**: Report security issues privately

---

Built with ❤️ using Python 3.11, Groq AI, and modern production practices.