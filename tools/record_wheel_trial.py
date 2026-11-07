"""Record external-camera ground truth during one manually supervised wheel trial."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import threading

from wheel_step import wheel_step, TrialError
from camera_shared import CONFIG, snapshot


def shared_trial(folder, args):
    stopped = threading.Event()
    failures = []
    def collect():
        index = 0
        previous = None
        try:
            while not stopped.is_set():
                destination = folder/f'sample-{index}'
                metadata = snapshot(destination)
                # Repeated frames would bias the trajectory statistics.
                if metadata['timestamp'] != previous:
                    previous = metadata['timestamp']
                    index += 1
                stopped.wait(0.09)
        except Exception as error:
            failures.append(error)
    collector = threading.Thread(target=collect, daemon=True)
    collector.start()
    try:
        time.sleep(0.5)
        if failures:
            raise failures[0]
        try:
            report = wheel_step(args.port, args.speeds, args.ms, args.ramp_ms, args.pulse)
        except TrialError as error:
            report = error.report
            (folder/'trial.json').write_text(json.dumps(report, indent=2))
            time.sleep(0.6)
            raise
        time.sleep(0.8)
        if failures:
            report['error'] = 'Shared camera failed: '+str(failures[0])
        (folder/'trial.json').write_text(json.dumps(report, indent=2))
        if failures:
            raise failures[0]
    finally:
        stopped.set()
        collector.join(timeout=4)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('speeds', type=int, nargs=4)
    parser.add_argument('--ms', type=int, default=200)
    parser.add_argument('--ramp-ms', type=int, default=0)
    parser.add_argument('--camera-exe', type=Path, required=True)
    parser.add_argument('--dll-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', default='COM5')
    parser.add_argument('--pulse', action='store_true')
    args = parser.parse_args()
    limit, duration_limit = (60, 150) if args.pulse else (40, 600)
    if not 20 <= args.ms <= duration_limit or any(abs(v)>limit for v in args.speeds) or (args.pulse and args.ramp_ms):
        parser.error('Trial capped at 600 ms and wheel speed 40')
    folder = args.output/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    if CONFIG.exists():
        shared_trial(folder, args)
        print('TRIAL', folder)
        return
    env = dict(os.environ)
    env['PATH'] = str(args.dll_directory)+os.pathsep+env.get('PATH', '')
    with (folder/'capture.log').open('wb') as log:
        process = subprocess.Popen([str(args.camera_exe), str(folder), '90'],
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic()+8
            while not (folder/'sample-0'/'frame-1.json').exists():
                if process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('Camera did not start; no motor command issued')
                time.sleep(0.05)
            try:
                report = wheel_step(args.port, args.speeds, args.ms, args.ramp_ms, args.pulse)
            except TrialError as error:
                (folder/'trial.json').write_text(json.dumps(error.report, indent=2))
                # Preserve the post-stop frames when a motor/communication error
                # aborts the pulse, so failed attempts cannot become training data.
                process.wait(timeout=25)
                raise
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
