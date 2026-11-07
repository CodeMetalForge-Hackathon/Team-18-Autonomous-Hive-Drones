import argparse, serial, time
parser = argparse.ArgumentParser(description='Read status; --reset reboots the stopped board')
parser.add_argument('--port', default='COM5')
parser.add_argument('--reset', action='store_true')
args = parser.parse_args()
s = serial.Serial(port=None, baudrate=115200, timeout=0.2)
s.dtr = False
s.rts = False
s.port = args.port
s.open()
if args.reset:
    s.rts = True
    time.sleep(0.15)
    s.rts = False
try:
    end = time.monotonic() + 8
    while time.monotonic() < end:
        data = s.read(4096)
        if data: print(data.decode('utf-8', errors='replace'), end='', flush=True)
    s.write(b'STATUS\n')
    time.sleep(0.5)
    print(s.read(4096).decode('utf-8', errors='replace'))
    s.write(b'STOP\n')
    time.sleep(0.5)
    print(s.read(4096).decode('utf-8', errors='replace'))
finally:
    s.close()

