import time
import tkinter as tk
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import controller
root = tk.Tk()
root.withdraw()
app = controller.Controller(root, 'COM5')
def pump(seconds):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        root.update()
        time.sleep(0.01)
try:
    app.connect()
    pump(3)
    assert app.ready, app.status.get()
    app.arm()
    pump(1.5)
    assert app.armed, app.status.get()
    app.disarm()
    pump(0.4)
    assert not app.armed
    print('PASS: desktop controller connects, arms while idle, and disarms without movement.')
finally:
    app.close()
