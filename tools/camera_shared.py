"""Client for the single-owner background camera recorder."""
import argparse
import io
import json
from pathlib import Path
import urllib.request
import zipfile

CONFIG = Path(__file__).resolve().parents[1]/'.camera-recorder.json'


def request(route, method='GET'):
    config = json.loads(CONFIG.read_text())
    req = urllib.request.Request(config['url']+route, method=method,
                                 headers={'X-Camera-Token':config['token']})
    return urllib.request.urlopen(req, timeout=3)


def snapshot(folder):
    with request('/snapshot') as response:
        data = response.read()
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in ('frame-1.json','frame-1.raw'):
            (folder/name).write_bytes(archive.read(name))
    return json.loads((folder/'frame-1.json').read_text())


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status','snapshot','stop'])
    parser.add_argument('--output', type=Path)
    args=parser.parse_args()
    if args.action == 'snapshot':
        if not args.output:
            parser.error('--output is required')
        print(json.dumps(snapshot(args.output), indent=2))
    else:
        with request('/'+args.action, 'POST' if args.action=='stop' else 'GET') as response:
            print(response.read().decode())
