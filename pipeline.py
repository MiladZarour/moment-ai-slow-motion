"""On-demand RIFE interpolation. Upload never invokes the AI engine."""
from pathlib import Path
import json
import math
import shutil
import subprocess
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
ENGINE = ROOT / 'tools/rife-ncnn-vulkan-20221029-windows'
JOBS = {}
LOCK = threading.RLock()
GPU = threading.Semaphore(1)
CANCEL = {}
CHUNK_SECONDS = .5
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
GEOMETRY = "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1"
SCALE = GEOMETRY + ',fps=30'
PREVIEW_GEOMETRY = "scale=w='min(960,iw)':h='min(540,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1"
PREVIEW_SCALE = PREVIEW_GEOMETRY + ',fps=30'
BATCH_WINDOWS = 4


def update(item, **values):
    with LOCK:
        item.update(values)


def run(args, log):
    with open(log, 'ab') as output:
        result = subprocess.run([str(x) for x in args], stdout=output, stderr=output,
                                creationflags=NO_WINDOW)
    if result.returncode:
        raise RuntimeError(f'{Path(str(args[0])).name} failed. Details: {Path(log).name}')


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                            '-of', 'json', str(path)], capture_output=True, text=True,
                            creationflags=NO_WINDOW, check=True)
    return json.loads(result.stdout)


def remember(job):
    keys = ('id', 'phase', 'progress', 'duration', 'audio', 'playbackFile', 'sourceMime', 'preview', 'directPlayback', 'message')
    manifest = DATA / job['id'] / 'job.json'
    temporary = manifest.with_suffix('.tmp')
    temporary.write_text(json.dumps({key: job[key] for key in keys if key in job}), encoding='utf-8')
    temporary.replace(manifest)


def restore_jobs():
    for manifest in DATA.glob('*/job.json'):
        try:
            job = json.loads(manifest.read_text(encoding='utf-8'))
            if job['id'] != manifest.parent.name or len(job['id']) != 32 or any(c not in '0123456789abcdef' for c in job['id']):
                continue
            if job['playbackFile'] not in ('source', 'preview.mp4') or not (manifest.parent / job['playbackFile']).is_file():
                continue
            if not math.isfinite(job['duration']) or job['duration'] <= 0:
                continue
            job.update(chunks={}, sessions={}, aiInvocations=0)
            JOBS[job['id']] = job
        except (ValueError, KeyError, TypeError, OSError):
            continue


def prepare(job):
    folder = DATA / job['id']
    try:
        update(job, phase='checking', message='Reading video metadata...', progress=None)
        info = probe(folder / 'source')
        stream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
        if not stream:
            raise ValueError('No video stream found.')
        duration = float(stream.get('duration') or info['format'].get('duration') or 0)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('The video must have a valid, positive duration.')
        audio = any(s['codec_type'] == 'audio' for s in info['streams'])
        if job.get('directPlayback'):
            formats = info['format'].get('format_name', '')
            mime = 'video/webm' if 'webm' in formats else 'video/mp4' if 'mp4' in formats else 'video/x-matroska'
            update(job, phase='ready', progress=100, duration=duration, audio=audio,
                   playbackFile='source', sourceMime=mime,
                   preview=f'/media/{job["id"]}/source', chunks={}, sessions={}, aiInvocations=0,
                   message='Playing the original video. No conversion needed. AI starts when you hold.')
            remember(job)
            return
        update(job, phase='converting', message='Converting an incompatible format for browser playback...', progress=0)
        args = ['ffmpeg', '-hide_banner', '-y', '-progress', 'pipe:1', '-nostats', '-i', folder / 'source', '-t', str(duration),
             '-map', '0:v:0', '-map', '0:a:0?', '-vf', SCALE, '-c:v', 'libx264',
             '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-g', '15',
             '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', folder / 'preview.mp4']
        with (folder / 'processing.log').open('ab') as log:
            process = subprocess.Popen([str(x) for x in args], stdout=subprocess.PIPE, stderr=log,
                                       text=True, creationflags=NO_WINDOW)
            for line in process.stdout:
                if line.startswith('out_time_us='):
                    try:
                        seconds = max(0, int(line.split('=', 1)[1]) / 1_000_000)
                        update(job, progress=min(99, round(seconds / duration * 100, 1)), convertedSeconds=seconds)
                    except ValueError:
                        pass
            if process.wait():
                raise RuntimeError('Video conversion failed. See processing.log in the video data folder.')
        info = probe(folder / 'preview.mp4')
        stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
        if int(stream.get('nb_frames', 0)) < 2:
            raise ValueError('At least two video frames are required.')
        update(job, phase='ready', progress=100, duration=float(stream['duration']),
               audio=any(s['codec_type'] == 'audio' for s in info['streams']),
               playbackFile='preview.mp4', preview=f'/media/{job["id"]}/preview.mp4', chunks={}, sessions={}, aiInvocations=0,
               message='Ready to play. AI starts only when you hold the corner.')
        remember(job)
    except Exception as error:
        update(job, phase='error', progress=0, message=str(error))


