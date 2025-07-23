# Deployment Guide for Telegram Summarization Bot

## Overview

This Telegram bot supports multiple deployment modes to ensure reliable operation across different platforms.

## Fixed Deployment Issues

✅ **Health Check Endpoints**: Added comprehensive HTTP health checks
✅ **Explicit Run Command**: Replaced `$file` variable with explicit `python run.py`
✅ **Flask Dependency**: Already included in pyproject.toml
✅ **Multiple Deployment Modes**: Cloud Run and Background Worker support
✅ **Proper Polling Loop**: Bot starts correctly in main execution block

## Deployment Options

### 1. Cloud Run Deployment (HTTP Server + Bot) - RECOMMENDED
- **Entry Point**: `simple_server.py` (primary), `run.py`, `app.py` (compatibility)
- **Health Checks**: Available at `/`, `/health`, `/ready`
- **Port**: 5000 (configurable via `PORT` environment variable)
- **Features**: Simplified HTTP server with Telegram bot running concurrently
- **Fixed Issues**: 
  - ✓ Removed $file variable dependency
  - ✓ Added explicit entry point files
  - ✓ Simplified health check endpoints for reliable deployment
  - ✓ Streamlined server startup process
  - ✓ Enhanced root endpoint response for Cloud Run compatibility

**Command**: `python simple_server.py`

### 2. Background Worker Deployment (Bot Only)
- **Entry Point**: `simple_bot.py`
- **Mode**: Pure Telegram bot without HTTP server
- **Best for**: Platforms that support long-running background processes

**Command**: `python simple_bot.py`

### 3. Auto-Detection Deployment
- **Entry Point**: `main.py`
- **Features**: Automatically detects deployment environment and chooses mode
- **Environment Variables**: Uses `K_SERVICE`, `REPLIT_DEPLOYMENT`, `DEPLOYMENT_TYPE`
- **Deployment Types**: 
  - 'cloudrun' or 'http' → HTTP server + bot
  - 'background' or 'worker' → Bot only

**Command**: `python main.py`

## Health Check Endpoints

All endpoints return JSON responses with proper HTTP status codes:

- `GET /` - Main health check
- `GET /health` - Health status with timestamp
- `GET /ready` - Readiness probe for Kubernetes/Cloud Run
- `GET /ping` - Simple ping endpoint
- `GET /status` - Detailed service information

### Example Response (Healthy):
```json
{
  "status": "healthy",
  "service": "telegram-bot",
  "timestamp": 1234567.89,
  "ready": true
}
```

## Environment Variables

### Required
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- `GROQ_API_KEY`: Groq API key (optional, enables primary AI backend)

### Optional
- `PORT`: HTTP server port (default: 5000)
- `DEPLOYMENT_TYPE`: Force deployment mode (`cloudrun` or `background`)
- `DATABASE_URL`: SQLite database path (default: `bot_database.db`)

## Platform-Specific Instructions

### Replit
1. The current configuration automatically uses the correct deployment mode
2. Workflow is configured to run `python main_server.py` on port 5000
3. Health checks are accessible via the public URL

### Cloud Run (Google Cloud)
```bash
# Use the Dockerfile provided
docker build -t telegram-bot .
docker run -p 5000:5000 -e TELEGRAM_BOT_TOKEN=your_token telegram-bot
```

### Heroku
```bash
# Use main_server.py as entry point
echo "python main_server.py" > Procfile
```

### Traditional VPS
```bash
# Background worker mode
python simple_bot.py

# Or with HTTP server
python main_server.py
```

## Deployment Verification

1. **Health Check**: `curl http://your-app-url/health`
2. **Bot Status**: Check logs for "Бот запущен и готов к работе!"
3. **Telegram Test**: Send `/help` to your bot

## Troubleshooting

### Health Checks Failing
- Ensure the application is binding to `0.0.0.0:5000`
- Check logs for startup errors
- Verify `PORT` environment variable

### Bot Not Responding
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Check internet connectivity
- Review bot logs for API errors

### Mixed Mode Issues
- Use `DEPLOYMENT_TYPE=background` to force background worker mode
- Use `DEPLOYMENT_TYPE=cloudrun` to force HTTP server mode

## Current Status

The application is configured and tested for:
- ✅ HTTP server on port 5000
- ✅ Health checks responding correctly
- ✅ Telegram bot active and registered
- ✅ All endpoints returning proper responses
- ✅ Graceful shutdown handling
- ✅ Error handling and logging

The deployment is ready for production use on any supported platform.