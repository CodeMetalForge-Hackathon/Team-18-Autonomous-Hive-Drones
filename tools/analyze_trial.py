"""Extract board pose throughout a camera-recorded wheel trial, in image units."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from camera_pose import board_pose
from decode_camera import decode


def analyze(folder, box, heading):
    trial = json.loads((folder/'trial.json').read_text())
    trajectory = []
    for sample in sorted(folder.glob('sample-*'), key=lambda p:int(p.name.split('-')[1])):
        metadata = json.loads((sample/'frame-1.json').read_text())
        path = decode(sample, quiet=True)
        try:
            with Image.open(path) as image:
                pose = board_pose(image, box, heading)
            heading = pose['heading_degrees']
            trajectory.append({'time_ms': metadata['host_time_ms'], 'sample': sample.name, **pose})
        except ValueError as error:
            raise ValueError(f'{sample.name}: tracking lost: {error}') from error
    baseline = [p for p in trajectory if p['time_ms'] < trial['started_unix_ms']-100]
    settled = [p for p in trajectory if p['time_ms'] > trial['stopped_unix_ms']+400]
    if len(baseline)<5 or len(settled)<5:
        raise ValueError('Insufficient frames before/after motion')
    def median_pose(rows):
        return np.median([[*p['center_pixels'], p['heading_degrees']] for p in rows], axis=0)
    before, after = median_pose(baseline[-15:]), median_pose(settled[:15])
    result = {'trial': trial, 'frames': len(trajectory),
              'before': before.tolist(), 'after': after.tolist(),
              'delta': (after-before).tolist(), 'units': '[image x pixels, y pixels, heading degrees]',
              'trajectory': trajectory}
    (folder/'trajectory.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='trajectory'}, indent=2))
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--box', nargs=4, type=int, required=True)
    parser.add_argument('--heading', type=float, required=True)
    args=parser.parse_args()
    analyze(args.folder, args.box, args.heading)
