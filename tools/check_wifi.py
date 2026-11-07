"""Exercise Wi-Fi control with speed zero; close other control pages first."""
import argparse
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request


def check(base):
    token = ""

    def call(path, data=None, authenticated=True, expected=200):
        headers = {"X-Rover-Control": "1"}
        if authenticated:
            headers["X-Rover-Token"] = token
        body = None if data is None else urllib.parse.urlencode(data).encode()
        request = urllib.request.Request(base + path, data=body, headers=headers)
        # The rover network is local and must not go through a system proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=8) as response:
                status, result = response.status, json.load(response)
        except urllib.error.HTTPError as error:
            status, result = error.code, json.load(error)
        assert status == expected, (path, status, result)
        return result

    try:
        status = call("/api/status")
        assert status["connected"], status
        token = call("/api/arm", {})["token"]
        call("/api/drive", {"d": "F", "s": 0, "seq": 1})
        assert call("/api/status")["moving"]
        call("/api/stop", {"seq": 2})
        assert not call("/api/status")["moving"]
        call("/api/drive", {"d": "F", "s": 0, "seq": 1}, expected=409)
        assert not call("/api/status")["moving"], "Late drive restarted after stop"
        call("/api/drive", {"d": "F", "s": 0, "seq": 3})
        time.sleep(0.6)
        status = call("/api/status")
        assert not status["moving"] and not status["owner"] and not status["armed"], status
        call("/api/drive", {"d": "F", "s": 0, "seq": 4}, expected=409)
        print("PASS: Wi-Fi arm, zero-speed drive, stop, stale-command rejection, timeout and lease revocation.")
        token = call("/api/arm", {})["token"]
        call("/api/drive", {"d": "F", "s": 0, "seq": 1})
        deadline = call("/api/status")["drive_deadline_ms"]
        host = urllib.parse.urlsplit(base).hostname
        port = urllib.parse.urlsplit(base).port or 80
        with socket.create_connection((host, port), timeout=3) as slow:
            # Leave a POST body incomplete so HTTP processing waits on the client.
            slow.sendall(("POST /api/drive HTTP/1.1\r\nHost: " + host +
                          "\r\nContent-Type: application/x-www-form-urlencoded\r\n"
                          "Content-Length: 100\r\nX-Rover-Control: 1\r\n"
                          "X-Rover-Token: " + token + "\r\n\r\nd=F").encode())
            time.sleep(1)
        status = call("/api/status")
        assert not status["moving"] and not status["armed"], status
        delay = (status["watchdog_stop_ms"] - deadline) & 0xFFFFFFFF
        assert delay < 200, ("Watchdog waited on HTTP", delay, status)
        print(f"PASS: independent watchdog stopped {delay}ms after deadline during an incomplete HTTP request.")
    finally:
        try:
            call("/api/disarm", {})
        except Exception:
            pass  # The device-side watchdog remains responsible for stopping.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://192.168.4.1")
    check(parser.parse_args().url.rstrip("/"))
