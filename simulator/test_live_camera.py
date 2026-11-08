import base64
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import live_camera
import server


def payload(stale=False):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('frame-1.json', json.dumps({'width':640, 'height':400,
                         'configured_rgb_mode':31, 'host_time_ms':time.time()*1000-(5000 if stale else 0)}))
        archive.writestr('frame-1.raw', bytes([16])*(640*400)+bytes([128])*(640*200))
    return data.getvalue()


class CameraTests(unittest.TestCase):
    def test_decode_and_stale_rejection(self):
        with patch('live_camera.Path.read_text', return_value=json.dumps({'url':'http://camera', 'token':'private'})), \
             patch('live_camera.urllib.request.urlopen') as request:
            request.return_value.__enter__.return_value.read.return_value = payload()
            frame = live_camera.read_frame('unused')
            self.assertTrue(base64.b64decode(frame['jpeg']).startswith(b'\xff\xd8'))
            self.assertNotIn('token', frame)
            request.return_value.__enter__.return_value.read.return_value = payload(stale=True)
            with self.assertRaisesRegex(ValueError, 'stale'):
                live_camera.read_frame('unused')

    def test_worker_reads_existing_recorder_and_reuses_frame(self):
        class Recorder(BaseHTTPRequestHandler):
            def log_message(self, *args):pass
            def do_GET(self):
                assert self.path == '/snapshot'
                assert self.headers['X-Camera-Token'] == 'private'
                body = payload()
                self.send_response(200);self.end_headers();self.wfile.write(body)
        recorder = ThreadingHTTPServer(('127.0.0.1',0),Recorder)
        thread = threading.Thread(target=recorder.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                config = Path(folder)/'camera.json'
                config.write_text(json.dumps({'url':f'http://127.0.0.1:{recorder.server_port}', 'token':'private'}))
                camera = live_camera.LiveCamera(config)
                try:
                    first = camera.frame()
                    self.assertEqual(first, camera.frame())
                    self.assertNotIn('private', json.dumps(camera.status()))
                finally:camera.close()
        finally:recorder.shutdown();recorder.server_close();thread.join()

    def test_http_frames_and_errors_do_not_expose_configuration(self):
        class Camera:
            def status(self):return {'configured':True}
            def frame(self):return {'jpeg':base64.b64encode(b'jpeg').decode(),
                                   'captured_ms':time.time()*1000,'width':640,'height':400}
        http_server = ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        thread = threading.Thread(target=http_server.serve_forever,daemon=True);thread.start()
        try:
            with patch.object(server, 'camera', Camera()):
                client = http.client.HTTPConnection('127.0.0.1',http_server.server_port)
                client.request('GET','/api/camera.jpg');response=client.getresponse()
                self.assertEqual(response.status,200)
                self.assertEqual(response.getheader('Content-Type'),'image/jpeg')
                self.assertEqual(response.getheader('Cache-Control'),'no-store')
                self.assertEqual(response.read(),b'jpeg');client.close()
            with patch.object(server, 'camera', live_camera.LiveCamera()):
                client = http.client.HTTPConnection('127.0.0.1',http_server.server_port)
                client.request('GET','/api/camera.jpg');response=client.getresponse()
                self.assertEqual(response.status,503)
                self.assertEqual(json.loads(response.read())['error'],'Live camera is not configured')
                client.close()
        finally:http_server.shutdown();http_server.server_close();thread.join()


if __name__ == '__main__':unittest.main()
