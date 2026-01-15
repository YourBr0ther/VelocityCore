FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    rubberband-cli \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install PyTorch with CUDA support (GPU)
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install Demucs for vocal separation
RUN pip install --no-cache-dir demucs soundfile

# Copy application code
COPY app.py .
COPY templates templates/
COPY static static/

# Create directories for processing
RUN mkdir -p /app/downloads /app/jobs /app/separated

# Expose port
EXPOSE 5000

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "300", "app:app"]
