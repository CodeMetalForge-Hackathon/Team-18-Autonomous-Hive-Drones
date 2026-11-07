"""One bounded USB movement step; camera supervision remains external.

Use only after inspecting a recent camera frame for clearance. The firmware's
independent watchdog provides a second stop if the host exits unexpectedly.
"""
import argparse
import time
import serial


def read_for(link, seconds):
    end = time.monotonic() + seconds
    output = b""
    while time.monotonic() < end:
        output += link.read(4096)
    return output.decode(errors="replace")


def step(port, direction, speed, milliseconds):
    if direction not in "FBLRQE" or len(direction) != 1:
        raise ValueError("Unknown direction")
    if not 0 <= speed <= 30 or not 20 <= milliseconds <= 250:
        raise ValueError("Supervised steps are limited to speed 30 and 250 ms")
    link = serial.Serial(port=None, baudrate=115200, timeout=0.01, write_timeout=0.1)
    link.dtr = link.rts = False
    link.port = port
    link.open()
    try:
        read_for(link, 2)
        link.write(b"DISARM\nSTATUS\n")
        status = read_for(link, 0.3)
        if "connected=1" not in status or "moving=0" not in status:
            raise RuntimeError("Rover not ready: " + status)
        link.write(b"ARM\n")
        if "ARMED" not in read_for(link, 0.2):
            raise RuntimeError("Rover did not arm")
        started = time.monotonic()
        link.write(f"DRIVE {direction} {speed}\n".encode())
        result = read_for(link, milliseconds / 1000)
        link.write(b"STOP\nDISARM\nSTATUS\n")
        stopped = read_for(link, 0.4)
        if "DRIVING" not in result or "moving=0" not in stopped or "armed=0" not in stopped:
            raise RuntimeError("Step not confirmed: " + result + stopped)
        print(f"STEP direction={direction} speed={speed} requested_ms={milliseconds}")
        print(result + stopped)
    finally:
        try:
            link.write(b"DISARM\n")
            time.sleep(0.05)
        finally:
            link.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("direction", choices=list("FBLRQE"))
    parser.add_argument("--speed", type=int, default=20)
    parser.add_argument("--ms", type=int, default=150)
    parser.add_argument("--port", default="COM5")
    args = parser.parse_args()
    step(args.port, args.direction, args.speed, args.ms)
