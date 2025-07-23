# Dockerfile for Cloud Run deployment
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv pip install --system --no-deps -r pyproject.toml

# Copy application code
COPY . .

# Create a non-root user
RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run the application
CMD ["python", "main_server.py"]