def live(job, session, active):
    if not isinstance(session, str) or not 1 <= len(session) <= 80:
        raise ValueError('Invalid hold session.')
    with LOCK:
        # A released session cannot be reactivated by a late arriving start request.
        if not active:
            job['sessions'][session] = False
            for chunk in job['chunks'].values():
                if chunk.get('session') == session and chunk['phase'] not in ('ready', 'error', 'cancelled'):
                    CANCEL[chunk['token']].set()
        elif session not in job['sessions']:
            job['sessions'][session] = True
        return {'active': job['sessions'][session]}


def request_chunk(job, index, session):
    if type(index) is not int or not 0 <= index < math.ceil(job['duration'] / CHUNK_SECONDS):
        raise ValueError('Invalid frame window.')
    with LOCK:
        if not job['sessions'].get(session):
            raise ValueError('This hold was released.')
        key = str(index)
        previous = job['chunks'].get(key)
        if previous and (previous['phase'] == 'ready' or
                (previous['phase'] in ('queued', 'decoding', 'interpolating', 'encoding') and
                 not CANCEL[previous['token']].is_set())):
            return dict(previous)
        token = uuid.uuid4().hex
        CANCEL[token] = threading.Event()
        batch = []
        for offset in range(BATCH_WINDOWS):
            cursor = index + offset
            if cursor * CHUNK_SECONDS >= job['duration']:
                break
            previous = job['chunks'].get(str(cursor))
            if offset and previous and previous['phase'] == 'ready':
                break
            chunk = {'index': cursor, 'token': token, 'session': session, 'phase': 'queued', 'progress': 0,
                     'start': cursor * CHUNK_SECONDS,
                     'end': min(job['duration'], (cursor + 1) * CHUNK_SECONDS)}
            job['chunks'][str(cursor)] = chunk
            batch.append(chunk)
        threading.Thread(target=generate_batch, args=(job, batch), daemon=True).start()
        return dict(batch[0])


def generate_batch(job, batch):
    """One model load per batch; publish windows while RIFE continues generating."""
    token = batch[0]['token']
    cancelled = CANCEL[token]
    folder = DATA / job['id']
    work = folder / f'work-{token}'
    frame_in, frame_out = work / 'in', work / 'out'
    log = folder / 'ai.log'
    started = time.monotonic()
    process = None
    try:
        with GPU:
            if cancelled.is_set():
                raise InterruptedError()
            frame_in.mkdir(parents=True); frame_out.mkdir()
            for chunk in batch:
                update(chunk, phase='decoding', progress=5)
            length = batch[-1]['end'] - batch[0]['start']
            decode_start = time.monotonic()
            run(['ffmpeg', '-hide_banner', '-y', '-ss', str(batch[0]['start']), '-i', folder / job['playbackFile'],
                 '-t', str(length + 1 / 30), '-an', '-vf', PREVIEW_SCALE, '-q:v', '2', frame_in / '%08d.jpg'], log)
            count = len(list(frame_in.glob('*.jpg')))
            if count == 0:
                raise ValueError('No frames found at this position.')
            expected = math.ceil(length * 30 - 1e-6) + 1
            while count < expected:
                shutil.copyfile(frame_in / f'{count:08}.jpg', frame_in / f'{count+1:08}.jpg'); count += 1
            if cancelled.is_set():
                raise InterruptedError()
            target = (count - 1) * 4 + 1
            decode_seconds = time.monotonic() - decode_start
            with LOCK:
                job['aiInvocations'] += 1
            for chunk in batch:
                update(chunk, phase='interpolating', progress=10, previewHeight=540)
            with open(log, 'ab') as output:
                process = subprocess.Popen([str(ENGINE / 'rife-ncnn-vulkan.exe'), '-i', str(frame_in),
                    '-o', str(frame_out), '-m', str(ENGINE / 'rife-v4.6'), '-n', str(target),
                    '-j', '2:2:1', '-f', '%08d.jpg'], stdout=output, stderr=output, creationflags=NO_WINDOW)
                for chunk in batch:
                    offset = round((chunk['start'] - batch[0]['start']) * 120)
                    frames = max(1, round((chunk['end'] - chunk['start']) * 120))
                    required = [frame_out / f'{n:08}.jpg' for n in range(offset + 1, offset + frames + 1)]
                    previous_sizes = None
                    while True:
                        if cancelled.wait(.04):
                            raise InterruptedError()
                        sizes = tuple(p.stat().st_size if p.exists() else 0 for p in required)
                        if all(sizes) and sizes == previous_sizes:
                            break
                        previous_sizes = sizes
                        if process.poll() is not None and (process.returncode or not all(sizes)):
                            raise RuntimeError('RIFE could not finish the frame window. See ai.log.')
                    update(chunk, phase='encoding', progress=90)
                    name = f'chunk-{token}-{chunk["index"]}.mp4'
                    run(['ffmpeg', '-hide_banner', '-y', '-framerate', '120', '-start_number', str(offset + 1),
                        '-i', frame_out / '%08d.jpg', '-frames:v', str(frames), '-an',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
                        '-profile:v', 'baseline', '-level:v', '4.2', '-crf', '18', '-pix_fmt', 'yuv420p',
                        '-g', '60', '-keyint_min', '60', '-sc_threshold', '0', '-video_track_timescale', '15360',
                        '-movflags', '+frag_keyframe+empty_moov+default_base_moof', folder / name], log)
                    if cancelled.is_set():
                        (folder / name).unlink(missing_ok=True)
                        raise InterruptedError()
                    update(chunk, phase='ready', progress=100, url=f'/media/{job["id"]}/{name}',
                           seconds=round(time.monotonic() - started, 2), decodeSeconds=round(decode_seconds, 2))
                if process.wait():
                    raise RuntimeError('RIFE inference failed.')
    except InterruptedError:
        for chunk in batch:
            if chunk['phase'] != 'ready':
                update(chunk, phase='cancelled', progress=0)
    except Exception as error:
        for chunk in batch:
            if chunk['phase'] != 'ready':
                update(chunk, phase='error', message=str(error))
    finally:
        if process is not None and process.poll() is None:
            process.terminate(); process.wait()
        if work.is_dir() and work.parent.resolve() == folder.resolve():
            shutil.rmtree(work)


