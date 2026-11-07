"""Check arming and command expiry using speed zero (no wheel motion)."""
import argparse
import time

import serial


def read_for(link, seconds):
    end = time.monotonic() + seconds
    data = b""
    while time.monotonic() < end:
        data += link.read(4096)
    return data.decode("utf-8", errors="replace")


def check(port):
    link = serial.Serial(port=None, baudrate=115200, timeout=0.05, write_timeout=0.2)
    link.dtr = link.rts = False
    link.port = port
    link.open()
    try:
        # Wait for any USB-open reset to finish. No nonzero drive command is sent.
        read_for(link, 3)

        def send(command, wait=0.15):
            link.write((command + "\n").encode("ascii"))
            return read_for(link, wait)

        send("DISARM")
        assert "DISARMED" in send("DRIVE F 0"), "Drive accepted while disarmed"
        assert "ARMED" in send("ARM"), "Rover did not arm"
        assert "DRIVING" in send("DRIVE F 0", 0.08), "Zero-speed drive was not accepted"
        status = send("STATUS", 0.08)
        assert "moving=1" in status and "armed=1" in status, status
        expired = read_for(link, 0.5) + send("STATUS")
        assert "TIMED_STOP" in expired and "moving=0" in expired, expired
        send("DISARM")
        assert "DISARMED" in send("DRIVE F 0"), "Disarm did not latch"
        send("ARM")
        assert "INVALID_COMMAND" in send("X" * 50, 0.5), "Overlong command not rejected"
        status = send("STATUS")
        assert "moving=0" in status and "armed=0" in status, status
        assert "SONAR_UNAVAILABLE" in send("AUTO"), "Unconfigured sonar allowed autonomy"
        status = send("STATUS")
        assert "moving=0" in status and "sonar_configured=0" in status, status
        print("PASS: arming, 300ms command expiry, disarm, and malformed-command stop; all speeds zero.")
        print("PASS: autonomous mode refused without a configured sonar.")
    finally:
        try:
            link.write(b"DISARM\n")
            time.sleep(0.1)
        finally:
            link.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM5")
    check(parser.parse_args().port)
