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


def envelope(elapsed_ms, duration_ms, ramp_ms):
    if elapsed_ms < 0 or elapsed_ms >= duration_ms:
        return 0.0
    if ramp_ms == 0:
        return 1.0
    phase = min(1.0, elapsed_ms/ramp_ms, (duration_ms-elapsed_ms)/ramp_ms)
    return phase*phase*(3-2*phase)


def wheel_step(port, speeds, duration_ms, ramp_ms=0):
    if len(speeds) != 4 or any(type(v) is not int or abs(v) > 40 for v in speeds):
        raise ValueError("Four integer wheel speeds in [-40,40] are required")
    if not 20 <= duration_ms <= 1000 or not 0 <= ramp_ms <= duration_ms/2:
        raise ValueError("Duration 20..1000 ms; ramp 0..duration/2")
    link = serial.Serial(port=None, baudrate=115200, timeout=0.005, write_timeout=0.1)
    link.dtr = link.rts = False
    link.port = port
    link.open()
    report = {"speeds": speeds, "duration_ms": duration_ms, "ramp_ms": ramp_ms, "commands": []}
    try:
        read_for(link, 2)
        link.write(b"DISARM\nSTATUS\n")
        status = read_for(link, 0.3)
        if "connected=1" not in status or "moving=0" not in status:
            raise RuntimeError("Rover not ready: "+status)
        link.write(b"ARM\n")
        if "ARMED" not in read_for(link, 0.2):
            raise RuntimeError("Could not arm")
        started = time.monotonic()
        report["started_unix_ms"] = time.time()*1000
        last_ack = started
        acknowledged = False
        while True:
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
        acknowledged = acknowledged or "DRIVING" in status
        if not acknowledged:
            raise RuntimeError("No wheel command was acknowledged")
        if "moving=0" not in status or "armed=0" not in status:
            raise RuntimeError("Stop not verified: "+status)
        report["stopped_disarmed"] = True
        return report
    finally:
        try:
            link.write(b"DISARM\n")
            time.sleep(0.05)
        finally:
            link.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("speeds", nargs=4, type=int)
    parser.add_argument("--ms", type=int, default=200)
    parser.add_argument("--ramp-ms", type=int, default=0)
    parser.add_argument("--port", default="COM5")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = wheel_step(args.port, args.speeds, args.ms, args.ramp_ms)
    data = json.dumps(report, indent=2)
    if args.report:
        args.report.write_text(data)
    print(data)