def generate_chunk(job, chunk):
    token = chunk['token']
    cancelled = CANCEL[token]
    folder = DATA / job['id']
    work = folder / f'work-{token}'
    frame_in, frame_out = work / 'in', work / 'out'
    log = folder / 'ai.log'
    started = time.monotonic()
    try:
        with GPU:
            if cancelled.is_set():
                raise InterruptedError()
            frame_in.mkdir(parents=True)
            frame_out.mkdir()
            update(chunk, phase='decoding', progress=5)
            # Include the next real frame to interpolate the last interval correctly.
            run(['ffmpeg', '-hide_banner', '-y', '-ss', str(chunk['start']), '-i', folder / job['playbackFile'],
                 '-t', str(chunk['end'] - chunk['start'] + 1 / 30), '-an', '-vf', SCALE,
                 '-q:v', '2', frame_in / '%08d.jpg'], log)
            count = len(list(frame_in.glob('*.jpg')))
            expected = round((chunk['end'] - chunk['start']) * 30) + 1
            if count < 1:
                raise ValueError('No source frames found in this window.')
            while count < expected:
                shutil.copyfile(frame_in / f'{count:08}.jpg', frame_in / f'{count + 1:08}.jpg')
                count += 1
            if cancelled.is_set():
                raise InterruptedError()
            target = (count - 1) * 4 + 1
            update(chunk, phase='interpolating', progress=10, inputFrames=count, outputFrames=target)
            with LOCK:
                job['aiInvocations'] += 1
            with open(log, 'ab') as output:
                process = subprocess.Popen([str(ENGINE / 'rife-ncnn-vulkan.exe'), '-i', str(frame_in),
                    '-o', str(frame_out), '-m', str(ENGINE / 'rife-v4.6'), '-n', str(target),
                    '-j', '2:2:2', '-f', '%08d.jpg'], stdout=output, stderr=output, creationflags=NO_WINDOW)
                while process.poll() is None:
                    if cancelled.wait(.05):
                        process.terminate()
                        process.wait()
                        raise InterruptedError()
                if process.returncode:
                    raise RuntimeError('RIFE failed. See ai.log in the video data folder.')
            if cancelled.is_set():
                raise InterruptedError()
            files = sorted(frame_out.glob('*.jpg'))
            if len(files) != target:
                raise RuntimeError('AI frame generation was incomplete.')
            update(chunk, phase='encoding', progress=90)
            name = f'chunk-{token}.mp4'
            run(['ffmpeg', '-hide_banner', '-y', '-framerate', '120', '-start_number', str(int(files[0].stem)),
                 '-i', frame_out / '%08d.jpg', '-ss', str(chunk['start']), '-i', folder / job['playbackFile'],
                 '-map', '0:v:0', '-map', '1:a:0?', '-t', str(chunk['end'] - chunk['start']),
                 '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-pix_fmt', 'yuv420p',
                 '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', folder / name], log)
            if cancelled.is_set():
                (folder / name).unlink(missing_ok=True)
                raise InterruptedError()
            update(chunk, phase='ready', progress=100, url=f'/media/{job["id"]}/{name}',
                   seconds=round(time.monotonic() - started, 2))
    except InterruptedError:
        update(chunk, phase='cancelled', progress=0)
    except Exception as error:
        update(chunk, phase='error', message=str(error))
    finally:
        if work.is_dir() and work.parent.resolve() == folder.resolve():
            shutil.rmtree(work)


