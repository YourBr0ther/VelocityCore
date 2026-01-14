import os
import subprocess
import uuid
import threading
import time
import re
import json
from flask import Flask, render_template, request, jsonify, send_file, url_for, Response
from werkzeug.utils import secure_filename

app = Flask(__name__)


def sanitize_title(title):
    """Clean up YouTube title to get just Artist - Song Name"""
    # Patterns to remove (case insensitive)
    patterns_to_remove = [
        r'\(Official\s*(Music\s*)?Video\)',
        r'\(Official\s*Audio\)',
        r'\(Audio\)',
        r'\(Lyrics?\)',
        r'\(Lyric\s*Video\)',
        r'\(Visualizer\)',
        r'\(HD\)',
        r'\(HQ\)',
        r'\(4K\)',
        r'\(4K\s*Remaster(ed)?\)',
        r'\(Remaster(ed)?\)',
        r'\(Official\)',
        r'\(Explicit\)',
        r'\(Clean\)',
        r'\(Radio\s*Edit\)',
        r'\(Music\s*Video\)',
        r'\(Video\)',
        r'\(Live\)',
        r'\(Acoustic\)',
        r'\(Remix\)',
        r'\[Official\s*(Music\s*)?Video\]',
        r'\[Official\s*Audio\]',
        r'\[Lyrics?\]',
        r'\[HD\]',
        r'\[HQ\]',
        r'\[4K\]',
        r'Official\s*(Music\s*)?Video',
        r'Official\s*Audio',
        r'Lyrics?\s*Video',
        r'\bLyrics?\b',
        r'\bHD\b',
        r'\bHQ\b',
        r'\b4K\b',
        r'ft\.',
        r'feat\.',
    ]

    cleaned = title
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # Clean up extra whitespace and dashes
    cleaned = re.sub(r'\s+', ' ', cleaned)  # Multiple spaces to single
    cleaned = re.sub(r'\s*-\s*-\s*', ' - ', cleaned)  # Double dashes
    cleaned = re.sub(r'\s*\(\s*\)', '', cleaned)  # Empty parentheses
    cleaned = re.sub(r'\s*\[\s*\]', '', cleaned)  # Empty brackets
    cleaned = re.sub(r'^\s*-\s*', '', cleaned)  # Leading dash
    cleaned = re.sub(r'\s*-\s*$', '', cleaned)  # Trailing dash
    cleaned = cleaned.strip()

    return cleaned if cleaned else title

# Configuration
DOWNLOAD_FOLDER = '/app/downloads'
JOBS_FOLDER = '/app/jobs'
SEPARATED_FOLDER = '/app/separated'
VOICES_FOLDER = '/app/voices'
SEED_VC_PATH = '/app/seed-vc'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(JOBS_FOLDER, exist_ok=True)
os.makedirs(SEPARATED_FOLDER, exist_ok=True)
os.makedirs(VOICES_FOLDER, exist_ok=True)


