FROM python:3.11-slim

# Metadata
LABEL maintainer="CuePlex"
LABEL version="1.0.0"
LABEL description="CuePlex - Self-hosted Plex request platform"

# Set working directory
WORKDIR /app

# Create non-root user for security
RUN groupadd -r cueplex && useradd -r -g cueplex cueplex

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    openssl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code (excluding dev files via .dockerignore)
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p logs data \
    && chown -R cueplex:cueplex /app

# Copy env-template to .env and generate secure secret key
RUN cp env-template .env \
    && SECRET_KEY=$(openssl rand -hex 32) \
    && sed -i "s/CHANGE_THIS_TO_A_RANDOM_STRING_32_CHARS_MIN/$SECRET_KEY/g" .env \
    && chown cueplex:cueplex .env

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Switch to non-root user
USER cueplex

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run the application with Gunicorn for production
CMD ["python", "-m", "gunicorn", "app.main:app", \
     "-w", "1", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8001", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--preload"]