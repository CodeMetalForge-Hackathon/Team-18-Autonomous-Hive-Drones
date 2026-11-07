"""Bounded four-wheel calibration pulse, optionally with a smooth speed envelope.

Requires the WHEELS firmware API and recent visual inspection of clear space.
All emergency stops remain immediate; the ramp applies only to planned motion.
"""
import argparse
import json
from pathlib import Path
import time

import serial
from supervised_step import read_for


class TrialError(RuntimeError):
    def __init__(self, message, report):
        super().__init__(message)
        self.report = report


def envelope(elapsed_ms, duration_ms, ramp_ms):
    if elapsed_ms < 0 or elapsed_ms >= duration_ms:
        return 0.0
    if ramp_ms == 0:
        return 1.0
    phase = min(1.0, elapsed_ms/ramp_ms, (duration_ms-elapsed_ms)/ramp_ms)
    return phase*phase*(3-2*phase)


def wheel_step(port, speeds, duration_ms, ramp_ms=0, pulse=False):
    limit, duration_limit = (60, 150) if pulse else (40, 1000)
    if len(speeds) != 4 or any(type(v) is not int or abs(v) > limit for v in speeds):
        raise ValueError(f"Four integer wheel speeds in [-{limit},{limit}] are required")
    if not 20 <= duration_ms <= duration_limit or not 0 <= ramp_ms <= duration_ms/2 or (pulse and ramp_ms):
        raise ValueError("Duration 20..1000 ms; ramp 0..duration/2")
    link = serial.Serial(port=None, baudrate=115200, timeout=0.005, write_timeout=0.1)
    link.dtr = link.rts = False
    link.port = port
    link.open()
    report = {"speeds": speeds, "duration_ms": duration_ms, "ramp_ms": ramp_ms,
              "pulse":pulse, "commands": []}
    try:
        read_for(link, 2)
        link.write(b"DISARM\nSTATUS\n")
        status = read_for(link, 0.3)
        report['status_before'] = status
        if "connected=1" not in status or "moving=0" not in status or 'stop_ack=0' in status:
            raise RuntimeError("Rover not ready: "+status)
        link.write(b"ARM\n")
        if "ARMED" not in read_for(link, 0.2):
            raise RuntimeError("Could not arm")
        started = time.monotonic()
        report["started_unix_ms"] = time.time()*1000
        last_ack = started
        acknowledged = False
        if pulse:
            link.write((f'PULSE {duration_ms} '+ ' '.join(map(str,speeds))+'\n').encode())
            report['commands'].append({'elapsed_ms':0, 'speeds':speeds})
            response = read_for(link, duration_ms/1000+0.08)
            if any(error in response for error in ('INVALID','DISARMED','NOT_FOUND','ERROR','INIT_DISPLAY')):
                raise RuntimeError('Controller rejected calibration pulse: '+response)
            acknowledged = 'DRIVING' in response
            report['firmware_timed_stop'] = 'TIMED_STOP' in response
            if not report['firmware_timed_stop']:
                raise RuntimeError('Firmware pulse deadline was not acknowledged: '+response)
        while not pulse:
            elapsed = (time.monotonic()-started)*1000
            if elapsed >= duration_ms:
                break
            scale = envelope(elapsed, duration_ms, ramp_ms)
            values = [round(v*scale) for v in speeds]
            link.write(("WHEELS "+" ".join(map(str, values))+"\n").encode())
            response = read_for(link, min(0.04, (duration_ms-elapsed)/1000))
            report["commands"].append({"elapsed_ms": round(elapsed, 2), "speeds": values})
            if any(error in response for error in ("INVALID", "DISARMED", "NOT_FOUND", "ERROR", "INIT_DISPLAY")):
                raise RuntimeError("Controller rejected pulse: "+response)
            if "DRIVING" in response:
                last_ack = time.monotonic()
                acknowledged = True
            elif time.monotonic()-last_ack > 0.15:
                raise RuntimeError("Missing wheel-command acknowledgement: "+response)
        link.write(b"STOP\nDISARM\nSTATUS\n")
        report["stopped_unix_ms"] = time.time()*1000
        status = read_for(link, 0.4)
        report['status_after'] = status
        acknowledged = acknowledged or "DRIVING" in status
        if not acknowledged:
            raise RuntimeError("No wheel command was acknowledged")
        if "moving=0" not in status or "armed=0" not in status or 'stop_ack=0' in status:
            raise RuntimeError("Stop not verified: "+status)
        report["stopped_disarmed"] = True
        return report
    except Exception as error:
        report["error"] = str(error)
        report["aborted_unix_ms"] = time.time()*1000
        raise TrialError(str(error), report) from error
    finally:
        try:
            link.write(b"DISARM\nSTATUS\n")
            final_status = read_for(link, 0.3)
            report['final_status'] = final_status
            if 'moving=0' in final_status and 'armed=0' in final_status and 'stop_ack=0' not in final_status:
                report['stopped_disarmed'] = True
        except Exception as error:
            report['final_status_error'] = str(error)
        finally:
            link.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("speeds", nargs=4, type=int)
    parser.add_argument("--ms", type=int, default=200)
    parser.add_argument("--ramp-ms", type=int, default=0)
    parser.add_argument("--port", default="COM5")
    parser.add_argument('--pulse', action='store_true', help='One firmware-timed pulse: max speed 60, max 150 ms, no ramp')
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = wheel_step(args.port, args.speeds, args.ms, args.ramp_ms, args.pulse)
    data = json.dumps(report, indent=2)
    if args.report:
        args.report.write_text(data)
    print(data)
