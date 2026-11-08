"""Standalone RoverC serial control and shared-recorder camera client.

One instance owns the serial port. Calls are synchronous; do not share an
instance between threads. Wheel actions always attempt stop/disarm, including
on failure. Servo targets do not measure position or define mechanical limits.
"""
import base64
import io
import json
import os
from pathlib import Path
import time
import urllib.request
import zipfile


def wheel_arguments(values, milliseconds, pulse=False):
    limit, maximum = (60, 150) if pulse else (40, 1000)
    if (not isinstance(values, list) or len(values) != 4
            or any(type(v) is not int or abs(v) > limit for v in values)):
        raise ValueError(f'four integer wheel values in [-{limit}, {limit}] required')
    if type(milliseconds) is not int or not 20 <= milliseconds <= maximum:
        raise ValueError(f'duration_ms must be an integer in [20, {maximum}]')
    return values, milliseconds


def servo_arguments(channel, value, pulse=False):
    if type(channel) is not int or channel not in (1, 2):
        raise ValueError('servo channel must be 1 or 2')
    low, high = (500, 2500) if pulse else (0, 180)
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'servo value must be an integer in [{low}, {high}]')
    return channel, value


def tone_arguments(frequency, duration_ms, volume):
    for value, low, high, name in [(frequency, 20, 20000, 'frequency'),
                                   (duration_ms, 1, 5000, 'duration_ms'), (volume, 0, 255, 'volume')]:
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{name} must be an integer in [{low}, {high}]')
    return frequency, duration_ms, volume


def parse_fields(text, prefix):
    for line in text.splitlines():
        if line.startswith(prefix + ' '):
            result = {}
            for field in line.split()[1:]:
                key, separator, value = field.partition('=')
                if separator:
                    result[key] = int(value) if value.isdigit() else value
            return result
    raise RuntimeError(f'Missing {prefix} response: {text}')


def parse_status(text):
    result = {}
    for line in text.splitlines():
        if line.startswith(('ROVER_STATUS ', 'MOTOR_DIAG ', 'AGENT_STATUS ')):
            for field in line.split()[1:]:
                key, separator, value = field.partition('=')
                if separator:
                    result[key] = int(value) if value.isdigit() else value
    if not {'connected', 'moving', 'armed', 'stop_ack', 'stop_pending', 'error_count'} <= result.keys():
        raise RuntimeError('Incomplete status; the RoverC diagnostic firmware is required')
    return {**result, 'raw': text}


