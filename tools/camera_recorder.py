"""Continuous color archive and shared snapshot source; never controls motors."""
import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import zipfile

HEADER = struct.Struct('<4sIIIQQ')


def read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size-len(data))
        if not chunk:
            raise EOFError('Camera stream ended')
        data.extend(chunk)
    return bytes(data)


def read_frame(stream):
    magic, width, height, size, timestamp, host_time = HEADER.unpack(read_exact(stream, HEADER.size))
    if magic != b'FRM1' or (width, height) != (640, 400) or size != width*height*3//2:
        raise ValueError('Invalid camera frame header')
    return ({'width':width, 'height':height, 'bytes':size, 'timestamp':timestamp,
             'host_time_ms':host_time, 'configured_rgb_mode':33, 'format':0, 'type':1},
            read_exact(stream, size))


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera-exe', type=Path, required=True)
    parser.add_argument('--dll-directory', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1]/'.camera-recorder.json')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--segment-seconds', type=int, default=300)
    parser.add_argument('--seconds', type=float, default=0, help='0 keeps recording until stopped')
    args = parser.parse_args()
    if not args.output.is_dir():
        raise ValueError('Recording output directory must already exist')
    token = secrets.token_hex(24)
    session = args.output/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+token[:6])
    session.mkdir()
    stop = threading.Event()
    lock = threading.Lock()
    state = {'recording':False, 'frames':0, 'session':str(session), 'pid':os.getpid()}
    latest = [None]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def authorized(self):
            if not secrets.compare_digest(self.headers.get('X-Camera-Token',''), token):
                self.send_error(403)
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            with lock:
                frame = latest[0]
                status = dict(state)
            if self.path == '/status':
                payload = json.dumps(status).encode()
                kind = 'application/json'
            elif self.path == '/snapshot':
                if not frame or time.time()*1000-frame[0]['host_time_ms'] > 1500:
                    self.send_error(503, 'No fresh camera frame')
                    return
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
                    archive.writestr('frame-1.json', json.dumps(frame[0]))
                    archive.writestr('frame-1.raw', frame[1])
                payload, kind = buffer.getvalue(), 'application/zip'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            if not self.authorized():
                return
            if self.path != '/stop':
                self.send_error(404)
                return
            stop.set()
            self.send_response(202)
            self.end_headers()

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = {'url':f'http://127.0.0.1:{args.port}', 'token':token, 'pid':os.getpid(), 'session':str(session)}
    atomic_json(args.config, config)
    env = dict(os.environ)
    env['PATH'] = str(args.dll_directory)+os.pathsep+env.get('PATH','')
    started = time.monotonic()
    encoder = camera = None
    try:
        with (session/'events.jsonl').open('a', buffering=1) as events, \
             (session/'frames.jsonl').open('a', buffering=1) as frames, \
             (session/'capture.log').open('ab') as camera_log, \
             (session/'encoder.log').open('ab') as encoder_log:
            attempt = 0
            while not stop.is_set():
                if shutil.disk_usage(session).free < 5*1024**3:
                    raise RuntimeError('Recording stopped: less than 5 GiB free')
                attempt += 1
                camera = subprocess.Popen([str(args.camera_exe), '--pipe'], env=env,
                                          stdout=subprocess.PIPE, stderr=camera_log)
                # A reader thread allows stop/stale detection even if the SDK blocks.
                queue = __import__('queue').Queue(maxsize=5)
                def receive(process, queue):
                    try:
                        while not stop.is_set():
                            frame = read_frame(process.stdout)
                            queue.put(frame, timeout=2)
                    except Exception as error:
                        try: queue.put(error, timeout=2)
                        except Exception: pass
                reader = threading.Thread(target=receive, args=(camera, queue), daemon=True)
                reader.start()
                encoder = None
                last_frame = time.monotonic()
                try:
                    while not stop.is_set():
                        if args.seconds and time.monotonic()-started >= args.seconds:
                            stop.set()
                            break
                        try:
                            frame = queue.get(timeout=0.5)
                        except __import__('queue').Empty:
                            if time.monotonic()-last_frame > 6:
                                raise TimeoutError('No camera frames for 6 seconds')
                            continue
                        if isinstance(frame, Exception):
                            raise frame
                        last_frame = time.monotonic()
                        if encoder is None:
                            output = session/(f'part-{attempt}-%Y%m%d-%H%M%S.mp4')
                            command = [str(args.ffmpeg), '-hide_banner', '-loglevel','warning',
                                '-f','rawvideo','-pixel_format','nv12','-video_size','640x400',
                                '-framerate','10','-i','pipe:0','-an','-c:v','libx264',
                                '-preset','ultrafast','-crf','23','-threads','1','-g','50',
                                '-f','segment','-segment_time',str(args.segment_seconds),
                                '-segment_format','mp4','-segment_format_options',
                                'movflags=+frag_keyframe+empty_moov+default_base_moof',
                                '-reset_timestamps','1','-strftime','1',str(output)]
                            encoder = subprocess.Popen(command, stdin=subprocess.PIPE,
                                                       stdout=encoder_log, stderr=encoder_log)
                        encoder.stdin.write(frame[1])
                        with lock:
                            latest[0] = frame
                            state.update(recording=True, frames=state['frames']+1,
                                         last_frame_time_ms=frame[0]['host_time_ms'])
                            status = dict(state)
                        frames.write(json.dumps({'index':status['frames'], **frame[0]})+'\n')
                        if status['frames']%10 == 0:
                            atomic_json(session/'status.json', status)
                            if shutil.disk_usage(session).free < 5*1024**3:
                                stop.set()
                except Exception as error:
                    events.write(json.dumps({'time':datetime.now(timezone.utc).isoformat(),
                                             'event':'capture_gap', 'error':str(error)})+'\n')
                finally:
                    with lock: state['recording'] = False
                    if camera.poll() is None:
                        camera.terminate()
                    camera.wait(timeout=5)
                    if encoder:
                        try:
                            encoder.stdin.close()
                            encoder.wait(timeout=10)
                        except Exception:
                            encoder.kill()
                            encoder.wait(timeout=5)
                    camera = encoder = None
                if not stop.is_set():
                    stop.wait(2)
    finally:
        stop.set()
        with lock: state['recording'] = False
        atomic_json(session/'status.json', state)
        server.shutdown()
        server.server_close()
        if args.config.exists():
            current = json.loads(args.config.read_text())
            if current.get('token') == token:
                args.config.unlink()


if __name__ == '__main__':
    main()
