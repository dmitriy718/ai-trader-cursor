# Multi-stage build for ARM64 optimization
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libc6-dev \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt /tmp/requirements.txt

# Install Python dependencies
# Upgrade pip first for better compatibility
RUN pip install --upgrade pip setuptools wheel

# Install core dependencies first (without TensorFlow)
RUN pip install --no-cache-dir --user \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    pydantic==2.5.0 \
    pydantic-settings==2.1.0 \
    python-binance==1.0.19 \
    pandas==2.1.3 \
    numpy==1.26.2 \
    ta==0.11.0 \
    aiosqlite==0.19.0 \
    aiohttp==3.9.1 \
    websockets==12.0 \
    python-json-logger==2.0.7 \
    python-dotenv==1.0.0 \
    pyyaml==6.0.1 \
    tenacity==8.2.3 \
    requests==2.31.0 \
    python-telegram-bot==20.7 \
    feedparser==6.0.10 \
    beautifulsoup4==4.12.2 \
    textblob==0.17.1 \
    pytest==7.4.3 \
    pytest-asyncio==0.21.1 \
    pytest-cov==4.1.0 \
    pytest-mock==3.12.0 \
    httpx==0.25.2 \
    faker==20.1.0

# Try to install tflite-runtime for ARM64, fallback to tensorflow or skip
RUN pip install --no-cache-dir --user tflite-runtime || \
    (echo "tflite-runtime not available, trying tensorflow..." && \
     pip install --no-cache-dir --user tensorflow || \
     echo "TensorFlow installation failed, ML features will use dummy model")

# Final stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    libffi8 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Set working directory
WORKDIR /app

# Copy application code
COPY . /app

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/models

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/health')" || exit 1

# Run the application
CMD ["python", "-m", "src.main", "--config", "config/config.yaml"]
