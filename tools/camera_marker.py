"""Enable the on-screen camera reference, or restore the normal status screen."""
import argparse
import serial
from supervised_step import read_for


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM5')
    parser.add_argument('--restore-ui',action='store_true')
    args=parser.parse_args()
    link=serial.Serial(port=None,baudrate=115200,timeout=0.02,write_timeout=0.2)
    link.dtr=link.rts=False
    link.port=args.port
    link.open()
    try:
        read_for(link,2)
        command=b'UI\n' if args.restore_ui else b'MARKER\n'
        link.write(b'DISARM\n'+command+b'STATUS\n')
        result=read_for(link,0.5)
        expected='UI_READY' if args.restore_ui else 'MARKER_READY'
        if expected not in result or 'moving=0' not in result or 'armed=0' not in result:
            raise RuntimeError('Reference display change not confirmed: '+result)
        print(result)
    finally:
        link.close()
