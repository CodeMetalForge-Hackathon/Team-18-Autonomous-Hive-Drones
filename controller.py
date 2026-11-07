"""USB keyboard controller for the Team 18 RoverC Pro firmware."""
import argparse
import time
import tkinter as tk
from tkinter import ttk

import serial
from serial.tools import list_ports

KEYS = {"Up": "F", "Down": "B", "Left": "L", "Right": "R", "q": "Q", "e": "E"}


class Controller:
    def __init__(self, root, port):
        self.root = root
        self.link = None
        self.ready = self.armed = False
        self.direction = None
        self.last_rx = self.last_status = 0
        self.buffer = ""
        root.title("Team 18 — RoverC Pro")
        root.geometry("540x560")
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="RoverC Pro", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Hold an arrow key to drive • Q / E to rotate").pack(anchor="w", pady=(4, 14))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        self.port = tk.StringVar(value=port)
        ports = [p.device for p in list_ports.comports()]
        ttk.Combobox(row, textvariable=self.port, values=ports, width=12).pack(side="left")
        self.connect_button = ttk.Button(row, text="Connect", command=self.connect)
        self.connect_button.pack(side="left", padx=8)
        ttk.Button(row, text="Arm driving", command=self.arm).pack(side="left")
        self.status = tk.StringVar(value="Disconnected. Connect, then arm driving.")
        ttk.Label(frame, textvariable=self.status, wraplength=460).pack(anchor="w", pady=14)
        self.speed = tk.IntVar(value=25)
        speed_row = ttk.Frame(frame)
        speed_row.pack(fill="x")
        ttk.Label(speed_row, text="Speed (10–40)").pack(side="left")
        tk.Scale(speed_row, from_=10, to=40, orient="horizontal", variable=self.speed,
                 length=260).pack(side="left", padx=14)
        grid = ttk.Frame(frame)
        grid.pack(pady=12)
        for label, direction, r, c in [
            ("↖ Rotate Q", "Q", 0, 0), ("↑ Forward", "F", 0, 1), ("Rotate E ↗", "E", 0, 2),
            ("← Strafe", "L", 1, 0), ("↓ Reverse", "B", 1, 1), ("Strafe →", "R", 1, 2),
        ]:
            button = ttk.Button(grid, text=label, width=16)
            button.grid(row=r, column=c, padx=3, pady=4, ipady=8)
            button.bind("<ButtonPress-1>", lambda event, d=direction: self.start(d))
        ttk.Button(frame, text="STOP / DISARM — Space", command=self.disarm).pack(fill="x", ipady=8)
        ttk.Label(frame, text="Release to stop. Firmware stops after 300 ms without commands.\n"
                  "The M5Stick’s B button also disarms driving.", wraplength=460).pack(anchor="w", pady=12)
        root.bind("<KeyPress>", self.key_down)
        root.bind("<KeyRelease>", self.key_up)
        root.bind_all("<ButtonRelease-1>", lambda event: self.stop())
        root.bind("<FocusOut>", lambda event: root.after_idle(self.check_focus))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(50, self.tick)

    def send(self, message):
        if not self.link:
            return False
        try:
            self.link.write((message + "\n").encode("ascii"))
            return True
        except (serial.SerialException, OSError) as exc:
            self.disconnect(f"Connection lost: {exc}")
            return False

    def connect(self):
        if self.link:
            self.send("DISARM")
            self.disconnect("Disconnected.")
            return
        try:
            link = serial.Serial(port=None, baudrate=115200, timeout=0, write_timeout=0.1)
            link.dtr = link.rts = False
            link.port = self.port.get()
            link.open()
            self.link = link
            self.ready = self.armed = False
            self.direction = None
            self.buffer = ""
            self.last_rx = time.monotonic()
            self.last_status = 0
            self.connect_button.configure(text="Disconnect")
            self.status.set("Connected. Waiting for rover firmware…")
            self.send("DISARM")
        except (serial.SerialException, OSError) as exc:
            self.status.set(str(exc))

    def disconnect(self, message):
        self.ready = self.armed = False
        self.direction = None
        if self.link:
            try:
                self.link.close()
            except (serial.SerialException, OSError):
                pass
        self.link = None
        self.connect_button.configure(text="Connect")
        self.status.set(message)

    def arm(self):
        if self.ready:
            self.direction = None
            self.send("ARM")
            self.root.focus_set()
        else:
            self.status.set("Connect and wait for the rover to respond first.")

    def start(self, direction):
        if self.armed:
            self.direction = direction

    def stop(self):
        if self.direction:
            self.direction = None
            self.send("STOP")

    def disarm(self):
        self.direction = None
        self.armed = False
        self.send("DISARM")
        self.status.set("Stopped and disarmed. Click Arm driving to resume.")

    def check_focus(self):
        if self.root.focus_displayof() is None and self.armed:
            self.disarm()

    def key_down(self, event):
        if event.keysym == "space":
            self.disarm()
        elif event.keysym in KEYS:
            self.start(KEYS[event.keysym])

    def key_up(self, event):
        if KEYS.get(event.keysym) == self.direction:
            self.stop()

    def receive(self, line):
        self.last_rx = time.monotonic()
        if line.startswith("ROVER_TEST_READY"):
            self.ready = self.armed = False
            self.direction = None
            self.send("DISARM")
            self.send("STATUS")
        elif line.startswith("ROVER_STATUS"):
            self.ready = "connected=1" in line
            self.armed = "armed=1" in line
            if not self.armed:
                self.direction = None
            self.status.set("Armed — hold a direction to drive." if self.armed else
                            "Rover ready. Click Arm driving." if self.ready else
                            "Rover not detected. Check its power and connection.")
        elif line == "ARMED":
            self.armed = True
            self.status.set("Armed — hold a direction to drive.")
        elif line in ("DISARMED", "ROVER_NOT_FOUND", "INVALID_COMMAND", "INVALID_DIRECTION"):
            self.armed = False
            self.direction = None
            self.status.set(f"Stopped: {line}. Click Arm driving to resume.")

    def tick(self):
        if self.link:
            try:
                self.buffer += self.link.read(8192).decode("utf-8", errors="replace").replace("\r", "")
                if len(self.buffer) > 16384:
                    self.buffer = self.buffer[-8192:]
                while "\n" in self.buffer:
                    line, self.buffer = self.buffer.split("\n", 1)
                    self.receive(line.strip())
            except (serial.SerialException, OSError) as exc:
                self.disconnect(f"Connection lost: {exc}")
            now = time.monotonic()
            if self.link and self.armed and now - self.last_rx > 0.8:
                self.send("DISARM")
                self.disconnect("No response from rover. Reconnect to continue.")
            elif self.link:
                if self.armed and self.direction:
                    self.send(f"DRIVE {self.direction} {self.speed.get()}")
                if now - self.last_status > 0.3:
                    self.last_status = now
                    self.send("STATUS")
        self.root.after(100, self.tick)

    def close(self):
        self.send("DISARM")
        self.disconnect("Closed")
        self.root.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM5")
    args = parser.parse_args()
    root = tk.Tk()
    Controller(root, args.port)
    root.mainloop()