class Rover:
    def __init__(self, port="COM5", camera_config=None, allow_motion=True):
        self.port, self.camera_config, self.allow_motion = port, camera_config, allow_motion
        self.link = None
        self.attempted_motion = False
        self.audio_used = False

    def connect(self):
        if self.link is None:
            import serial
            link = serial.Serial(port=None, baudrate=115200, timeout=.01, write_timeout=.2)
            link.dtr = link.rts = False
            if os.name != 'nt':
                link.exclusive = True
            link.port = self.port
            link.open()
            self.link = link
        return self.link

    def read_for(self, seconds):
        end, data = time.monotonic() + seconds, bytearray()
        while time.monotonic() < end:
            data.extend(self.connect().read(4096))
        return data.decode(errors='replace')

    def send(self, command):
        self.connect().write((command + '\n').encode('ascii'))

    def status(self):
        self.connect().reset_input_buffer()
        self.send('STATUS')
        return parse_status(self.read_for(.3))

    def query(self, command, prefix):
        self.connect().reset_input_buffer()
        self.send(command)
        return parse_fields(self.read_for(.3), prefix)

    def capabilities(self):
        status = self.status()
        if status.get('protocol', 1) < 2:
            return {'version': 1, 'servo_channels': 0, 'buzzer': 0}
        return self.query('CAPABILITIES', 'ROVER_CAPABILITIES')

    def buzzer(self):
        if self.status().get('protocol', 1) < 3:
            raise RuntimeError('Buzzer access requires firmware protocol 3')
        return self.query('BUZZER', 'BUZZER_STATUS')

    def tone(self, frequency, duration_ms, volume=32):
        if not self.allow_motion:
            raise PermissionError('Actuator access is disabled for this run')
        frequency, duration_ms, volume = tone_arguments(frequency, duration_ms, volume)
        if self.status().get('protocol', 1) < 3:
            raise RuntimeError('Buzzer access requires firmware protocol 3')
        self.audio_used = True
        return self.query(f'TONE {frequency} {duration_ms} {volume}', 'BUZZER_OK')

    def silence(self):
        if not self.allow_motion:
            raise PermissionError('Actuator access is disabled for this run')
        return self.query('SILENCE', 'BUZZER_OK')

    def imu(self):
        self.connect().reset_input_buffer()
        self.send('IMU')
        for line in self.read_for(.3).splitlines():
            if line.startswith('IMU '):
                return json.loads(line[4:])
        raise RuntimeError('Missing IMU response')

    def sonar(self):
        status = self.status()
        if status.get('protocol', 1) < 2:
            return {'configured': status.get('sonar_configured', 0),
                    'valid': status.get('range_valid', 0), 'range_mm': status.get('range_mm', 0),
                    'age_ms': None, 'source': 'firmware status'}
        return self.query('SONAR', 'SONAR_STATUS')

    def servos(self):
        if self.status().get('protocol', 1) < 2:
            raise RuntimeError('Servo access requires RoverC firmware protocol 2')
        return self.query('SERVOS', 'SERVO_STATUS')

    def servo(self, channel, *, angle=None, pulse_us=None):
        if (angle is None) == (pulse_us is None):
            raise ValueError("Supply exactly one of angle or pulse_us")
        pulse = pulse_us is not None
        value = pulse_us if pulse else angle
        if not self.allow_motion:
            raise PermissionError('Actuator access is disabled for this run')
        channel, value = servo_arguments(channel, value, pulse)
        before = self.status()
        if before.get('protocol', 1) < 2:
            raise RuntimeError('Servo access requires RoverC firmware protocol 2')
        if (not before['connected'] or before['moving'] or before['armed']
                or not before['stop_ack'] or before['stop_pending']):
            raise RuntimeError('Rover must be connected, stopped and disarmed before servo control')
        report = {'channel': channel, 'pulse_us' if pulse else 'angle': value, 'before': before}
        self.attempted_motion = True
        error = None
        try:
            self.send('ARM')
            if 'ARMED' not in self.read_for(.2).splitlines():
                raise RuntimeError('Rover did not arm')
            self.send(f'{"SERVO_US" if pulse else "SERVO"} {channel} {value}')
            response = self.read_for(.3)
            report['acknowledgement'] = parse_fields(response, 'SERVO_OK')
            report['feedback'] = 'Command acknowledged; physical servo position is not measured'
        except Exception as failure:
            error = str(failure)
        finally:
            try:
                report['after'] = self.stop()
            except Exception as failure:
                error = (error + '; ' if error else '') + str(failure)
        report['valid'] = error is None
        if error:
            report['error'] = error
        return report

    def stop(self):
        if not self.allow_motion:
            raise PermissionError('Motion access is disabled for this run')
        self.send('STOP\nDISARM\nSTATUS')
        status = parse_status(self.read_for(.35))
        if status['moving'] or status['armed'] or not status['stop_ack'] or status['stop_pending']:
            raise RuntimeError('Stop/disarm not acknowledged by all four motor writes')
        return status

    def wheels(self, values, duration_ms, pulse=False):
        milliseconds = duration_ms
        if not self.allow_motion:
            raise PermissionError('Motion access is disabled for this run')
        values, milliseconds = wheel_arguments(values, milliseconds, pulse)
        before = self.status()
        if (not before['connected'] or before['moving'] or before['armed']
                or not before['stop_ack'] or before['stop_pending']):
            raise RuntimeError('Rover must be connected, stopped and disarmed before a step')
        report = {'wheels': values, 'duration_ms': milliseconds, 'pulse': pulse, 'before': before}
        error = None
        self.attempted_motion = True
        try:
            self.send('ARM')
            if 'ARMED' not in self.read_for(.2).splitlines():
                raise RuntimeError('Rover did not arm')
            report['started_unix_ms'] = time.time() * 1000
            start = time.monotonic()
            if pulse:
                self.send('PULSE ' + str(milliseconds) + ' ' + ' '.join(map(str, values)))
                response = self.read_for(milliseconds / 1000 + .25)
                if 'DRIVING' not in response.splitlines() or 'TIMED_STOP' not in response.splitlines():
                    raise RuntimeError('Firmware pulse/start/stop acknowledgement missing: ' + response)
            else:
                response, last_ack, acknowledged = '', start, False
                ack_count = 0
                while (time.monotonic() - start) * 1000 < milliseconds:
                    self.send('WHEELS ' + ' '.join(map(str, values)))
                    remaining = milliseconds / 1000 - (time.monotonic() - start)
                    chunk = self.read_for(min(.04, max(0, remaining)))
                    response += chunk
                    if any(word in response for word in ('ERROR', 'INVALID', 'DISARMED', 'NOT_FOUND', 'INIT_DISPLAY', 'STOP_UNCONFIRMED')):
                        raise RuntimeError('Motor command failed: ' + chunk)
                    count = response.splitlines().count('DRIVING')
                    if count > ack_count:
                        last_ack, acknowledged = time.monotonic(), True
                        ack_count = count
                    if time.monotonic() - last_ack > .15:
                        raise RuntimeError('Wheel command acknowledgement lost')
                # A short step can end before its acknowledgement arrives.
                # Stop on time, then collect that reply without repeating motion.
            report['response'] = response
        except Exception as failure:
            error = str(failure)
        finally:
            try:
                report['after'] = self.stop()
                report['stopped_unix_ms'] = time.time() * 1000
                received = report.get('response', '') + report['after']['raw']
                if error is None and 'DRIVING' not in received.splitlines():
                    error = 'No wheel command acknowledged'
                if any(word in received for word in ('INVALID', 'DISARMED', 'NOT_FOUND', 'MOTOR_ERROR', 'STOP_UNCONFIRMED')):
                    error = error or 'Controller rejected wheel command'
                if report['after']['error_count'] != before['error_count']:
                    error = error or 'Motor error counter changed during step'
            except Exception as failure:
                error = (error + '; ' if error else '') + str(failure)
        report['valid'] = error is None
        if error:
            report['error'] = error
        return report

    def snapshot(self):
        if self.camera_config is None:
            raise ValueError('Supply camera_config to use snapshots')
        import numpy as np
        from PIL import Image
        config = json.loads(Path(self.camera_config).read_text())
        started = time.time() * 1000
        deadline = time.monotonic() + 3
        while True:
            request = urllib.request.Request(config['url'] + '/snapshot',
                                             headers={'X-Camera-Token': config['token']})
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = response.read(2_000_001)
            if len(payload) > 2_000_000:
                raise ValueError('Camera response exceeds size limit')
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                metadata = json.loads(archive.read('frame-1.json'))
                member = archive.getinfo('frame-1.raw')
                if member.file_size > 1_000_000:
                    raise ValueError('Camera frame exceeds size limit')
                data = archive.read(member)
            if metadata['host_time_ms'] > started:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Camera did not supply a frame captured after this request')
            time.sleep(.02)
        width, height = metadata['width'], metadata['height']
        if ((width, height) != (640, 400) or metadata.get('configured_rgb_mode') not in (31, 32, 33)
                or len(data) != width * height * 3 // 2):
            raise ValueError('Expected the recorder\'s 640x400 NV12 frame')
        pixels = np.frombuffer(data, dtype=np.uint8).astype(np.int32)
        y = pixels[:width * height].reshape(height, width) - 16
        uv = pixels[width * height:].reshape(height // 2, width // 2, 2).repeat(2, 0).repeat(2, 1) - 128
        u, v = uv[:, :, 0], uv[:, :, 1]
        rgb = np.stack(((298*y + 409*v + 128) >> 8, (298*y - 100*u - 208*v + 128) >> 8,
                        (298*y + 516*u + 128) >> 8), axis=-1)
        output = io.BytesIO()
        Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(output, format='PNG')
        return {'png': base64.b64encode(output.getvalue()).decode(),
                'timestamp': metadata['timestamp'], 'host_time_ms': metadata['host_time_ms'],
                'width': width, 'height': height, 'captured_after_request': True}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        try:
            if self.link is not None and self.attempted_motion:
                self.stop()
            elif self.link is not None and self.audio_used:
                self.silence()
        finally:
            if self.link is not None:
                self.link.close()
                self.link = None
