"""On-demand, cached 60 fps accelerated video. Source recordings are read-only."""
import concurrent.futures
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import threading

_workers = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='replay-render')
_lock = threading.Lock()
_jobs = {}
BLOCK_SECONDS = 12


def plan(root, catalog, session, factor, block):
    if factor not in (16, 32, 64, 128, 256, 512, 1024) or block < 0:
        raise ValueError('Invalid preview position')
    clips = sorted((c for c in catalog if c['session'] == session), key=lambda c: c['file'][-19:])
    total = sum(c['duration'] for c in clips)
    start = block * factor * BLOCK_SECONDS
    end = min(total, start + factor * BLOCK_SECONDS)
    if not clips or start >= total:
        raise ValueError('Recording not found')
    selected, cursor, first_start = [], 0, None
    for clip in clips:
        if cursor < end and cursor + clip['duration'] > start:
            path = (root / session / clip['file']).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError('Recording not found')
            selected.append((path, clip['duration'], clip['bytes']))
            if first_start is None:
                first_start = cursor
        cursor += clip['duration']
    signature = json.dumps([factor, block, [(str(p), d, size) for p, d, size in selected]])
    key = hashlib.sha256(signature.encode()).hexdigest()[:40]
    return {'key': key, 'factor': factor, 'start': start, 'duration': end-start,
            'offset': start-first_start, 'clips': selected}


def _render(ffmpeg, folder, spec):
    key = spec['key']
    listing = folder / f'{key}.ffconcat'
    temporary = folder / f'{key}.partial.mp4'
    output = folder / f'{key}.mp4'
    try:
        lines = ['ffconcat version 1.0']
        for path, duration, _ in spec['clips']:
            escaped = path.as_posix().replace("'", "'\\''")
            lines += [f"file '{escaped}'", f'duration {duration:.8f}']
        listing.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        command = [str(ffmpeg), '-nostdin', '-hide_banner', '-loglevel', 'error', '-threads', '2']
        if spec['factor'] >= 256:
            command += ['-skip_frame', 'nokey']
        offset, end = spec['offset'], spec['offset']+spec['duration']
        filters = f"trim=start={offset}:end={end},setpts=(PTS-{offset}/TB)/{spec['factor']},fps=60:start_time=0"
        command += ['-f', 'concat', '-safe', '0', '-i', str(listing), '-an', '-vf', filters,
                    '-c:v', 'libx264', '-profile:v', 'baseline', '-level', '3.0', '-pix_fmt', 'yuv420p',
                    '-preset', 'ultrafast', '-crf', '24', '-threads', '2', '-g', '60', '-keyint_min', '60',
                    '-sc_threshold', '0', '-movflags', '+frag_keyframe+empty_moov+default_base_moof',
                    '-t', str(spec['duration']/spec['factor']), '-y', str(temporary)]
        result = subprocess.run(command, capture_output=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace')[-1000:])
        temporary.replace(output)
        with _lock:
            _jobs[key] = {'status': 'ready'}
    except Exception as error:
        with _lock:
            _jobs[key] = {'status': 'error', 'error': str(error)}
    finally:
        listing.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)


def request(root, catalog, session, factor, block, ffmpeg):
    if not ffmpeg or not Path(ffmpeg).is_file():
        raise ValueError('Replay renderer is not configured')
    spec = plan(root, catalog, session, factor, block)
    folder = root / '.replay-cache'
    folder.mkdir(exist_ok=True)
    key = spec['key']
    with _lock:
        if (folder / f'{key}.mp4').is_file():
            state = {'status': 'ready'}
        else:
            state = _jobs.get(key)
            if state is None:
                state = _jobs[key] = {'status': 'preparing'}
                _workers.submit(_render, ffmpeg, folder, spec)
        return {**state, 'id': key, 'start': spec['start'], 'duration': spec['duration'],
                'url': f'/api/camera/rendered?id={key}'}


def output_path(root, key):
    if not re.fullmatch('[0-9a-f]{40}', key):
        raise ValueError('Invalid preview')
    path = root / '.replay-cache' / f'{key}.mp4'
    if not path.is_file():
        raise ValueError('Preview not ready')
    return path
