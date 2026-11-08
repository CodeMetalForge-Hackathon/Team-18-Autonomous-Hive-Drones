import functools
import json
import pathlib
import tempfile
import threading
import struct
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import camera_archive


class ArchiveTest(unittest.TestCase):
    def test_fragment_duration(self):
        box=lambda tag,body:struct.pack('>I4s',len(body)+8,tag)+body
        mdhd=box(b'mdhd',bytes(12)+struct.pack('>I',1000)+bytes(8))
        tfhd=box(b'tfhd',struct.pack('>III',8,1,100))
        tfdt=box(b'tfdt',struct.pack('>II',0,1000))
        trun=box(b'trun',struct.pack('>II',0,20))
        data=box(b'moov',box(b'trak',box(b'mdia',mdhd)))+box(b'moof',box(b'traf',tfhd+tfdt+trun))
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'clip.mp4'
            path.write_bytes(data)
            self.assertEqual(camera_archive.duration(str(path),len(data),0),3)

    def test_closed_clips_ranges_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            session = root / 'session'
            session.mkdir()
            (session/'part-1.mp4').write_bytes(b'0123456789')
            (session/'part-2.mp4').write_bytes(b'open')
            (session/'status.json').write_text(json.dumps({'recording': True}))
            self.assertEqual([c['file'] for c in camera_archive.clips(root)], ['part-1.mp4'])

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    camera_archive.serve(self, root, 'session', self.path[1:])
                def log_message(self, *args):
                    pass

            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            url = f'http://127.0.0.1:{server.server_port}/'
            try:
                for interval, expected in [('bytes=2-5', b'2345'), ('bytes=-3', b'789'), ('bytes=7-', b'789')]:
                    with urllib.request.urlopen(urllib.request.Request(url+'part-1.mp4', headers={'Range':interval})) as response:
                        self.assertEqual(response.status, 206)
                        self.assertEqual(response.read(), expected)
                for name, headers, code in [('part-2.mp4', {}, 404), ('../part-1.mp4', {}, 404), ('part-1.mp4', {'Range':'bytes=99-'}, 416)]:
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(urllib.request.Request(url+name, headers=headers))
                    self.assertEqual(error.exception.code, code)
            finally:
                server.shutdown()
                server.server_close()
                worker.join()


if __name__ == '__main__':
    unittest.main()
