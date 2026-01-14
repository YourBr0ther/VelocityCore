FROM python:3.11-slim

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
RUN pip install --no-cache-dir demucs soundfile

# Clone and install Seed-VC for voice conversion
RUN git clone https://github.com/Plachtaa/seed-vc.git /app/seed-vc
WORKDIR /app/seed-vc
RUN pip install --no-cache-dir -r requirements.txt || true
# Install additional Seed-VC dependencies
RUN pip install --no-cache-dir transformers accelerate safetensors einops librosa munch descript-audio-codec

WORKDIR /app

# Copy application code
COPY app.py .
COPY templates templates/
COPY static static/

# Create directories for voice samples and converted audio
RUN mkdir -p /app/downloads /app/jobs /app/separated /app/voices

# Expose port
EXPOSE 5000

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "300", "app:app"]
