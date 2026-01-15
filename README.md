# VelocityCore GPU

A GPU-accelerated nightcore converter. Transforms YouTube audio into high-energy nightcore tracks with AI-powered vocal separation.

## Features

- **YouTube Download** - Direct audio extraction from YouTube URLs
- **Vocal Separation** - AI-powered vocal/instrumental separation using Demucs
- **Nightcore Processing** - Speed increase with pitch shift, bass boost, stereo widening
- **Sub-Bass Layer** - Octave-down vocal sub-layer for depth
- **GPU Acceleration** - CUDA-powered processing for fast conversions

## Requirements

- NVIDIA GPU with CUDA support
- Docker with NVIDIA Container Toolkit

## Quick Start

```bash
# Build the image
docker build -t velocitycore-gpu .

# Run with GPU support
docker run -d --gpus all \
  --name velocitycore \
  -p 5555:5000 \
  -v ./output:/app/downloads \
  velocitycore-gpu
```

Access the web interface at `http://localhost:5555`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/convert` | POST | Start conversion job |
| `/api/status/<job_id>` | GET | Check job status |
| `/api/download/<job_id>` | GET | Download result |
| `/api/stream/<job_id>` | GET | Stream audio |

### Convert Request

```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "debug": false
}
```

## Tech Stack

- **Flask** - Web framework
- **Demucs** - Vocal separation (htdemucs model)
- **FFmpeg** - Audio processing
- **Rubberband** - Pitch shifting
- **PyTorch + CUDA** - GPU acceleration

## Processing Pipeline

1. Download audio from YouTube (yt-dlp)
2. Separate vocals from instrumental (Demucs)
3. Apply nightcore effects (speed/pitch up 25%)
4. Generate sub-bass vocal layer (octave down)
5. Mix all tracks with mastering chain
6. Output final MP3

## License

MIT
