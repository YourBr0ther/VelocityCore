# VelocityCore GPU

A GPU-accelerated nightcore converter that transforms YouTube audio into high-energy nightcore tracks using AI-powered vocal separation and professional audio mastering.

## What is Nightcore?

Nightcore is a style of music created by speeding up and pitch-shifting the original track, producing a faster, higher-pitched version with enhanced energy. VelocityCore takes this further by separating vocals from instrumentals using AI, applying sophisticated audio processing to each layer independently, and mixing them back together with professional mastering.

## Features

- **YouTube Integration** - Direct audio extraction from any YouTube URL using yt-dlp
- **AI Vocal Separation** - Demucs neural network isolates vocals from instrumentals for independent processing
- **Nightcore Processing** - 25% speed increase with natural pitch shift
- **Sub-Bass Vocal Layer** - Creates an octave-down vocal harmony for depth and richness
- **GPU Acceleration** - CUDA-powered neural network inference for fast separation
- **Track Library** - Persistent storage of converted tracks with autoplay queue
- **Debug Mode** - Export intermediate tracks (vocals, instrumental, sub-vocals) for inspection
- **Web Interface** - Modern cyberpunk-styled UI with real-time progress tracking
- **Audio Streaming** - Range request support for proper seeking in the browser player

## Requirements

- NVIDIA GPU with CUDA support (4GB+ VRAM recommended)
- Docker with [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

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

Access the web interface at **http://localhost:5555**

## Usage

1. Open the web interface in your browser
2. Paste a YouTube URL into the input field
3. Optionally enable **Debug Mode** to export intermediate tracks
4. Click **Convert** and wait for processing (typically 1-3 minutes)
5. Play the result in the embedded player or download the MP3
6. Tracks are automatically saved to your library for later playback

## Volume Mounts

| Mount Point | Purpose |
|-------------|---------|
| `/app/downloads` | Converted MP3s and debug files |
| `/app/jobs` | Job metadata and library persistence |
| `/app/separated` | Temporary Demucs output (can be omitted) |

Example with all volumes:
```bash
docker run -d --gpus all \
  --name velocitycore \
  -p 5555:5000 \
  -v ./output:/app/downloads \
  -v ./jobs:/app/jobs \
  velocitycore-gpu
```

## API Reference

### Start Conversion
```
POST /api/convert
Content-Type: application/json

{
  "url": "https://www.youtube.com/watch?v=...",
  "debug": false
}
```
Returns: `{"job_id": "abc123"}`

### Check Status
```
GET /api/status/<job_id>
```
Returns job status, progress percentage, and file info when complete.

### Download/Stream
```
GET /api/download/<job_id>    # Download as attachment
GET /api/stream/<job_id>      # Stream with range support
```

### Debug Tracks (when debug=true)
```
GET /api/debug/<job_id>/vocals
GET /api/debug/<job_id>/instrumental
GET /api/debug/<job_id>/sub_vocals
```

### Library
```
GET /api/library              # List all saved tracks
DELETE /api/library/<job_id>  # Remove track from library
```

## Processing Pipeline

```
YouTube URL
    │
    ▼
┌─────────────────────┐
│  Download Audio     │  yt-dlp extracts best quality audio
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  AI Separation      │  Demucs (htdemucs) splits vocals/instrumental
└─────────────────────┘
    │
    ├────────────────────────────────┐
    ▼                                ▼
┌─────────────┐              ┌───────────────┐
│   Vocals    │              │ Instrumental  │
└─────────────┘              └───────────────┘
    │                                │
    │  ┌─────────────────────────────┤
    │  │                             │
    ▼  ▼                             ▼
┌─────────────┐              ┌───────────────┐
│ Nightcore   │              │  Nightcore    │
│ + De-esser  │              │  Processing   │
└─────────────┘              └───────────────┘
    │                                │
    ├────────────┐                   │
    ▼            │                   │
┌─────────────┐  │                   │
│ Sub-Octave  │  │                   │
│ Vocal Layer │  │                   │
└─────────────┘  │                   │
    │            │                   │
    ▼            ▼                   ▼
┌─────────────────────────────────────────┐
│            Master Mix                    │
│  • Stereo widening (1.5x)               │
│  • Bass boost (+2dB)                    │
│  • High-frequency air (+3dB @ 12kHz)    │
│  • Room ambiance                        │
│  • Loudness normalization (-14 LUFS)    │
│  • Limiter (0.95 ceiling)               │
└─────────────────────────────────────────┘
    │
    ▼
  MP3 Output
```

## Audio Processing Details

### Nightcore Transform
- **Speed/Pitch:** +25% (asetrate filter)
- **Sampling Rate:** 44.1kHz

### Vocal Processing
- **De-esser:** -4dB at 6kHz (2 octave width)
- **High-cut:** -3dB shelf at 8kHz

### Sub-Bass Layer
- **Pitch Shift:** -12 semitones (1 octave down via Rubberband)
- **Lowpass Filter:** 300Hz cutoff
- **Saturation:** Tanh soft clipping

### Master Chain
- **Stereo Width:** 1.5x enhancement
- **Bass Boost:** +2dB low shelf
- **Air:** +3dB high shelf at 12kHz
- **Ambiance:** 15-20ms echo with 0.1-0.15 feedback
- **Loudness:** -14 LUFS (streaming standard)
- **Limiter:** 0.95 ceiling

## Tech Stack

| Component | Technology |
|-----------|------------|
| Web Framework | Flask 3.0 |
| Production Server | Gunicorn |
| YouTube Download | yt-dlp |
| Vocal Separation | Demucs (htdemucs) |
| Audio Processing | FFmpeg |
| Pitch Shifting | Rubberband |
| GPU Acceleration | PyTorch + CUDA 11.8 |

## File Retention

- Temporary files are automatically cleaned up after 1 hour
- Library tracks are preserved indefinitely
- Cleanup runs every 5 minutes

## Troubleshooting

### "CUDA out of memory"
The Demucs model requires ~3-4GB VRAM. Close other GPU applications or use a GPU with more memory.

### Slow first conversion
The Demucs model (~200MB) is downloaded on first run. Subsequent conversions will be faster.

### Container won't start
Ensure NVIDIA Container Toolkit is installed:
```bash
nvidia-smi  # Should show your GPU
docker run --rm --gpus all nvidia/cuda:11.8-base nvidia-smi  # Test Docker GPU access
```

### Health check failing
The container has a 60-second startup grace period for model loading. Check logs:
```bash
docker logs velocitycore
```

## License

MIT