def export_video(job, segments, scope='full'):
    folder = DATA / job['id']
    work = folder / f'export-{uuid.uuid4().hex}'
    work.mkdir()
    log = folder / 'export.log'
    try:
        pieces = []
        # Smooth playback uses 540p previews; render requested slow sections at 720p
        # for saving. This work happens only after the user explicitly saves.
        hd_cache = job.setdefault('exportChunks', {})
        needed = sorted({index for start, end, speed in segments if speed != 1
                         for index in range(int((start + 1e-7) / CHUNK_SECONDS), math.ceil((end - 1e-7) / CHUNK_SECONDS))})
        for index in needed:
            preview = job['chunks'].get(str(index))
            if not preview or preview['phase'] != 'ready':
                raise ValueError('Replay this section while holding to generate its AI frames before saving.')
            if hd_cache.get(str(index), {}).get('phase') == 'ready':
                continue
            token = uuid.uuid4().hex
            CANCEL[token] = threading.Event()
            hd = {'index': index, 'token': token, 'session': 'export', 'phase': 'queued', 'start': preview['start'], 'end': preview['end']}
            generate_chunk(job, hd)
            if hd['phase'] != 'ready':
                raise RuntimeError(hd.get('message', 'Could not render the saved section.'))
            hd_cache[str(index)] = hd
            update(job, exportProgress=round(40 * (needed.index(index) + 1) / len(needed)))
        for start, end, speed in segments:
            cursor = start
            while cursor < end - 1e-7:
                if speed == 1:
                    pieces.append((folder / job['playbackFile'], cursor, end - cursor, speed))
                    break
                index = int((cursor + 1e-7) / CHUNK_SECONDS)
                chunk = hd_cache.get(str(index))
                if not chunk or chunk['phase'] != 'ready':
                    raise ValueError('A marked section has no AI frames. Replay that section while holding before saving.')
                stop = min(end, chunk['end'])
                pieces.append((folder / chunk['url'].split('/')[-1], cursor - chunk['start'], stop - cursor, speed))
                cursor = stop
        for i, (source, start, length, speed) in enumerate(pieces):
            run(['ffmpeg', '-hide_banner', '-y', '-ss', str(start), '-t', str(length), '-i', source,
                 '-an', '-vf', f'{GEOMETRY},setpts=(PTS-STARTPTS)/{speed},fps=30', '-t', str(length / speed),
                 '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                 '-video_track_timescale', '15360', work / f'{i:04}.mp4'], log)
            update(job, exportProgress=round(40 + (i + 1) / len(pieces) * 50))
        listing = work / 'concat.txt'
        listing.write_text('\n'.join(f"file '{i:04}.mp4'" for i in range(len(pieces))), encoding='utf-8')
        name = f'moment-{"section-" if scope == "section" else ""}{uuid.uuid4().hex[:8]}.mp4'
        args = ['ffmpeg', '-hide_banner', '-y', '-f', 'concat', '-safe', '0', '-i', listing]
        if job['audio']:
            filters, labels = [], []
            for i, (start, end, speed) in enumerate(segments):
                tempo = 'atempo=0.5,atempo=0.5' if speed == .25 else f'atempo={speed}'
                filters.append(f'[1:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,{tempo},apad,atrim=duration={(end-start)/speed}[a{i}]')
                labels.append(f'[a{i}]')
            filters.append(''.join(labels) + f'concat=n={len(segments)}:v=0:a=1[a]')
            args += ['-i', folder / job['playbackFile'], '-filter_complex', ';'.join(filters),
                     '-map', '0:v:0', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k']
        else:
            args += ['-map', '0:v:0']
        args += ['-c:v', 'copy', '-movflags', '+faststart', folder / name]
        run(args, log)
        update(job, exportState='ready', exportProgress=100, download=f'/media/{job["id"]}/{name}')
    except Exception as error:
        update(job, exportState='error', exportMessage=str(error))
    finally:
        if work.parent.resolve() == folder.resolve():
            shutil.rmtree(work)
