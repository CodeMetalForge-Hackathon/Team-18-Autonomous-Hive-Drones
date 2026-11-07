"""Record external-camera ground truth during one manually supervised wheel trial."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from wheel_step import wheel_step


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('speeds', type=int, nargs=4)
    parser.add_argument('--ms', type=int, default=200)
    parser.add_argument('--ramp-ms', type=int, default=0)
    parser.add_argument('--camera-exe', type=Path, required=True)
    parser.add_argument('--dll-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', default='COM5')
    args = parser.parse_args()
    if not 20 <= args.ms <= 600 or any(abs(v)>40 for v in args.speeds):
        parser.error('Trial capped at 600 ms and wheel speed 40')
    folder = args.output/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    env = dict(os.environ)
    env['PATH'] = str(args.dll_directory)+os.pathsep+env.get('PATH', '')
    with (folder/'capture.log').open('wb') as log:
        process = subprocess.Popen([str(args.camera_exe), str(folder), '180'],
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic()+8
            while not (folder/'sample-0'/'frame-1.json').exists():
                if process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('Camera did not start; no motor command issued')
                time.sleep(0.05)
            report = wheel_step(args.port, args.speeds, args.ms, args.ramp_ms)
            (folder/'trial.json').write_text(json.dumps(report, indent=2))
            if process.wait(timeout=25):
                raise RuntimeError('Recording failed; motion report preserved')
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
    print('TRIAL', folder)


if __name__ == '__main__':
    main()
