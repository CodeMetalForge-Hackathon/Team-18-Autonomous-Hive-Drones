"""Read-only frames from the existing shared camera recorder."""
import base64
import io
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile


def read_frame(config_path):
    import numpy as np
    from PIL import Image

    config = json.loads(Path(config_path).read_text(encoding='utf-8-sig'))
    request = urllib.request.Request(config['url'] + '/snapshot',
                                     headers={'X-Camera-Token': config['token']})
    with urllib.request.urlopen(request, timeout=2) as response:
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError('Camera response too large')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if archive.getinfo('frame-1.json').file_size > 16384:
            raise ValueError('Camera metadata too large')
        metadata = json.loads(archive.read('frame-1.json'))
        if archive.getinfo('frame-1.raw').file_size != 640*400*3//2:
            raise ValueError('Unexpected camera frame size')
        data = archive.read('frame-1.raw')
    if (metadata.get('width'), metadata.get('height')) != (640, 400) or metadata.get('configured_rgb_mode') not in (31, 32, 33):
        raise ValueError('Expected configured NV12 camera frame')
    captured = float(metadata['host_time_ms'])
    if not 0 <= time.time()*1000 - captured <= 1000:
        raise ValueError('Camera frame is stale')
    pixels = np.frombuffer(data, dtype=np.uint8).astype(np.int32)
    y = pixels[:640*400].reshape(400, 640)-16
    uv = pixels[640*400:].reshape(200, 320, 2).repeat(2, 0).repeat(2, 1)-128
    u, v = uv[:, :, 0], uv[:, :, 1]
    rgb = np.stack(((298*y+409*v+128)>>8, (298*y-100*u-208*v+128)>>8,
                    (298*y+516*u+128)>>8), axis=-1)
    output = io.BytesIO()
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(output, format='JPEG', quality=85)
    return {'jpeg': base64.b64encode(output.getvalue()).decode(), 'captured_ms': captured,
            'width': 640, 'height': 400}


class LiveCamera:
    def __init__(self, config=None, python=None):
        self.config, self.python = config, python or sys.executable
        self.lock = threading.Lock()
        self.process = None
        self.cached = None
        self.cached_at = 0

    def status(self):
        return {'configured': bool(self.config)}

    def _start(self):
        self.responses = queue.Queue()
        self.process = subprocess.Popen(
            [str(self.python), '-u', '-c', Path(__file__).read_text(), '--camera-worker', str(self.config)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        process, responses = self.process, self.responses

        def collect():
            for line in process.stdout:
                try: responses.put(json.loads(line))
                except ValueError: responses.put({'error': True})
            responses.put({'error': True})
        threading.Thread(target=collect, daemon=True).start()

    def frame(self):
        if not self.config:
            raise RuntimeError('Live camera is not configured')
        with self.lock:
            if self.cached and time.monotonic()-self.cached_at < .15 and time.time()*1000-self.cached['captured_ms'] < 1000:
                return self.cached
            if self.process is None or self.process.poll() is not None:
                self._stop()
                self._start()
            try:
                self.process.stdin.write('frame\n')
                self.process.stdin.flush()
                frame = self.responses.get(timeout=3)
                if frame.get('error') or not 0 <= time.time()*1000-frame['captured_ms'] <= 1000:
                    raise ValueError('Frame unavailable')
                self.cached, self.cached_at = frame, time.monotonic()
                return frame
            except (OSError, ValueError, KeyError, queue.Empty):
                self._stop()
                raise RuntimeError('Live camera unavailable; check the recorder') from None

    def _stop(self):
        if self.process:
            self.process.kill() if self.process.poll() is None else None
            self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()
            self.process = None

    def close(self):
        with self.lock:
            self._stop()


if __name__ == '__main__' and sys.argv[1:2] == ['--camera-worker']:
    for _ in sys.stdin:
        try: result = read_frame(sys.argv[2])
        except Exception: result = {'error': True}
        print(json.dumps(result), flush=True)
