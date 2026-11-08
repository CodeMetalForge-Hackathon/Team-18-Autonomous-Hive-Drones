import json
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

from rover_wifi import WifiRover


class WifiTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.last_sequence = 0
        self.moving = False
        self.reject_lease_once = False
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.handle_call()

            def do_POST(self):
                self.handle_call()

            def handle_call(self):
                route = self.path.rsplit('/', 1)[-1]
                data = urllib.parse.parse_qs(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode())
                test.calls.append((route, data))
                code, result = 200, {}
                if self.headers.get('X-Rover-Key') != 'test-key':
                    code, result = 403, {'error':'Invalid key'}
                elif route == 'claim':
                    test.last_sequence = 0
                    result = {'token':'lease'}
                elif route in ('wheels','stop','servo','tone','silence'):
                    if test.reject_lease_once:
                        test.reject_lease_once = False
                        body = json.dumps({'error': 'Control lease required'}).encode()
                        self.send_response(409)
                        self.send_header('Content-Length', str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    sequence = int(data['seq'][0])
                    if self.headers.get('X-Rover-Token') != 'lease' or sequence <= test.last_sequence:
                        code = 409
                    else:
                        test.last_sequence = sequence
                        if route == 'wheels': test.moving = True
                        if route == 'stop': test.moving = False
                        result = {'accepted':True}
                if route in ('status','stop') and code == 200:
                    result = {'connected':1, 'moving':int(test.moving), 'armed':0,
                              'stop_ack':int(not test.moving), 'stop_pending':0, 'error_count':0}
                body = json.dumps(result).encode()
                self.send_response(code)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = WifiRover('http://127.0.0.1:'+str(self.server.server_port), 'test-key')

    def test_imu_is_read_only(self):
        self.client.allow_motion = False
        self.client.imu()
        self.assertEqual(self.calls, [('imu', {})])
        self.assertEqual(self.client.token, '')

    def tearDown(self):
        self.client.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_wrong_key_cannot_read_status(self):
        client = WifiRover(self.client.url.removesuffix('/api/robot/'), 'wrong')
        with self.assertRaises(HTTPError): client.status()

    def test_short_wheel_step_stops_and_does_not_retry(self):
        result = self.client.wheels([1,-2,3,-4], 25)
        self.assertTrue(result['valid'],result)
        wheel_calls = [d for r,d in self.calls if r == 'wheels']
        self.assertEqual(len(wheel_calls),1)
        self.assertEqual(wheel_calls[0]['w1'],['-2'])
        self.assertFalse(self.moving)

    def test_pulse_and_servo_share_monotonic_sequence(self):
        result = self.client.wheels([60]*4,30,pulse=True)
        self.assertTrue(result['valid'],result)
        result = self.client.servo(1,angle=95)
        self.assertTrue(result['valid'])
        self.assertEqual(self.last_sequence,3)

    def test_expired_lease_reclaims_after_explicit_rejection(self):
        self.client.claim()
        self.reject_lease_once = True
        result = self.client.action('stop')
        self.assertTrue(result['stop_ack'])
        self.assertEqual([r for r, _ in self.calls], ['claim', 'stop', 'claim', 'stop'])

    def test_read_only_cannot_claim(self):
        self.client.allow_motion = False
        with self.assertRaises(PermissionError): self.client.wheels([0]*4,25)
        self.assertFalse(any(r=='claim' for r,_ in self.calls))

    def test_stale_sequence_is_rejected(self):
        self.client.claim()
        self.client.action('stop')
        with self.assertRaises(HTTPError): self.client.call('stop',{'seq':1})


if __name__ == '__main__':
    unittest.main()
