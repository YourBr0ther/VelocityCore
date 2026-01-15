FROM python:3.10-slim

LABEL maintainer="VelocityCore"
LABEL description="GPU-accelerated nightcore converter"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    rubberband-cli \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Create app directory
WORKDIR /app

# Install Python dependencies (as root for pip)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install PyTorch with CUDA support (GPU)
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install Demucs for vocal separation
RUN pip install --no-cache-dir demucs soundfile

# Copy application code
COPY --chown=appuser:appuser app.py .
COPY --chown=appuser:appuser templates templates/
COPY --chown=appuser:appuser static static/

# Create directories for processing with proper ownership
RUN mkdir -p /app/downloads /app/jobs /app/separated \
    && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Expose port
EXPOSE 5000

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "300", "app:app"]
