"""Integration check against an already running local server; uses generated fixtures."""
from pathlib import Path
import json
import subprocess
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import probe

BASE = 'http://127.0.0.1:8766'


def request(path, data=None):
    req = Request(BASE + path, data=data, headers={'X-Moment-Client': '1'})
    with urlopen(req, timeout=60) as response:
        return json.load(response)


def wait(identity, field, expected):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        job = request('/api/jobs/' + identity)
        assert job.get('phase') != 'error', job
        assert job.get('exportState') != 'error', job
        if job.get(field) == expected:
            return job
        time.sleep(.5)
    raise TimeoutError(job)


if __name__ == '__main__':
    fixture = ROOT / 'tools/test-portrait.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                    '-i', 'testsrc2=size=180x320:rate=30', '-t', '1', '-an',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(fixture)], check=True)
    identity = request('/api/upload', fixture.read_bytes())['id']
    job = wait(identity, 'phase', 'ready')
    assert job['aiInvocations'] == 0 and job['chunks'] == {}, job
    assert job.get('convertedSeconds', 0) > 0, 'Fallback progress must come from actual FFmpeg output timestamps'
    assert job['audio'] is False
    preview = ROOT / 'data' / identity / 'preview.mp4'
    stream = probe(preview)['streams'][0]
    assert (stream['width'], stream['height'], stream['r_frame_rate']) == (180, 320, '30/1'), stream
    request('/api/live/' + identity, json.dumps({'session': 'integration', 'active': True}).encode())
    for index in (0, 1):
        request('/api/chunks/' + identity, json.dumps({'session': 'integration', 'index': index}).encode())
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        job = request('/api/jobs/' + identity)
        if all(c['phase'] == 'ready' for c in job['chunks'].values()):
            break
        assert not any(c['phase'] == 'error' for c in job['chunks'].values()), job
        time.sleep(.2)
    assert len(job['chunks']) == 2 and all(c['phase'] == 'ready' for c in job['chunks'].values()), job
    request('/api/live/' + identity, json.dumps({'session': 'integration', 'active': False}).encode())
    chunk_path = ROOT / 'data' / identity / job['chunks']['0']['url'].split('/')[-1]
    ai_stream = probe(chunk_path)['streams'][0]
    assert ai_stream['r_frame_rate'] == '120/1', ai_stream
    count = subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                    '-show_entries', 'stream=nb_read_frames', '-of', 'default=nw=1:nk=1', str(chunk_path)], text=True)
    assert int(count.strip()) == 60, count
    hashes = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(chunk_path), '-an',
                    '-frames:v', '8', '-f', 'framemd5', '-'], text=True)
    frames = [line.split(',')[-1].strip() for line in hashes.splitlines() if not line.startswith('#')]
    assert len(set(frames)) == 8, 'Expected distinct interpolated frames in this moving fixture'
    holds = [{'start': .2, 'end': .8, 'speed': .25}, {'start': .5, 'end': .8, 'speed': .5}]
    request('/api/export/' + identity, json.dumps({'holds': holds}).encode())
    job = wait(identity, 'exportState', 'ready')
    exported = ROOT / 'data' / identity / job['download'].split('/')[-1]
    streams = probe(exported)['streams']
    assert len(streams) == 1 and streams[0]['codec_type'] == 'video'
    # .2 normal + .3 quarter + .3 half + .2 normal = 2.2 seconds.
    assert abs(float(streams[0]['duration']) - 2.2) < .05, streams
    with urlopen(Request(BASE + job['preview'], headers={'Range': 'bytes=16-31'})) as response:
        assert response.status == 206 and len(response.read()) == 16
    print('PASS: silent portrait, zero AI on upload, on-demand 120fps windows, distinct frames, overlapping edits, 2.2s MP4, HTTP seeking.')
    print(json.dumps({'job': identity, 'aiInvocations': job['aiInvocations']}))
