#!/bin/bash
# Startup script for deployment

echo "Starting Telegram Bot Application..."
echo "Environment: ${REPLIT_ENV:-production}"
echo "Port: ${PORT:-5000}"

# Set default port if not specified
export PORT=${PORT:-5000}

# Start the application based on deployment type
if [ "$DEPLOYMENT_TYPE" = "background" ]; then
    echo "Starting in Background Worker mode..."
    python simple_bot.py
else
    echo "Starting in Cloud Run mode with HTTP server..."
    python main_server.py
fi