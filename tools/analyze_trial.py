"""Extract board pose throughout a camera-recorded wheel trial, in image units."""
import argparse
import json
import re
from pathlib import Path
import numpy as np
from PIL import Image
from camera_pose import board_pose
from decode_camera import decode
from marker_pose import marker_pose


def pose_statistics(rows):
    values=np.array([[*p['center_pixels'],p['heading_degrees']] for p in rows],dtype=float)
    values[:,2]=np.degrees(np.unwrap(np.radians(values[:,2])))
    return np.median(values,axis=0),np.std(values,axis=0)


def analyze(folder, box, heading, marker_front=None):
    try:
        return analyze_validated(folder,box,heading,marker_front)
    except Exception as error:
        path=folder/'trajectory.json'
        previous=json.loads(path.read_text()) if path.exists() else {}
        previous.update(valid=False,rejection_reason=str(error))
        path.write_text(json.dumps(previous,indent=2))
        raise


def analyze_validated(folder, box, heading, marker_front=None):
    trial = json.loads((folder/'trial.json').read_text())
    if trial.get('error') or not trial.get('stopped_disarmed'):
        raise ValueError('Faulted or unverified trial cannot be used for calibration')
    counts = [int(match.group(1)) for key in ('status_before','status_after','final_status')
              for match in [re.search(r'MOTOR_DIAG error_count=(\d+)', trial.get(key,''))] if match]
    if counts and counts[-1] > counts[0]:
        raise ValueError('Motor error count increased; exclude this trial from calibration')
    trajectory = []
    missing = []
    for sample in sorted(folder.glob('sample-*'), key=lambda p:int(p.name.split('-')[1])):
        metadata = json.loads((sample/'frame-1.json').read_text())
        path = decode(sample, quiet=True)
        try:
            with Image.open(path) as image:
                pose = marker_pose(image, box, marker_front) if marker_front else board_pose(image, box, heading)
            pose['heading_degrees']=heading+(pose['heading_degrees']-heading+180)%360-180
            heading = pose['heading_degrees']
            trajectory.append({'time_ms': metadata['host_time_ms'], 'sample': sample.name, **pose})
        except ValueError as error:
            missing.append({'sample':sample.name, 'time_ms':metadata['host_time_ms'], 'error':str(error)})
    total = len(trajectory)+len(missing)
    if not total or len(missing)/total > 0.2:
        raise ValueError(f'Too much tracking loss: {len(missing)}/{total} frames')
    baseline = [p for p in trajectory if p['time_ms'] < trial['started_unix_ms']-100]
    settled = [p for p in trajectory if p['time_ms'] > trial['stopped_unix_ms']+400]
    if len(baseline)<5 or len(settled)<5:
        raise ValueError('Insufficient frames before/after motion')
    before,before_noise=pose_statistics(baseline[-15:])
    after,after_noise=pose_statistics(settled[:15])
    if marker_front and max(before_noise[2],after_noise[2])>2:
        raise ValueError('Reference unstable at rest; inspect marker visibility before calibration')
    result = {'valid':True, 'trial': trial, 'frames': len(trajectory),
              'before': before.tolist(), 'after': after.tolist(),
              'delta': (after-before).tolist(), 'units': '[image x pixels, y pixels, heading degrees]',
              'trajectory': trajectory, 'missing_measurements':missing,
              'valid_fraction':len(trajectory)/total,
              'before_std':before_noise.tolist(), 'after_std':after_noise.tolist()}
    (folder/'trajectory.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({'source':str(folder), 'speeds':trial['speeds'],
                     'duration_ms':trial['duration_ms'], 'ramp_ms':trial['ramp_ms'],
                     'frames':len(trajectory), 'before':result['before'],
                     'after':result['after'], 'delta':result['delta'],
                     'missing_frames':len(missing),
                     'before_std':result['before_std'], 'after_std':result['after_std'],
                     'motor_errors_added':counts[-1]-counts[0] if counts else None}, indent=2))
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--box', nargs=4, type=int, required=True)
    parser.add_argument('--heading', type=float, required=True)
    parser.add_argument('--marker-front', choices=['cyan','magenta'])
    args=parser.parse_args()
    analyze(args.folder, args.box, args.heading, args.marker_front)
