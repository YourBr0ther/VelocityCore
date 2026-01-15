import os
import subprocess
import uuid
import threading
import time
import re
import json
from flask import Flask, render_template, request, jsonify, send_file, Response

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
LIBRARY_FILE = '/app/jobs/library.json'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(JOBS_FOLDER, exist_ok=True)
os.makedirs(SEPARATED_FOLDER, exist_ok=True)


def get_library():
    """Read the track library"""
    if os.path.exists(LIBRARY_FILE):
        try:
            with open(LIBRARY_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return []


def save_library(library):
    """Save the track library"""
    with open(LIBRARY_FILE, 'w') as f:
        json.dump(library, f, indent=2)


def add_to_library(job_id, title, filename, file_path):
    """Add a completed track to the library"""
    library = get_library()

    # Check if already exists
    for track in library:
        if track['job_id'] == job_id:
            return

    library.insert(0, {
        'job_id': job_id,
        'title': title,
        'filename': filename,
        'file': file_path,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    })

    save_library(library)


def remove_from_library(job_id):
    """Remove a track from the library and delete its file"""
    library = get_library()
    track_to_remove = None

    for track in library:
        if track['job_id'] == job_id:
            track_to_remove = track
            break

    if track_to_remove:
        # Delete the audio file
        if os.path.exists(track_to_remove['file']):
            try:
                os.remove(track_to_remove['file'])
            except:
                pass

        # Delete the job file
        job_file = os.path.join(JOBS_FOLDER, f'{job_id}.json')
        if os.path.exists(job_file):
            try:
                os.remove(job_file)
            except:
                pass

        # Remove from library
        library = [t for t in library if t['job_id'] != job_id]
        save_library(library)
        return True

    return False


def get_library_job_ids():
    """Get set of job IDs in the library (for cleanup exclusion)"""
    library = get_library()
    return {track['job_id'] for track in library}


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
    """Remove files older than 1 hour, but preserve library tracks"""
    while True:
        time.sleep(300)  # Check every 5 minutes
        try:
            now = time.time()
            library_ids = get_library_job_ids()

            # Clean up downloads (skip library tracks)
            for filename in os.listdir(DOWNLOAD_FOLDER):
                filepath = os.path.join(DOWNLOAD_FOLDER, filename)
                if os.path.isfile(filepath) and now - os.path.getmtime(filepath) > 3600:
                    # Check if this file belongs to a library track
                    job_id = filename.split('_')[0] if '_' in filename else None
                    if job_id not in library_ids:
                        os.remove(filepath)

            # Clean up job files (skip library tracks and library.json)
            for filename in os.listdir(JOBS_FOLDER):
                if filename == 'library.json':
                    continue
                filepath = os.path.join(JOBS_FOLDER, filename)
                if os.path.isfile(filepath) and now - os.path.getmtime(filepath) > 3600:
                    job_id = filename.replace('.json', '')
                    if job_id not in library_ids:
                        os.remove(filepath)
        except Exception:
            pass


# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()


def process_nightcore(job_id, youtube_url, debug_mode=False):
    """Download from YouTube and convert to nightcore with vocal sub-layer"""
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

            save_job(job_id, {'status': 'processing', 'progress': 60})

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

        # Add to library for sidebar playback
        add_to_library(job_id, job_result['title'], job_result['filename'], nightcore_file)

    except subprocess.TimeoutExpired:
        save_job(job_id, {'status': 'error', 'message': 'Processing timed out.'})
    except Exception as e:
        save_job(job_id, {'status': 'error', 'message': str(e)})


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/convert', methods=['POST'])
def convert():
    data = request.get_json()
    youtube_url = data.get('url', '').strip()
    debug_mode = data.get('debug', False)

    if not youtube_url:
        return jsonify({'error': 'No URL provided'}), 400

    # Basic URL validation
    if not ('youtube.com' in youtube_url or 'youtu.be' in youtube_url):
        return jsonify({'error': 'Please provide a valid YouTube URL'}), 400

    # Generate job ID
    job_id = str(uuid.uuid4())[:8]
    save_job(job_id, {'status': 'queued', 'progress': 0, 'debug': debug_mode})

    # Start processing in background thread
    thread = threading.Thread(target=process_nightcore, args=(job_id, youtube_url, debug_mode))
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


@app.route('/api/library', methods=['GET'])
def list_library():
    """List all tracks in the library"""
    library = get_library()
    # Filter out tracks whose files no longer exist
    valid_tracks = []
    for track in library:
        if os.path.exists(track['file']):
            valid_tracks.append(track)
    return jsonify({'tracks': valid_tracks})


@app.route('/api/library/<job_id>', methods=['DELETE'])
def delete_from_library(job_id):
    """Delete a track from the library"""
    if remove_from_library(job_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Track not found'}), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
