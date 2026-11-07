import io
import json
import unittest
import zipfile
from unittest.mock import patch

from rover import Rover


class Clock:
    now = 0.0

    def monotonic(self):
        return self.now


class Serial:
    def __init__(self, clock, delay=.03, fragmented=False, acknowledge=True,
                 stop_ack=1, reject=False):
        self.clock = clock
        self.delay = delay
        self.fragmented = fragmented
        self.acknowledge = acknowledge
        self.stop_ack = stop_ack
        self.reject = reject
        self.pending = []
        self.commands = []
        self.command_times = []
        self.closed = False
        self.angle = 90

    def reset_input_buffer(self):
        self.pending = []

    def queue(self, data, delay=.001):
        self.pending.append((self.clock.now + delay, data.encode()))

    def write(self, data):
        for cmd in data.decode().splitlines():
            self.commands.append(cmd)
            self.command_times.append((cmd, self.clock.now))
            if cmd == 'STATUS':
                self.queue('ROVER_STATUS protocol=3 connected=1 moving=0 armed=0\n'
                           f'MOTOR_DIAG error_count=0 stop_ack={self.stop_ack} stop_pending=0\n')
            elif cmd == 'ARM':
                self.queue('ARMED\n')
            elif cmd.startswith(('WHEELS ', 'PULSE ')):
                if self.reject:
                    self.queue('MOTOR_ERROR\n', self.delay)
                elif self.acknowledge:
                    self.queue('DRI' if self.fragmented else 'DRIVING\n', self.delay)
                    if self.fragmented:
                        self.queue('VING\n', self.delay + .012)
                if cmd.startswith('PULSE '):
                    self.queue('TIMED_STOP\n', int(cmd.split()[1])/1000)
            elif cmd.startswith(('SERVO ', 'SERVO_US ')):
                _, channel, value = cmd.split()
                self.queue(f'SERVO_OK channel={channel} value={value}\n')
            elif cmd in ('STOP', 'DISARM'):
                self.queue('STOPPED\n')

    def read(self, size):
        self.clock.now += .002
        self.pending.sort(key=lambda item: item[0])
        if self.pending and self.pending[0][0] <= self.clock.now:
            return self.pending.pop(0)[1]
        return b''

    def close(self):
        self.closed = True


class RoverTest(unittest.TestCase):
    def run_wheels(self, duration=25, pulse=False, **options):
        clock = Clock()
        link = Serial(clock, **options)
        rover = Rover()
        rover.link = link
        with patch('rover.time.monotonic', clock.monotonic):
            report = rover.wheels([20, -20, 20, -20], duration, pulse=pulse)
        return report, link

    def test_delayed_ack_after_short_step_is_not_a_failure_or_retry(self):
        report, link = self.run_wheels(delay=.08)
        self.assertTrue(report['valid'], report)
        self.assertEqual(sum(c.startswith('WHEELS ') for c in link.commands), 1)
        start = next(t for c, t in link.command_times if c.startswith('WHEELS '))
        stop = next(t for c, t in link.command_times if c == 'STOP')
        self.assertLessEqual(stop - start, .03)
        self.assertIn('STOP', link.commands)
        self.assertIn('DISARM', link.commands)

    def test_fragmented_ack_is_reassembled(self):
        report, _ = self.run_wheels(100, fragmented=True)
        self.assertTrue(report['valid'], report)

    def test_missing_ack_still_stops_and_reports_failure(self):
        report, link = self.run_wheels(acknowledge=False)
        self.assertFalse(report['valid'])
        self.assertIn('No wheel command acknowledged', report['error'])
        self.assertIn('STOP', link.commands)

    def test_late_error_is_not_hidden_by_successful_stop(self):
        report, _ = self.run_wheels(reject=True, delay=.08)
        self.assertFalse(report['valid'])

    def test_firmware_timed_pulse(self):
        report, link = self.run_wheels(100, pulse=True)
        self.assertTrue(report['valid'], report)
        self.assertIn('PULSE 100 20 -20 20 -20', link.commands)

    def test_unconfirmed_stop_prevents_arming(self):
        with self.assertRaises(RuntimeError):
            self.run_wheels(stop_ack=0)

    def test_invalid_values_do_not_open_serial(self):
        rover = Rover('invalid')
        for values, duration in [([41]*4, 100), ([1]*3, 100), ([0]*4, 19)]:
            with self.assertRaises(ValueError):
                rover.wheels(values, duration)
        with self.assertRaises(ValueError):
            rover.servo(1, angle=90, pulse_us=1500)
        self.assertIsNone(rover.link)

    def test_servo_does_not_remap_target_and_context_closes(self):
        clock = Clock()
        link = Serial(clock)
        with patch('rover.time.monotonic', clock.monotonic):
            with Rover() as rover:
                rover.link = link
                report = rover.servo(1, angle=90)
                self.assertTrue(report['valid'], report)
                self.assertIn('SERVO 1 90', link.commands)
                self.assertFalse(any(c.startswith('WHEELS') for c in link.commands))
        self.assertTrue(link.closed)

    def test_fresh_camera_frame_is_decoded_with_metadata(self):
        payload = io.BytesIO()
        metadata = {'width': 640, 'height': 400, 'configured_rgb_mode': 31,
                    'host_time_ms': 1001, 'timestamp': 42}
        with zipfile.ZipFile(payload, 'w') as archive:
            archive.writestr('frame-1.json', json.dumps(metadata))
            archive.writestr('frame-1.raw', bytes([16])*(640*400) + bytes([128])*(640*200))
        with patch('rover.Path.read_text', return_value=json.dumps({'url':'http://localhost', 'token':'test'})), \
             patch('rover.urllib.request.urlopen') as urlopen, patch('rover.time.time', return_value=1):
            urlopen.return_value.__enter__.return_value.read.return_value = payload.getvalue()
            frame = Rover(camera_config='unused').snapshot()
        self.assertEqual(frame['host_time_ms'], 1001)
        self.assertEqual(frame['timestamp'], 42)
        self.assertTrue(frame['captured_after_request'])
        self.assertTrue(frame['png'].startswith('iVBOR'))


if __name__ == '__main__':
    unittest.main()