def convert_voice_seedvc(source_audio, reference_voice, output_path, singing_mode=True, semi_tone_shift=0):
    """Convert voice using Seed-VC with singing voice conversion model

    When singing_mode=True, uses the seed-uvit-whisper-base model (200M params, 44kHz)
    which is specifically designed for singing voice conversion.
    """
    try:
        print(f"[Seed-VC SVC] Starting singing voice conversion...", flush=True)
        print(f"[Seed-VC SVC] Source: {source_audio}", flush=True)
        print(f"[Seed-VC SVC] Reference: {reference_voice}", flush=True)
        print(f"[Seed-VC SVC] Output: {output_path}", flush=True)
        print(f"[Seed-VC SVC] Singing mode: {singing_mode}, Semi-tone shift: {semi_tone_shift}", flush=True)

        # Run Seed-VC inference with SVC settings
        # When f0-condition=True, it auto-downloads seed-uvit-whisper-base (SVC model)
        cmd = [
            'python', f'{SEED_VC_PATH}/inference.py',
            '--source', source_audio,
            '--target', reference_voice,
            '--output', os.path.dirname(output_path),
            '--diffusion-steps', '30',  # 30-50 recommended for singing
            '--f0-condition', 'True' if singing_mode else 'False',
            '--semi-tone-shift', str(semi_tone_shift),  # Pitch shift in semitones
            '--inference-cfg-rate', '0.7'
        ]
        print(f"[Seed-VC SVC] Command: {' '.join(cmd)}", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=SEED_VC_PATH)

        print(f"[Seed-VC SVC] Return code: {result.returncode}", flush=True)
        if result.stdout:
            print(f"[Seed-VC SVC] STDOUT: {result.stdout[:800]}", flush=True)
        if result.stderr:
            print(f"[Seed-VC SVC] STDERR: {result.stderr[:500]}", flush=True)

        # Seed-VC outputs to a directory, find the output file
        # Output format: vc_{source_basename}_{target_basename}_{params}.wav
        output_dir = os.path.dirname(output_path)
        source_basename = os.path.splitext(os.path.basename(source_audio))[0]
        print(f"[Seed-VC SVC] Looking for output in: {output_dir}", flush=True)
        print(f"[Seed-VC SVC] Source basename: {source_basename}", flush=True)
        files_in_dir = os.listdir(output_dir)
        print(f"[Seed-VC SVC] Files in output dir: {files_in_dir[:10]}", flush=True)

        for f in files_in_dir:
            # Match Seed-VC output pattern: vc_{source}_{target}_{params}.wav
            if f.startswith(f'vc_{source_basename}') and f.endswith('.wav'):
                actual_output = os.path.join(output_dir, f)
                os.rename(actual_output, output_path)
                print(f"[Seed-VC SVC] SUCCESS - output renamed to {output_path}", flush=True)
                return True
        print(f"[Seed-VC SVC] FAILED - no output file found", flush=True)
        return False
    except Exception as e:
        print(f"[Seed-VC SVC] EXCEPTION: {e}", flush=True)
        return False


