import argparse, json, re, time
from pathlib import Path
import serial
parser = argparse.ArgumentParser(description='Save Wi-Fi credentials to a private file')
parser.add_argument('--port', default='COM5')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
link=serial.Serial(port=None,baudrate=115200,timeout=0.1,write_timeout=0.2)
link.dtr=link.rts=False
link.port=args.port
link.open()
try:
    data=b''
    until=time.monotonic()+4
    while time.monotonic()<until:data+=link.read(4096)
    link.write(b'WIFI\nSTATUS\n')
    until=time.monotonic()+2
    while time.monotonic()<until:data+=link.read(4096)
    output=data.decode(errors='replace')
    match=re.search(r'WIFI_READY ssid=(\S+) password=([0-9a-f]{16}) ip=(\S+)',output)
    assert match, 'Wi-Fi information not received'
    args.output.write_text(json.dumps(dict(zip(['ssid','password','ip'],match.groups()))))
    print('Credentials saved to', args.output, '(keep private)')
finally:link.close()
