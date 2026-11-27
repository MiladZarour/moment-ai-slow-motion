"""Local-only RIFE video preparation and edited MP4 export. Python stdlib only."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import argparse
import json
import math
import shutil
import threading
import uuid

import pipeline
ROOT, DATA, ENGINE = pipeline.ROOT, pipeline.DATA, pipeline.ENGINE
JOBS, LOCK, GPU = pipeline.JOBS, pipeline.LOCK, pipeline.GPU
update, probe, prepare = pipeline.update, pipeline.probe, pipeline.prepare


def sections(holds, duration, fps=30):
    """Resolve overlapping takes with the most recently recorded hold winning."""
    # Snap edits to output frames. Near-adjacent pointer/keyboard holds can otherwise
    # leave sub-frame gaps that contain no decodable frame during segment export.
    fps = float(pipeline.Fraction(fps))
    duration = round(duration * fps) / fps
    cleaned = []
    if not isinstance(holds, list) or len(holds) > 50:
        raise ValueError('A maximum of 50 slow-motion sections is supported per export.')
    for hold in holds:
        start, end, speed = (float(hold[k]) for k in ('start', 'end', 'speed'))
        if not all(math.isfinite(v) for v in (start, end, speed)) or speed not in (.125, .25, .5):
            raise ValueError('Invalid slow-motion section.')
        start = max(0, min(duration, round(start * fps) / fps))
        end = max(0, min(duration, round(end * fps) / fps))
        if end - start >= 1 / fps - 1e-8:
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


export_video = pipeline.export_video


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
            return self.json({'engine': (ENGINE / 'rife-ncnn-vulkan.exe').exists(), 'apiVersion': 6, 'slowFactors': [2, 4, 8], 'maxSeconds': None, 'maxBytes': None, 'sectionExport': True})
        if path.startswith('/api/jobs/'):
            candidate = JOBS.get(path.split('/')[-1])
            if candidate and candidate['phase'] == 'ready':
                pipeline.ensure_timing(candidate)
            with LOCK:
                job = json.loads(json.dumps(JOBS.get(path.split('/')[-1], {})))
            return self.json(job or {'message': 'Job not found'}, 200 if job else 404)
        if path.startswith('/api/chunks/'):
            parts = path.strip('/').split('/')
            with LOCK:
                job = JOBS.get(parts[2]) if len(parts) == 4 else None
                chunk = dict(job.get('chunks', {}).get(parts[3], {})) if job else {}
            return self.json(chunk or {'message': 'Frame window not found'}, 200 if chunk else 404)
        if path.startswith('/media/'):
            parts = path.strip('/').split('/')
            if len(parts) != 3 or parts[1] not in JOBS or not (parts[2] in ('source', 'preview.mp4') or
                    (parts[2].startswith(('moment-', 'chunk-')) and parts[2].endswith('.mp4') and '/' not in parts[2])):
                return self.send_error(404)
            media = DATA / parts[1] / parts[2]
            if not media.is_file():
                return self.send_error(404)
            return self.media(media)
        if path not in ('/', '/index.html', '/style.css', '/app.js', '/live.js'):
            return self.send_error(404)
        super().do_GET()

    def do_HEAD(self):
        # Static/media GET handles Range; no arbitrary filesystem paths via HEAD.
        if urlparse(self.path).path not in ('/', '/index.html', '/style.css', '/app.js', '/live.js'):
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
        mime = JOBS.get(path.parent.name, {}).get('sourceMime', 'application/octet-stream') if path.name == 'source' else 'video/mp4'
        self.send_header('Content-Type', mime)
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
                    busy = any(j['phase'] not in ('ready', 'error') or j.get('exportState') == 'rendering' or any(c['phase'] in ('queued', 'decoding', 'interpolating', 'encoding') for c in j.get('chunks', {}).values()) for j in JOBS.values())
                if busy:
                    return self.json({'message': 'Wait until video processing and export finish before stopping.'}, 409)
                self.json({'message': 'Moment stopped. Your saved files remain in the data folder.'})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if path == '/api/upload':
                if length <= 0:
                    return self.json({'message': 'Choose a non-empty video file.'}, 400)
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
                job = {'id': identity, 'phase': 'queued', 'progress': None, 'message': 'Video received.', 'aiInvocations': 0,
                       'directPlayback': self.headers.get('X-Moment-Direct') == '1'}
                with LOCK:
                    JOBS[identity] = job
                threading.Thread(target=prepare, args=(job,), daemon=True).start()
                return self.json({'id': identity}, 202)
            if path.startswith(('/api/live/', '/api/chunks/')):
                if not 0 < length <= 4096:
                    raise ValueError('Invalid hold request.')
                with LOCK:
                    job = JOBS.get(path.split('/')[-1])
                if not job or job['phase'] != 'ready':
                    return self.json({'message': 'Normal playback is still being prepared.'}, 409)
                body = json.loads(self.rfile.read(length))
                if path.startswith('/api/live/'):
                    result = pipeline.live(job, body.get('session'), body.get('active') is True, body.get('factor', 4))
                else:
                    if job.get('exportState') == 'rendering':
                        return self.json({'message': 'Wait until saving finishes.'}, 409)
                    result = pipeline.request_chunk(job, body.get('index'), body.get('session'))
                return self.json(result)
            if path.startswith('/api/export/'):
                if length <= 0 or length > 65536:
                    return self.json({'message': 'Invalid export request.'}, 400)
                with LOCK:
                    job = JOBS.get(path.split('/')[-1])
                    if not job or job['phase'] != 'ready':
                        return self.json({'message': 'Wait until AI preparation finishes.'}, 409)
                    if job.get('exportState') == 'rendering':
                        return self.json({'message': 'An export is already running.'}, 409)
                body = json.loads(self.rfile.read(length))
                holds = body.get('holds')
                scope = body.get('scope', 'full')
                if scope not in ('full', 'section'):
                    raise ValueError('Invalid export scope.')
                if not holds:
                    raise ValueError('Hold the corner to mark a section before saving.')
                if scope == 'section' and (not isinstance(holds, list) or len(holds) != 1):
                    raise ValueError('Select exactly one slow-motion section.')
                pipeline.ensure_timing(job)
                segments = sections(holds, job['duration'], job['sourceFps'])
                if scope == 'section':
                    segments = [segment for segment in segments if segment[2] != 1]
                    if not segments:
                        raise ValueError('The selected section is shorter than one output frame.')
                update(job, exportState='rendering', exportProgress=0, download=None, exportScope=scope)
                threading.Thread(target=export_video, args=(job, segments, scope), daemon=True).start()
                return self.json({'message': 'Export started.'}, 202)
            self.json({'message': 'Not found'}, 404)
        except (ValueError, KeyError, TypeError) as error:
            self.json({'message': str(error)}, 400)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    if not (ENGINE / 'rife-ncnn-vulkan.exe').exists():
        raise SystemExit('RIFE is missing. Run setup.ps1 first.')
    if not all(shutil.which(command) for command in ('ffmpeg', 'ffprobe')):
        raise SystemExit('FFmpeg and ffprobe must be installed and available on PATH.')
    DATA.mkdir(exist_ok=True)
    pipeline.restore_jobs()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Moment is running at http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
