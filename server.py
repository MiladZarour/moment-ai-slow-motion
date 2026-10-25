"""Local-only RIFE video preparation and edited MP4 export. Python stdlib only."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import argparse
import json
import math
import os
import shutil
import subprocess
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
ENGINE = ROOT / 'tools/rife-ncnn-vulkan-20221029-windows'
JOBS = {}
LOCK = threading.Lock()
GPU = threading.Semaphore(1)
MAX_BYTES = 1024 ** 3
MAX_SECONDS = 120
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def update(job, **values):
    with LOCK:
        job.update(values)


def run(args, log):
    with open(log, 'ab') as output:
        result = subprocess.run([str(x) for x in args], stdout=output, stderr=output,
                                creationflags=NO_WINDOW)
    if result.returncode:
        tail = Path(log).read_text(errors='replace')[-1800:]
        raise RuntimeError(f'{Path(str(args[0])).name} failed: {tail}')


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                             '-of', 'json', str(path)], capture_output=True, text=True,
                            creationflags=NO_WINDOW, check=True)
    return json.loads(result.stdout)


def prepare(job):
    folder = DATA / job['id']
    log = folder / 'processing.log'
    frame_in, frame_out = folder / 'frames', folder / 'interpolated'
    try:
        update(job, phase='queued', message='Waiting for the GPU…', progress=2)
        with GPU:
            update(job, phase='decoding', message='Reading video and preparing frames…', progress=4)
            info = probe(folder / 'source')
            stream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
            if not stream:
                raise ValueError('No video stream found. Choose a playable video.')
            duration = float(stream.get('duration') or info['format'].get('duration') or 0)
            if not math.isfinite(duration) or duration <= 0 or duration > MAX_SECONDS:
                raise ValueError(f'Please choose a video between 0 and {MAX_SECONDS} seconds long.')
            audio = any(s['codec_type'] == 'audio' for s in info['streams'])
            update(job, duration=duration, audio=audio)
            frame_in.mkdir()
            frame_out.mkdir()
            # Fixed 30 fps source / 120 fps prepared stream: smooth 30 fps at quarter speed.
            scale = "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1,fps=30"
            run(['ffmpeg', '-hide_banner', '-y', '-i', folder / 'source', '-map', '0:v:0',
                 '-t', str(duration), '-an', '-vf', scale, '-q:v', '2', frame_in / '%08d.jpg'], log)
            count = len(list(frame_in.glob('*.jpg')))
            if count < 2:
                raise ValueError('This video is too short. At least two frames are required.')
            target = count * 4
            update(job, phase='interpolating', message='Generating AI frames with RIFE…', progress=10,
                   inputFrames=count, outputFrames=target)
            started = time.monotonic()
            with open(log, 'ab') as output:
                process = subprocess.Popen([str(ENGINE / 'rife-ncnn-vulkan.exe'), '-i', str(frame_in),
                    '-o', str(frame_out), '-m', str(ENGINE / 'rife-v4.6'), '-n', str(target),
                    '-j', '2:2:2', '-f', '%08d.jpg'], stdout=output, stderr=output,
                    creationflags=NO_WINDOW)
                while process.poll() is None:
                    done = len(list(frame_out.glob('*.jpg')))
                    elapsed = time.monotonic() - started
                    update(job, progress=round(10 + 75 * done / target, 1), generatedFrames=done,
                           inferenceFps=round(done / max(elapsed, .01), 1))
                    time.sleep(.75)
                if process.returncode:
                    raise RuntimeError('RIFE could not process this video. See processing.log in its data folder.')
            inference_seconds = time.monotonic() - started
            files = sorted(frame_out.glob('*.jpg'))
            if len(files) != target:
                raise RuntimeError(f'RIFE produced {len(files)} of {target} expected frames.')
            update(job, phase='encoding', message='Encoding your AI-ready preview…', progress=88,
                   inferenceSeconds=round(inference_seconds, 2), inferenceFps=round(target / inference_seconds, 1))
            args = ['ffmpeg', '-hide_banner', '-y', '-framerate', '120', '-start_number',
                    str(int(files[0].stem)), '-i', frame_out / '%08d.jpg', '-i', folder / 'source',
                    '-map', '0:v:0', '-map', '1:a:0?', '-t', str(duration), '-c:v', 'libx264',
                    '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                    '-b:a', '192k', '-movflags', '+faststart', folder / 'preview.mp4']
            run(args, log)
            preview_info = probe(folder / 'preview.mp4')
            ready_duration = float(next(s for s in preview_info['streams'] if s['codec_type'] == 'video')['duration'])
            update(job, phase='ready', message='AI frames ready. Hold the corner to slow down.',
                   progress=100, duration=min(duration, ready_duration), preview=f'/media/{job["id"]}/preview.mp4')
    except Exception as error:
        update(job, phase='error', message=str(error), progress=0)
    finally:
        # These are only generated intermediates inside this job, never user files.
        for path in (frame_in, frame_out):
            if path.is_dir() and path.parent.resolve() == folder.resolve():
                shutil.rmtree(path)


def sections(holds, duration):
    """Resolve overlapping takes with the most recently recorded hold winning."""
    # Snap edits to output frames. Near-adjacent pointer/keyboard holds can otherwise
    # leave sub-frame gaps that contain no decodable frame during segment export.
    duration = round(duration * 30) / 30
    cleaned = []
    if not isinstance(holds, list) or len(holds) > 50:
        raise ValueError('A maximum of 50 slow-motion sections is supported per export.')
    for hold in holds:
        start, end, speed = (float(hold[k]) for k in ('start', 'end', 'speed'))
        if not all(math.isfinite(v) for v in (start, end, speed)) or speed not in (.25, .5):
            raise ValueError('Invalid slow-motion section.')
        start = max(0, min(duration, round(start * 30) / 30))
        end = max(0, min(duration, round(end * 30) / 30))
        if end - start >= 1 / 30 - 1e-8:
            cleaned.append((start, end, speed))
    boundaries = sorted({0., duration, *(x for s, e, _ in cleaned for x in (s, e))})
    output = []
    for start, end in zip(boundaries, boundaries[1:]):
        midpoint = (start + end) / 2
        speed = next((r for s, e, r in reversed(cleaned) if s <= midpoint < e), 1.)
        if output and output[-1][2] == speed:
            output[-1] = (output[-1][0], end, speed)
        else:
            output.append((start, end, speed))
    return output


def export_video(job, segments):
    folder = DATA / job['id']
    work = folder / f'export-{uuid.uuid4().hex}'
    work.mkdir()
    log = folder / 'export.log'
    try:
        with GPU:
            for index, (start, end, speed) in enumerate(segments):
                duration = (end - start) / speed
                filters = f'[0:v]setpts=(PTS-STARTPTS)/{speed},fps=30,setsar=1[v]'
                if job['audio']:
                    tempo = 'atempo=0.5,atempo=0.5' if speed == .25 else f'atempo={speed}'
                    filters += f';[0:a]asetpts=PTS-STARTPTS,{tempo},apad,atrim=duration={duration}[a]'
                args = ['ffmpeg', '-hide_banner', '-y', '-ss', str(start), '-t', str(end - start),
                        '-i', folder / 'preview.mp4', '-filter_complex', filters, '-map', '[v]']
                if job['audio']:
                    args += ['-map', '[a]', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000']
                args += ['-t', str(duration), '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                         '-pix_fmt', 'yuv420p', '-video_track_timescale', '15360', work / f'{index:03}.mp4']
                run(args, log)
                update(job, exportProgress=round((index + 1) / len(segments) * 95))
            listing = work / 'concat.txt'
            listing.write_text('\n'.join(f"file '{i:03}.mp4'" for i in range(len(segments))), encoding='utf-8')
            result_name = f'moment-{uuid.uuid4().hex[:8]}.mp4'
            run(['ffmpeg', '-hide_banner', '-y', '-f', 'concat', '-safe', '0', '-i', listing,
                 '-c', 'copy', '-movflags', '+faststart', folder / result_name], log)
            update(job, exportState='ready', exportProgress=100,
                   download=f'/media/{job["id"]}/{result_name}')
    except Exception as error:
        update(job, exportState='error', exportMessage=str(error))
    finally:
        if work.parent.resolve() == folder.resolve():
            shutil.rmtree(work)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def json(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
        if path == '/api/health':
            return self.json({'engine': (ENGINE / 'rife-ncnn-vulkan.exe').exists(), 'maxSeconds': MAX_SECONDS})
        if path.startswith('/api/jobs/'):
            with LOCK:
                job = dict(JOBS.get(path.split('/')[-1], {}))
            return self.json(job or {'message': 'Job not found'}, 200 if job else 404)
        if path.startswith('/media/'):
            parts = path.strip('/').split('/')
            if len(parts) != 3 or parts[1] not in JOBS or not (parts[2] == 'preview.mp4' or
                    (parts[2].startswith('moment-') and parts[2].endswith('.mp4') and '/' not in parts[2])):
                return self.send_error(404)
            media = DATA / parts[1] / parts[2]
            if not media.is_file():
                return self.send_error(404)
            return self.media(media)
        if path not in ('/', '/index.html', '/style.css', '/app.js'):
            return self.send_error(404)
        super().do_GET()

    def do_HEAD(self):
        # Static/media GET handles Range; no arbitrary filesystem paths via HEAD.
        if urlparse(self.path).path not in ('/', '/index.html', '/style.css', '/app.js'):
            return self.send_error(404)
        super().do_HEAD()

    def media(self, path):
        size = path.stat().st_size
        start, end, partial = 0, size - 1, False
        header = self.headers.get('Range')
        if header:
            try:
                unit, span = header.split('=', 1)
                first, last = span.split('-', 1)
                if unit != 'bytes' or ',' in span:
                    raise ValueError()
                if first:
                    start = int(first)
                    end = min(int(last), size - 1) if last else size - 1
                else:
                    start = max(0, size - int(last))
                if start < 0 or start > end or start >= size:
                    raise ValueError()
                partial = True
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type', 'video/mp4')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        if partial:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if path.name.startswith('moment-'):
            self.send_header('Content-Disposition', f'attachment; filename="{path.name}"')
        self.end_headers()
        try:
            with path.open('rb') as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_POST(self):
        # Browser cross-origin forms cannot set this header; reject remote origins too.
        origin = self.headers.get('Origin')
        expected_origin = f'http://127.0.0.1:{self.server.server_port}'
        if self.headers.get('X-Moment-Client') != '1' or (origin and origin != expected_origin):
            return self.json({'message': 'Open the app using its local launcher.'}, 403)
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get('Content-Length', 0))
            if path == '/api/stop':
                with LOCK:
                    busy = any(j['phase'] not in ('ready', 'error') or j.get('exportState') == 'rendering' for j in JOBS.values())
                if busy:
                    return self.json({'message': 'Wait until video processing and export finish before stopping.'}, 409)
                self.json({'message': 'Moment stopped. Your saved files remain in the data folder.'})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if path == '/api/upload':
                if length <= 0 or length > MAX_BYTES:
                    return self.json({'message': 'Choose a video smaller than 1 GB.'}, 413)
                with LOCK:
                    busy = any(j['phase'] not in ('ready', 'error') for j in JOBS.values())
                if busy:
                    return self.json({'message': 'A video is already being prepared. Wait for it to finish.'}, 409)
                identity = uuid.uuid4().hex
                folder = DATA / identity
                folder.mkdir(parents=True)
                remaining = length
                with (folder / 'source').open('wb') as output:
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError('Upload interrupted. Please try again.')
                        output.write(chunk)
                        remaining -= len(chunk)
                job = {'id': identity, 'phase': 'queued', 'progress': 0, 'message': 'Video received.'}
                with LOCK:
                    JOBS[identity] = job
                threading.Thread(target=prepare, args=(job,), daemon=True).start()
                return self.json({'id': identity}, 202)
            if path.startswith('/api/export/'):
                if length <= 0 or length > 65536:
                    return self.json({'message': 'Invalid export request.'}, 400)
                with LOCK:
                    job = JOBS.get(path.split('/')[-1])
                    if not job or job['phase'] != 'ready':
                        return self.json({'message': 'Wait until AI preparation finishes.'}, 409)
                    if job.get('exportState') == 'rendering':
                        return self.json({'message': 'An export is already running.'}, 409)
                holds = json.loads(self.rfile.read(length)).get('holds')
                if not holds:
                    raise ValueError('Hold the corner to mark a section before saving.')
                segments = sections(holds, job['duration'])
                update(job, exportState='rendering', exportProgress=0, download=None)
                threading.Thread(target=export_video, args=(job, segments), daemon=True).start()
                return self.json({'message': 'Export started.'}, 202)
            self.json({'message': 'Not found'}, 404)
        except (ValueError, KeyError, TypeError) as error:
            self.json({'message': str(error)}, 400)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not (ENGINE / 'rife-ncnn-vulkan.exe').exists():
        raise SystemExit('RIFE is missing. Run setup.ps1 first.')
    if not all(shutil.which(command) for command in ('ffmpeg', 'ffprobe')):
        raise SystemExit('FFmpeg and ffprobe must be installed and available on PATH.')
    DATA.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Moment is running at http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
