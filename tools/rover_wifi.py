"""Authenticated Wi-Fi transport for RoverC; camera stays on the host."""
import json
import math
import time
import urllib.parse
import urllib.error
import urllib.request

from rover import Rover, wheel_arguments, servo_arguments, tone_arguments


class WifiRover(Rover):
    def __init__(self, url, key, camera_config=None, allow_motion=True):
        super().__init__(camera_config=camera_config, allow_motion=allow_motion)
        self.url = url.rstrip('/') + '/api/robot/'
        self.key, self.token, self.sequence = key, '', 0
        self.lease_time = 0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, route, data=None):
        headers = {'X-Rover-Key': self.key, 'X-Rover-Token': self.token}
        body = None if data is None else urllib.parse.urlencode(data).encode()
        request = urllib.request.Request(self.url + route, data=body, headers=headers)
        try:
            with self.opener.open(request, timeout=.8) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read(4096)).get('error', '')
            except (ValueError, AttributeError):
                detail = ''
            error.rover_reason = detail
            error.msg = f'{route}: {detail}' if detail else error.msg
            raise

    def claim(self):
        if not self.allow_motion:
            raise PermissionError('Actuator access is disabled')
        if not self.token:
            self.token = self.call('claim', {})['token']
            self.sequence = 0
            self.lease_time = time.monotonic()

    def action(self, route, **data):
        self.claim()
        self.sequence += 1
        try:
            result = self.call(route, dict(data, seq=self.sequence))
        except urllib.error.HTTPError as error:
            # This explicit rejection happens before actuation. Never replay a
            # timeout, network failure, expired sequence, or other rejection.
            if error.code != 409 or getattr(error, 'rover_reason', '') != 'Control lease required':
                raise
            self.token = ''
            self.claim()  # Fails if another controller owns the robot.
            self.sequence += 1
            result = self.call(route, dict(data, seq=self.sequence))
        self.lease_time = time.monotonic()
        return result

    def status(self):
        return self.call('status')

    def capabilities(self):
        return self.call('capabilities')

    def imu(self):
        return self.call('imu')

    def sonar(self):
        return self.call('sonar')

    def servos(self):
        return self.call('servos')

    def buzzer(self):
        return self.call('buzzer')

    def stop(self):
        result = self.action('stop')
        if result['moving'] or result['armed'] or not result['stop_ack'] or result['stop_pending']:
            raise RuntimeError('Stop/disarm not acknowledged')
        return result

    def ready(self):
        before = self.status()
        if not before['connected'] or before['moving'] or before['armed'] or not before['stop_ack'] or before['stop_pending']:
            raise RuntimeError('Rover must be connected, stopped and disarmed')
        self.claim()
        return before

    def wheels(self, values, duration_ms, pulse=False):
        values, duration_ms = wheel_arguments(values, duration_ms, pulse)
        before = self.ready()
        report = dict(wheels=values, duration_ms=duration_ms, pulse=pulse, before=before)
        error = None
        try:
            start = time.monotonic()
            report['started_unix_ms'] = time.time()*1000
            deadline = start + duration_ms/1000
            if pulse:
                self.action('wheels', **dict(zip(('w0','w1','w2','w3'), values)),
                            duration_ms=duration_ms, pulse=1)
                time.sleep(max(0, deadline-time.monotonic()))
            else:
                while time.monotonic() < deadline:
                    remaining = max(20, min(300, math.ceil((deadline-time.monotonic())*1000)))
                    self.action('wheels', **dict(zip(('w0','w1','w2','w3'), values)),
                                duration_ms=remaining, pulse=0)
                    time.sleep(max(0, min(.08, deadline-time.monotonic())))
                    if remaining <= 80:
                        break
        except Exception as failure:
            error = str(failure)
        finally:
            try:
                report['after'] = self.stop()
                report['stopped_unix_ms'] = time.time()*1000
                if report['after']['error_count'] != before['error_count']:
                    error = error or 'Motor error counter changed'
            except Exception as failure:
                error = (error+'; ' if error else '')+str(failure)
        report['valid'] = error is None
        if error:
            report['error'] = error
        return report

    def servo(self, channel, *, angle=None, pulse_us=None):
        if (angle is None) == (pulse_us is None):
            raise ValueError('Supply exactly one of angle or pulse_us')
        pulse = pulse_us is not None
        value = pulse_us if pulse else angle
        servo_arguments(channel, value, pulse)
        before = self.ready()
        result = self.action('servo', channel=channel, value=value, pulse=int(pulse))
        return dict(valid=True, before=before, after=self.status(), acknowledgement=result,
                    channel=channel, **({'pulse_us':value} if pulse else {'angle':value}))

    def tone(self, frequency, duration_ms, volume=32):
        tone_arguments(frequency, duration_ms, volume)
        return self.action('tone', frequency=frequency, duration_ms=duration_ms, volume=volume)

    def silence(self):
        return self.action('silence')

    def close(self):
        if self.token:
            try:
                self.call('release', {})
            finally:
                self.token = ''
