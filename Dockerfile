FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY pyproject.toml .
RUN pip install --upgrade pip && pip install --no-cache-dir .

# Copy the application code
COPY . .

# Set environment variables for Cloud Run
ENV PORT=5000
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV DEPLOYMENT_TYPE=cloudrun

# Expose the port
EXPOSE 5000

# Enhanced health check for Cloud Run deployment
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=5 \
    CMD curl -f http://localhost:5000/ || curl -f http://localhost:5000/health || exit 1

# Default command - runs the main entry point (explicit, no $file variable)
CMD ["python", "main_entrypoint.py"]