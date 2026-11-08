"""Read-only, range-enabled access to completed camera clips."""
import os
import pathlib
import re
import struct
import json
import subprocess
import time
import threading
from datetime import datetime
from functools import lru_cache

DEFAULT_ROOT = pathlib.Path('D:/Team18-Recordings' if os.name == 'nt' else '/mnt/d/Team18-Recordings')
_index_lock=threading.Lock()
_index=None
_index_time=0

def index(python=None):
    """Cache metadata; use the Windows worker for native external-drive I/O."""
    global _index, _index_time
    with _index_lock:
        if _index is None or time.monotonic()-_index_time>30:
            if os.name != 'nt' and python and str(python).lower().endswith('.exe'):
                code=pathlib.Path(__file__).read_text()+"\nprint(json.dumps(clips()))\n"
                result=subprocess.run([str(python),'-c',code],capture_output=True,text=True,timeout=60,check=True)
                _index=json.loads(result.stdout)
            else:
                _index=clips()
            _index_time=time.monotonic()
        return _index

@lru_cache(maxsize=2048)
def duration(filename, size, modified):
    """Read fragmented MP4 timing without decoding or loading video payloads."""
    scale, last = 1, 0
    def boxes(stream, stop):
        while stream.tell()+8 <= stop:
            start=stream.tell(); length, kind=struct.unpack('>I4s',stream.read(8))
            if length == 1: length=struct.unpack('>Q',stream.read(8))[0]
            if length == 0: length=stop-start
            if length < 8 or start+length > stop: break
            yield kind, start+length
            stream.seek(start+length)
    def walk(stream, stop):
        nonlocal scale,last
        base, default, total = 0, 0, 0
        for kind,end in boxes(stream,stop):
            if kind in (b'moov',b'trak',b'mdia',b'moof'):
                walk(stream,end)
            elif kind==b'traf': walk(stream,end)
            elif kind==b'mdhd':
                version=stream.read(1)[0];stream.read(3+(16 if version else 8));scale=struct.unpack('>I',stream.read(4))[0]
            elif kind==b'tfdt':
                version=stream.read(1)[0];stream.read(3);base=int.from_bytes(stream.read(8 if version else 4),'big')
            elif kind==b'tfhd':
                flags=int.from_bytes(stream.read(4),'big')&0xffffff;stream.read(4)
                if flags&1: stream.read(8)
                if flags&2: stream.read(4)
                if flags&8: default=int.from_bytes(stream.read(4),'big')
            elif kind==b'trun':
                flags=int.from_bytes(stream.read(4),'big')&0xffffff;count=int.from_bytes(stream.read(4),'big')
                if flags&1: stream.read(4)
                if flags&4: stream.read(4)
                for _ in range(count):
                    total+=int.from_bytes(stream.read(4),'big') if flags&0x100 else default
                    for flag in (0x200,0x400,0x800):
                        if flags&flag: stream.read(4)
        last=max(last,base+total)
    with open(filename,'rb') as stream: walk(stream,size)
    return last/scale


def clips(root=DEFAULT_ROOT):
    result = []
    if not root.is_dir():
        return result
    for session in sorted(root.iterdir(), reverse=True):
        if not session.is_dir() or session.is_symlink():
            continue
        files = sorted(session.glob('part-*.mp4'))
        # The recorder keeps its newest segment open. Only publish closed clips.
        status = session / 'status.json'
        import json
        try:
            active = json.loads(status.read_text()).get('recording', False)
        except (OSError, ValueError):
            active = False
        for path in reversed(files[:-1] if active else files):
            if path.is_symlink() or not path.stat().st_size:
                continue
            stat=path.stat()
            stamp=re.search(r'(\d{8}-\d{6})\.mp4$',path.name)
            started=datetime.strptime(stamp[1],'%Y%m%d-%H%M%S').astimezone().isoformat() if stamp else None
            result.append({'session': session.name, 'file': path.name, 'started_at':started,
                           'bytes': stat.st_size,
                           'duration':duration(str(path),stat.st_size,stat.st_mtime_ns)})
    return result


def serve(handler, root, session, filename, catalog=None):
    if not any(c['session'] == session and c['file'] == filename for c in (catalog if catalog is not None else clips(root))):
        return handler.send_error(404, 'Completed clip not found')
    path = (root / session / filename).resolve()
    if not path.is_relative_to(root.resolve()):
        return handler.send_error(404)
    return serve_file(handler,path)


def serve_file(handler,path):
    with path.open('rb') as stream:
        size = os.fstat(stream.fileno()).st_size
        start, end = 0, size - 1
        request = handler.headers.get('Range')
        if request:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', request)
            if not match or not any(match.groups()):
                handler.send_response(416)
                handler.send_header('Content-Range', f'bytes */{size}')
                handler.end_headers()
                return
            first, last = match.groups()
            start = int(first) if first else max(0, size-int(last))
            end = min(int(last), size-1) if first and last else size-1
            if start >= size or start > end:
                handler.send_response(416)
                handler.send_header('Content-Range', f'bytes */{size}')
                handler.end_headers()
                return
        handler.send_response(206 if request else 200)
        handler.send_header('Content-Type', 'video/mp4')
        handler.send_header('Accept-Ranges', 'bytes')
        handler.send_header('Content-Length', str(end-start+1))
        if request:
            handler.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        handler.end_headers()
        stream.seek(start)
        remaining = end-start+1
        try:
            while remaining:
                data = stream.read(min(256*1024, remaining))
                if not data:
                    break
                handler.wfile.write(data)
                remaining -= len(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
