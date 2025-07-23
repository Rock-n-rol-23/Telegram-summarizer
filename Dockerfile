FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
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

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health')" || exit 1

# Default command - runs the Cloud Run optimized server
CMD ["python", "cloudrun_optimized.py"]