def get_job(job_id):
    """Read job status from file"""
    job_file = os.path.join(JOBS_FOLDER, f'{job_id}.json')
    if os.path.exists(job_file):
        try:
            with open(job_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return None


def save_job(job_id, data):
    """Save job status to file"""
    job_file = os.path.join(JOBS_FOLDER, f'{job_id}.json')
    with open(job_file, 'w') as f:
        json.dump(data, f)


def cleanup_old_files():
    """Remove files older than 1 hour"""
    while True:
        time.sleep(300)  # Check every 5 minutes
        try:
            now = time.time()
            # Clean up downloads
            for filename in os.listdir(DOWNLOAD_FOLDER):
                filepath = os.path.join(DOWNLOAD_FOLDER, filename)
                if os.path.isfile(filepath) and now - os.path.getmtime(filepath) > 3600:
                    os.remove(filepath)
            # Clean up job files
            for filename in os.listdir(JOBS_FOLDER):
                filepath = os.path.join(JOBS_FOLDER, filename)
                if os.path.isfile(filepath) and now - os.path.getmtime(filepath) > 3600:
                    os.remove(filepath)
        except Exception:
            pass


# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()


def process_nightcore(job_id, youtube_url, debug_mode=False, main_voice=None, sub_voice=None):
    """Download from YouTube and convert to nightcore with vocal sub-layer and optional voice conversion"""
    try:
        save_job(job_id, {'status': 'downloading', 'progress': 5, 'debug': debug_mode})

        # Generate unique filenames
        original_file = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_original.mp3')
        wav_file = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_original.wav')
        nightcore_file = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_nightcore.mp3')
        job_separated_dir = os.path.join(SEPARATED_FOLDER, job_id)

        # Download audio using yt-dlp
        download_cmd = [
            'yt-dlp',
            '-x',  # Extract audio
            '--audio-format', 'mp3',
            '--audio-quality', '0',  # Best quality
            '-o', original_file.replace('.mp3', '.%(ext)s'),
            '--no-playlist',
            '--max-filesize', '50M',
            youtube_url
        ]

        result = subprocess.run(download_cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            save_job(job_id, {'status': 'error', 'message': 'Failed to download audio. Check the URL.'})
            return

        # Find the downloaded file (yt-dlp might have added extension)
        for ext in ['.mp3', '.m4a', '.webm', '.opus']:
            potential_file = original_file.replace('.mp3', ext)
            if os.path.exists(potential_file):
                original_file = potential_file
                break

        if not os.path.exists(original_file):
            save_job(job_id, {'status': 'error', 'message': 'Downloaded file not found.'})
            return

        save_job(job_id, {'status': 'separating', 'progress': 15})

        # Convert to WAV for Demucs
        subprocess.run(['ffmpeg', '-i', original_file, '-y', wav_file],
                      capture_output=True, timeout=60)

        # Run Demucs to separate vocals from instrumental
        # Using htdemucs model (good balance of speed/quality)
        demucs_cmd = [
            'python', '-m', 'demucs',
            '--two-stems', 'vocals',  # Only separate vocals vs other
            '-o', SEPARATED_FOLDER,
            '-n', 'htdemucs',
            '--mp3',  # Output as MP3 to avoid torchcodec issues
            '--filename', '{track}_{stem}.{ext}',
            wav_file
        ]

        result = subprocess.run(demucs_cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            # Fallback to simple method if Demucs fails
            save_job(job_id, {'status': 'converting', 'progress': 50})
            nightcore_filter = 'asetrate=44100*1.25,aresample=44100,bass=g=2,extrastereo=m=1.5'
            subprocess.run([
                'ffmpeg', '-i', original_file, '-af', nightcore_filter, '-y', nightcore_file
            ], capture_output=True, timeout=180)
        else:
            save_job(job_id, {'status': 'converting', 'progress': 50})

            # Find separated files (now MP3 format)
            vocals_file = os.path.join(SEPARATED_FOLDER, 'htdemucs', f'{job_id}_original_vocals.mp3')
            other_file = os.path.join(SEPARATED_FOLDER, 'htdemucs', f'{job_id}_original_no_vocals.mp3')

            # Temporary files for processing
            vocals_nc = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_vocals_nc.wav')
            vocals_sub = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_vocals_sub.wav')
            other_nc = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_other_nc.wav')

            # Voice conversion step (if voices specified)
            if main_voice or sub_voice:
                print(f"[{job_id}] Starting voice conversion - main: {main_voice}, sub: {sub_voice}", flush=True)
                save_job(job_id, {'status': 'voice_converting', 'progress': 55})

                # Convert separated vocals to WAV for Seed-VC
                vocals_wav = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_vocals_raw.wav')
                subprocess.run(['ffmpeg', '-i', vocals_file, '-y', vocals_wav],
                              capture_output=True, timeout=60)
                print(f"[{job_id}] Vocals WAV created: {os.path.exists(vocals_wav)}", flush=True)

                if main_voice:
                    # Convert main vocals to target voice
                    main_voice_path = os.path.join(VOICES_FOLDER, secure_filename(main_voice))
                    vocals_converted = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_vocals_converted.wav')
                    print(f"[{job_id}] Converting main voice with: {main_voice_path}", flush=True)
                    if convert_voice_seedvc(vocals_wav, main_voice_path, vocals_converted, singing_mode=True):
                        # Use converted vocals for processing
                        print(f"[{job_id}] Main voice conversion SUCCESS", flush=True)
                        vocals_file = vocals_converted
                    else:
                        # Fallback to original if conversion fails
                        print(f"[{job_id}] Main voice conversion FAILED - using original", flush=True)
                        vocals_file = vocals_wav

                if sub_voice:
                    # Convert vocals with sub voice for the sub-layer (will be pitch-shifted later)
                    sub_voice_path = os.path.join(VOICES_FOLDER, secure_filename(sub_voice))
                    vocals_sub_converted = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_vocals_sub_converted.wav')
                    print(f"[{job_id}] Converting sub voice with: {sub_voice_path}", flush=True)
                    result = convert_voice_seedvc(vocals_wav, sub_voice_path, vocals_sub_converted, singing_mode=True)
                    print(f"[{job_id}] Sub voice conversion result: {result}", flush=True)
                    # Store for later use in sub-layer
                    vocals_for_sub = vocals_sub_converted if os.path.exists(vocals_sub_converted) else vocals_wav
                else:
                    vocals_for_sub = None
            else:
                print(f"[{job_id}] No voice conversion requested", flush=True)

            save_job(job_id, {'status': 'processing', 'progress': 65})

            # Apply nightcore speed+pitch to vocals with de-essing and high cut
            # - asetrate/aresample: speed up 25% with natural pitch rise
            # - equalizer at 6kHz: de-esser (reduces harsh sibilance)
            # - highshelf at 8kHz: tames shrillness on high-pitched singers
            vocals_filter = (
                'asetrate=44100*1.25,aresample=44100,'
                'equalizer=f=6000:width_type=o:width=2:g=-4,'
                'highshelf=f=8000:g=-3'
            )
            subprocess.run([
                'ffmpeg', '-i', vocals_file,
                '-af', vocals_filter,
                '-y', vocals_nc
            ], capture_output=True, timeout=120)

            # Apply nightcore speed+pitch to instrumental
            subprocess.run([
                'ffmpeg', '-i', other_file,
                '-af', 'asetrate=44100*1.25,aresample=44100',
                '-y', other_nc
            ], capture_output=True, timeout=120)

            # Create sub-octave vocals using rubberband (pitch down without speed change)
            # Use converted sub voice if available, otherwise use main vocals
            if main_voice or sub_voice:
                if sub_voice and 'vocals_for_sub' in locals() and vocals_for_sub and os.path.exists(vocals_for_sub):
                    # Apply nightcore to sub-voice converted vocals first
                    vocals_sub_nc = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_vocals_sub_nc.wav')
                    subprocess.run([
                        'ffmpeg', '-i', vocals_for_sub,
                        '-af', 'asetrate=44100*1.25,aresample=44100',
                        '-y', vocals_sub_nc
                    ], capture_output=True, timeout=120)
                    # Then pitch down
                    subprocess.run([
                        'rubberband',
                        '-p', '-12',  # Pitch down 12 semitones (1 octave)
                        vocals_sub_nc, vocals_sub
                    ], capture_output=True, timeout=120)
                else:
                    # No sub voice, use main vocals for sub-layer
                    subprocess.run([
                        'rubberband',
                        '-p', '-12',
                        vocals_nc, vocals_sub
                    ], capture_output=True, timeout=120)
            else:
                # No voice conversion, use regular sub-layer
                subprocess.run([
                    'rubberband',
                    '-p', '-12',  # Pitch down 12 semitones (1 octave)
                    vocals_nc, vocals_sub
                ], capture_output=True, timeout=120)

            save_job(job_id, {'status': 'mixing', 'progress': 80})

            # Mix everything together:
            # - Instrumental (full volume)
            # - Vocals (full volume)
            # - Sub-vocals with processing:
            #   - lowpass=300Hz (only deep bass frequencies)
            #   - asoftclip (warm saturation/grit)
            #   - volume boost (0.35 = 35%)
            # Final mix processing:
            #   - bass boost (+2dB)
            #   - stereo widening (1.5x)
            #   - high-frequency "air" boost (+3dB at 12kHz+)
            #   - subtle room ambiance (short echo)
            #   - loudness normalization (-14 LUFS for streaming)
            #   - limiter (prevent clipping)
            mix_filter = (
                '[0:a]volume=1.0[inst];'
                '[1:a]volume=1.0[vox];'
                '[2:a]lowpass=f=300,asoftclip=type=tanh,volume=0.6[subvox];'
                '[inst][vox][subvox]amix=inputs=3:duration=longest[mixed];'
                '[mixed]bass=g=2,extrastereo=m=1.5,'
                'highshelf=f=12000:g=3,'
                'aecho=1.0:0.7:15|20:0.15|0.1,'
                'loudnorm=I=-14:TP=-1:LRA=11,'
                'alimiter=limit=0.95:level=1'
            )

            subprocess.run([
                'ffmpeg',
                '-i', other_nc,
                '-i', vocals_nc,
                '-i', vocals_sub,
                '-filter_complex', mix_filter,
                '-y', nightcore_file
            ], capture_output=True, timeout=180)

            # Get song title early for debug file naming
            title_cmd = ['yt-dlp', '--get-title', youtube_url]
            title_result = subprocess.run(title_cmd, capture_output=True, text=True, timeout=30)
            raw_title = title_result.stdout.strip() if title_result.returncode == 0 else 'Unknown Track'
            clean_title = sanitize_title(raw_title)
            safe_title = re.sub(r'[<>:"/\\|?*]', '', clean_title)

            debug_files = {}

            if debug_mode:
                # Rename and keep debug files with descriptive names
                debug_vocals = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_vocals.mp3')
                debug_instrumental = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_instrumental.mp3')
                debug_sub_vocals = os.path.join(DOWNLOAD_FOLDER, f'{job_id}_sub_vocals.mp3')

                # Convert wav files to mp3 for easier playback
                subprocess.run(['ffmpeg', '-i', vocals_nc, '-y', debug_vocals], capture_output=True, timeout=60)
                subprocess.run(['ffmpeg', '-i', other_nc, '-y', debug_instrumental], capture_output=True, timeout=60)
                subprocess.run(['ffmpeg', '-i', vocals_sub, '-y', debug_sub_vocals], capture_output=True, timeout=60)

                debug_files = {
                    'vocals': debug_vocals,
                    'instrumental': debug_instrumental,
                    'sub_vocals': debug_sub_vocals
                }

                # Clean up wav files but keep mp3 debug files
                for f in [vocals_nc, vocals_sub, other_nc, wav_file, vocals_file, other_file]:
                    try:
                        os.remove(f)
                    except:
                        pass
            else:
                # Clean up all temporary files
                for f in [vocals_nc, vocals_sub, other_nc, wav_file, vocals_file, other_file]:
                    try:
                        os.remove(f)
                    except:
                        pass

            # Clean up separated directory
            try:
                import shutil
                shutil.rmtree(os.path.join(SEPARATED_FOLDER, 'htdemucs'), ignore_errors=True)
            except:
                pass

        # Clean up original file
        try:
            os.remove(original_file)
        except:
            pass

        # Get song title if not already fetched
        if 'clean_title' not in locals():
            title_cmd = ['yt-dlp', '--get-title', youtube_url]
            title_result = subprocess.run(title_cmd, capture_output=True, text=True, timeout=30)
            raw_title = title_result.stdout.strip() if title_result.returncode == 0 else 'Unknown Track'
            clean_title = sanitize_title(raw_title)
            safe_title = re.sub(r'[<>:"/\\|?*]', '', clean_title)
            debug_files = {}

        # Create clean filename
        safe_filename = f'[NiGHTCoRE] {safe_title}.mp3'

        job_result = {
            'status': 'complete',
            'progress': 100,
            'file': nightcore_file,
            'title': f'[NiGHTCoRE] {clean_title}',
            'filename': safe_filename,
            'debug': debug_mode
        }

        if debug_files:
            job_result['debug_files'] = debug_files

        save_job(job_id, job_result)

    except subprocess.TimeoutExpired:
        save_job(job_id, {'status': 'error', 'message': 'Processing timed out.'})
    except Exception as e:
        save_job(job_id, {'status': 'error', 'message': str(e)})


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/voices', methods=['GET'])
def list_voices():
    """List available voice samples"""
    voices = []
    for filename in os.listdir(VOICES_FOLDER):
        if filename.endswith(('.mp3', '.wav', '.m4a', '.ogg')):
            voices.append({
                'id': filename,
                'name': os.path.splitext(filename)[0]
            })
    return jsonify({'voices': voices})


@app.route('/api/voices/upload', methods=['POST'])
def upload_voice():
    """Upload a voice sample"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Get custom name or use filename
    voice_name = request.form.get('name', '')
    if not voice_name:
        voice_name = os.path.splitext(file.filename)[0]

    # Secure the filename
    safe_name = secure_filename(voice_name)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.mp3', '.wav', '.m4a', '.ogg']:
        return jsonify({'error': 'Invalid file type. Use MP3, WAV, M4A, or OGG'}), 400

    filename = f'{safe_name}{ext}'
    filepath = os.path.join(VOICES_FOLDER, filename)
    file.save(filepath)

    return jsonify({
        'success': True,
        'voice': {
            'id': filename,
            'name': safe_name
        }
    })


@app.route('/api/voices/<voice_id>', methods=['DELETE'])
def delete_voice(voice_id):
    """Delete a voice sample"""
    filepath = os.path.join(VOICES_FOLDER, secure_filename(voice_id))
    if os.path.exists(filepath):
        os.remove(filepath)
        return jsonify({'success': True})
    return jsonify({'error': 'Voice not found'}), 404


@app.route('/api/convert', methods=['POST'])
def convert():
    data = request.get_json()
    youtube_url = data.get('url', '').strip()
    debug_mode = data.get('debug', False)
    main_voice = data.get('main_voice', None)  # Voice for main vocals
    sub_voice = data.get('sub_voice', None)    # Voice for sub-vocals (deep male)

    # DEBUG: Log received parameters
    print(f"=== CONVERT REQUEST ===", flush=True)
    print(f"URL: {youtube_url}", flush=True)
    print(f"Debug: {debug_mode}", flush=True)
    print(f"Main Voice: {main_voice} (type: {type(main_voice)})", flush=True)
    print(f"Sub Voice: {sub_voice} (type: {type(sub_voice)})", flush=True)
    print(f"=======================", flush=True)

    if not youtube_url:
        return jsonify({'error': 'No URL provided'}), 400

    # Basic URL validation
    if not ('youtube.com' in youtube_url or 'youtu.be' in youtube_url):
        return jsonify({'error': 'Please provide a valid YouTube URL'}), 400

    # Validate voice files exist if specified
    if main_voice:
        main_voice_path = os.path.join(VOICES_FOLDER, secure_filename(main_voice))
        if not os.path.exists(main_voice_path):
            return jsonify({'error': f'Main voice "{main_voice}" not found'}), 400
    if sub_voice:
        sub_voice_path = os.path.join(VOICES_FOLDER, secure_filename(sub_voice))
        if not os.path.exists(sub_voice_path):
            return jsonify({'error': f'Sub voice "{sub_voice}" not found'}), 400

    # Generate job ID
    job_id = str(uuid.uuid4())[:8]
    save_job(job_id, {'status': 'queued', 'progress': 0, 'debug': debug_mode})

    # Start processing in background thread
    thread = threading.Thread(target=process_nightcore, args=(job_id, youtube_url, debug_mode, main_voice, sub_voice))
    thread.start()

    return jsonify({'job_id': job_id})


@app.route('/api/status/<job_id>')
def status(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


@app.route('/api/download/<job_id>')
def download(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({'error': 'Job not found'}), 404

    if job.get('status') != 'complete':
        return jsonify({'error': 'File not ready'}), 400

    return send_file(
        job['file'],
        mimetype='audio/mpeg',
        as_attachment=True,
        download_name=job.get('filename', f'nightcore_{job_id}.mp3')
    )


@app.route('/api/debug/<job_id>/<track_type>')
def debug_download(job_id, track_type):
    """Download debug tracks: vocals, instrumental, or sub_vocals"""
    job = get_job(job_id)
    if job is None:
        return jsonify({'error': 'Job not found'}), 404

    if job.get('status') != 'complete':
        return jsonify({'error': 'File not ready'}), 400

    if not job.get('debug_files'):
        return jsonify({'error': 'Debug files not available. Enable debug mode when converting.'}), 400

    if track_type not in job['debug_files']:
        return jsonify({'error': f'Invalid track type. Use: vocals, instrumental, or sub_vocals'}), 400

    file_path = job['debug_files'][track_type]
    if not os.path.exists(file_path):
        return jsonify({'error': 'Debug file not found'}), 404

    title = job.get('title', 'Nightcore Track').replace('[NiGHTCoRE] ', '')
    filename = f'{title} - {track_type}.mp3'

    return send_file(
        file_path,
        mimetype='audio/mpeg',
        as_attachment=True,
        download_name=filename
    )


@app.route('/api/stream/<job_id>')
def stream(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({'error': 'Job not found'}), 404

    if job.get('status') != 'complete':
        return jsonify({'error': 'File not ready'}), 400

    file_path = job['file']
    file_size = os.path.getsize(file_path)

    # Handle range requests for proper audio streaming
    range_header = request.headers.get('Range')

    if range_header:
        # Parse range header
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else file_size - 1

            if start >= file_size:
                return Response(status=416)  # Range not satisfiable

            end = min(end, file_size - 1)
            length = end - start + 1

            def generate():
                with open(file_path, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk_size = min(8192, remaining)
                        data = f.read(chunk_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            response = Response(
                generate(),
                status=206,
                mimetype='audio/mpeg',
                direct_passthrough=True
            )
            response.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response.headers['Accept-Ranges'] = 'bytes'
            response.headers['Content-Length'] = length
            return response

    # No range request - return full file
    return send_file(file_path, mimetype='audio/mpeg')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
