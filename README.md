# VelocityCore GPU

A GPU-accelerated nightcore converter with AI voice transformation. Transforms YouTube audio into high-energy nightcore tracks with optional AI-powered voice conversion using Seed-VC.

## Features

- **YouTube Download** - Direct audio extraction from YouTube URLs
- **Vocal Separation** - AI-powered vocal/instrumental separation using Demucs
- **Voice Conversion** - Transform vocals using Seed-VC with custom voice samples
- **Nightcore Processing** - Speed increase with pitch shift, bass boost, stereo widening
- **Sub-Bass Layer** - Octave-down vocal sub-layer for depth
- **GPU Acceleration** - CUDA-powered processing for fast conversions

## Requirements

- NVIDIA GPU with CUDA support
- Docker with NVIDIA Container Toolkit
- ~10GB disk space for models

## Quick Start

```bash
# Build the image
docker build -t velocitycore-gpu .

# Run with GPU support
docker run -d --gpus all \
  --name velocitycore \
  -p 5555:5000 \
  -v ./voices:/app/voices \
  -v ./output:/app/downloads \
  velocitycore-gpu
```

Access the web interface at `http://localhost:5555`

## Voice Samples

Add voice samples (.wav, .mp3, .m4a, .ogg) to the `voices/` folder. These are used as reference voices for AI voice conversion.

**Main Voice** - Applied to the primary vocal track
**Sub Voice** - Applied to the sub-bass vocal layer

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/convert` | POST | Start conversion job |
| `/api/status/<job_id>` | GET | Check job status |
| `/api/download/<job_id>` | GET | Download result |
| `/api/stream/<job_id>` | GET | Stream audio |
| `/api/voices` | GET | List voice samples |
| `/api/voices/upload` | POST | Upload voice sample |

### Convert Request

```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "main_voice": "female_lead.wav",
  "sub_voice": "male_bass.wav",
  "debug": false
}
```

## Tech Stack

- **Flask** - Web framework
- **Demucs** - Vocal separation (htdemucs model)
- **Seed-VC** - Voice conversion
- **FFmpeg** - Audio processing
- **Rubberband** - Pitch shifting
- **PyTorch + CUDA** - GPU acceleration

## Processing Pipeline

1. Download audio from YouTube (yt-dlp)
2. Separate vocals from instrumental (Demucs)
3. Convert vocals with target voice (Seed-VC)
4. Apply nightcore effects (speed/pitch up 25%)
5. Generate sub-bass vocal layer (octave down)
6. Mix all tracks with mastering chain
7. Output final MP3

## License

MIT
