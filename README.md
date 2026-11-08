# Team 18 — RoverC Pro

Hardware: M5StickC Plus SE (ESP32-PICO-D4) on the RoverC Pro base. Windows USB port: COM5 on the development computer.

## Tabletop simulator

[simulator/](simulator/README.md) contains a local 3D tabletop rover simulator, editable arenas, bounded controller ROMs, and an automatic Claude Code Opus → sortie → dock → observation → revised ROM loop. The photo-based profile has one panning ultrasonic module and a top light sensor; range/servo/light parameters remain uncalibrated assumptions. Continuous replay includes archived maps, published debriefs and ROM diffs. A [minimal mission-supervisor screen](simulator/supervisor.html) shows agent beliefs and subtitle-length findings, plans and ROM-change reports. The simulator is separate from physical motor control; simulated sensor/odometry assumptions are not hardware measurements.

```bash
cd simulator
python3 server.py
```

Open http://localhost:8765. Python 3.10+, Node.js and an authenticated recent Claude Code CLI are required for automatic Opus experiments; manual simulation does not call a model. Local recordings and credentials are excluded from Git. See the simulator's [public-repository notes](simulator/README.md#public-repository-and-local-data) and [third-party notices](simulator/THIRD_PARTY_NOTICES.md).

## Wireless control

The M5Stick creates a WPA2-protected Wi-Fi network whose name and generated password appear on its screen. Join that network from a phone or laptop, then open **http://192.168.4.1**. No router or internet service is required. The password is saved on the device across reboots, not in this repository; USB serial command `WIFI` prints connection information.

Click **Arm driving**, then hold a direction button (or arrow key; Q/E rotate). Releasing stops movement. STOP/Space, leaving the page, button B, or a lost control connection stops and disarms the rover. One browser owns driving at a time. Commands carry a session token and sequence number so a delayed command cannot override a newer stop.

A separate FreeRTOS task checks the motor deadline every 10 ms and stops on button B or 300 ms without a renewed movement command. Motor I2C operations are serialized with a mutex. This keeps the stop timer independent of HTTP handling; bus latency can add to the stop time.

`node tools/test_control_page.js` checks browser hold/release and focus-loss behavior. Once connected to rover Wi-Fi, `python tools/check_wifi.py` checks the HTTP control API using speed zero. The USB camera is unrelated to this control network.

Hardware validation passed over the rover Wi-Fi: arming, zero-speed movement, stop, delayed-command rejection, timeout disarming, and session revocation. An incomplete HTTP POST also passed: the independent motor task stopped 5 ms after the drive deadline while HTTP processing was waiting. USB stop and unconfigured-sonar checks passed on the same firmware. The development laptop's original Wi-Fi connection was restored after testing.

For custom controllers, `POST /api/arm` returns a session token. Send it in `X-Rover-Token`, and send `X-Rover-Control: 1` on each POST. `POST /api/drive` accepts form fields `d` (F/B/L/R/Q/E), `s` (0–40), and an increasing `seq`. `POST /api/stop` accepts a newer `seq` and preserves the session; `/api/disarm` stops and revokes it. `GET /api/status` reports state and refreshes a valid owner's lease. Renew movement commands at least every 100 ms; idle owners should poll status every 500 ms. Expired commands and obsolete tokens are rejected. No internet-facing service or router port forwarding is needed.

## Keyboard driving over USB

Install Python 3 and run:

```powershell
python -m pip install -r requirements.txt
python controller.py --port COM5
```

Keep USB connected. Click **Connect**, wait for the rover to respond, then click **Arm driving**. Hold an arrow key to move forward/backward or strafe left/right; hold **Q/E** to rotate. The on-screen buttons also work while held. Start with the wheels raised to check directions.

Release the key/button to stop. **Space**, leaving the controller window, or the M5Stick's **B** button stops and disarms driving; click **Arm driving** to resume. Firmware stops after 300 ms without renewed drive commands, including a closed controller or lost USB connection. Speed is limited to 40. No gripper commands are sent.

Serial commands at 115200 baud: `ARM`, `DISARM`, `STOP`, `STATUS`, and `DRIVE <direction> <speed>`. Directions are `F/B/L/R/Q/E`; speed is 0–40. Drive commands require arming and expire after 300 ms. Physical wheel diagnostics with A are available only while disarmed.

Protocol 3 adds built-in buzzer control: `BUZZER` reports state,
`TONE <Hz> <milliseconds> <volume>` plays one finite tone, and `SILENCE` stops it.
Volume is 0?255, tones last 1?5000 ms, and STOP/button B silence audio.
The external Grove speaker is not needed.

Protocol 2 also exposes `SONAR`, `SERVOS`, `SERVO <channel> <angle>` and
`SERVO_US <channel> <microseconds>`. Servo channels are 1 and 2; electrical
ranges are 0–180 degrees or 500–2500 microseconds. Servo commands require arming
with the wheels stopped, then disarm. `SERVOS` reads target registers, not
physical position. Servos hold their last target after STOP; mechanical travel
and channel attachments are not calibrated. `CAPABILITIES` reports the protocol.

For controller calibration, `WHEELS <w0> <w1> <w2> <w3>` accepts four signed speeds in [-40,40], in I2C register order. It uses the same arming, physical stop, mutex, and 300 ms watchdog as `DRIVE`. Invalid input stops the motors. `tools/wheel_step.py` sends one bounded pulse, optionally with a cubic acceleration/braking envelope (`--ramp-ms`); this is a commanded speed profile, not a claim of physically smooth motion. Emergency stopping remains immediate.

### Python control

`tools/rover.py` provides a synchronous serial client using the dependencies in
`requirements.txt`. Run from `tools/`, or add that directory to Python's import
path. Close other serial controllers before opening it.

```python
from rover import Rover

with Rover("COM5", camera_config="../.camera-recorder.json") as rover:
    print(rover.status())
    print(rover.sonar())
    print(rover.servos())
    frame = rover.snapshot()
```

`wheels(values, duration_ms, pulse=False)` commands four signed motor channels;
normal steps allow +/-40 for 20–1000 ms. Firmware-timed pulse steps allow +/-60
for 20–150 ms. Each step attempts stop/disarm even on failure and returns a
report whose `valid` field must be checked. Late or fragmented acknowledgements
are collected without repeating a completed movement.

`servo(channel, angle=...)` or `servo(channel, pulse_us=...)` sets an electrical
target without remapping it. Check the attachment's clearance before use;
electrical limits are not safe mechanical limits. Other methods are
`capabilities()`, `buzzer()`, `tone(frequency, duration_ms, volume=32)`,
`silence()`, and `stop()`. Set `allow_motion=False` to permit observations only.
Use one client per port and one calling thread per client.

Camera access uses the existing recorder without taking ownership of the
device. `snapshot()` returns a base64 PNG plus frame timestamps, and waits for a
frame captured after the request. The configuration file contains the recorder
address and token; keep it outside source control. Omit `camera_config` when
only serial control is needed.

Run the client tests without hardware using
`python -m unittest discover -s tools -p test_rover.py`.

### Wi-Fi control

The firmware keeps its access point available and can also join a 2.4 GHz
network. With the rover stopped and disarmed, send `WIFI_JOIN ` followed by the
SSID, a tab, the password, and a newline over serial. Credentials are stored on
the device. `WIFI` reports its addresses; `WIFI_AP` removes the saved station
credentials. Do not put credentials in source files or commit their output.

`tools/rover_wifi.py` exposes the same controls through `WifiRover(url, key,
camera_config=None)`. The key is the rover's generated access-point password.
All `/api/robot/` routes require it; actuator calls also use an exclusive lease
and increasing sequence numbers. Camera snapshots still come from the host
recorder. The existing browser controller remains available on the rover's
access point.

Wheel commands expire on the controller within 300 ms without renewal; boosted
pulses expire within 150 ms. Connection loss or an expired control lease stops
and disarms the wheels. A lost response is not automatically retried. Servo
targets retain the same mechanical limitations as serial control.

## Onboard movement tests and navigation

`firmware/roverc-test/roverc-test.ino` uses M5Unified and M5GFX. The Plus SE has no IMU, so IMU initialization is disabled. Rover communication uses I2C bus 0 (M5Unified reserves bus 1 for internal peripherals), SDA GPIO 0, SCL GPIO 26, and I2C address 0x38, following M5Stack's RoverC Pro example.

The firmware stops all motors at startup. It does not move automatically or command the gripper.

- Lift the rover so its wheels are clear before testing.
- Click button A to move the whole rover at speed 20 for 200 milliseconds, then stop. Successive clicks test forward, reverse, strafe left/right, and rotate left/right. The screen shows the next direction. No USB connection is needed for these tests.
- Hold button A to request autonomous mode; it requires a fresh valid sonar reading.
- Button B stops all motors.
- The screen reports whether the rover responds on I2C.
- USB serial commands are terminated by a newline.

Keep the rear power switch within reach. The timed stop runs on the M5Stick; switching off the base is the fallback if the controller hangs. Movement tests execute known motor commands; they do not measure or learn displacement. Speed and timing still need calibration on the actual surface.

`Navigator.h` is an onboard reactive obstacle-avoidance policy. With a valid forward-facing sonar, it drives forward, stops at 300 mm, and turns in 120 ms pulses until two distinct readings show at least 500 mm clearance. It stops on invalid/stale readings (over 200 ms old) or after three seconds of unsuccessful turning. This is local avoidance, not mapping, path planning, or a trained policy. A single front sonar cannot detect every side obstacle or drop-off.

`Sonar.h` reads the Seeed Grove Ultrasonic Ranger's shared trigger/echo signal
on GPIO33, verified with the sensor and cable connected to this rover's StickC
Grove socket. Measurements
are spaced at least 60 ms apart and time out after 25 ms; no echo is invalid,
not clear space. Set `ROVER_SONAR_PIN=-1` when that sensor is absent. The camera
remains external and is not an input to the onboard navigator. The 300 ms USB
command expiry applies to externally commanded driving.

## Validation

Compilation and upload passed. On-device startup reached ROVER_TEST_READY and detected the RoverC Pro at I2C address 0x38 with motors stopped. The user confirmed the physical wheel test works. Keyboard driving direction and rotation still require physical testing.

`python tools/check_stop.py --port COM5` passed on hardware using speed zero: disarmed drive rejection, armed command acceptance, 300 ms expiry, latched disarm, and overlong-command stop. The desktop controller connection, idle arming, and disarming also passed without movement. Close the controller before running this check so the serial port is free.

The onboard-agent update compiled, uploaded with flash hash verification, and passed the hardware check that `AUTO` refuses to run without sonar. `tools/test_navigation.cpp` passed as a native C++ test, including close-obstacle stopping, fresh independent clearance samples, sensor failure, bounded turning, and timer rollover. Whole-body A-button movement tests and navigation with a real sonar still need physical validation.

## Build

Validated dependency targets: Espressif Arduino core 2.0.17, M5Unified 0.2.2, M5GFX 0.2.3. The `m5stick-c` target supplies the ESP32 configuration; M5Unified handles the Plus display and AXP192 power controller.

```powershell
arduino-cli core install esp32:esp32@2.0.17 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli lib install M5Unified@0.2.2 M5GFX@0.2.3
arduino-cli compile --fqbn esp32:esp32:m5stick-c --build-property build.flash_freq=40m firmware/roverc-test
arduino-cli upload --fqbn esp32:esp32:m5stick-c --port COM5 --upload-property upload.speed=115200 --upload-property build.flash_freq=40m firmware/roverc-test
```

The local toolchain, builds, and original firmware backup are outside this repository in `../roverc-tools/`. Do not publish flash backups; they can contain device settings.

References: [Plus SE hardware](https://docs.m5stack.com/en/core/StickC-Plus_SE), [RoverC Pro](https://docs.m5stack.com/en/hat/hat_roverc_pro), [official RoverC source](https://github.com/m5stack/M5-ProductExampleCodes/blob/master/Application/RoverC_PRO_Arduino_Alone/RoverC.cpp).

## Aurora 930 Pro depth camera

Continuous progress video is recorded to the development machine's external
drive at `D:\Team18-Recordings`. The background recorder shares snapshots with
the calibration tools rather than competing for the camera. See
[recording setup and controls](docs/camera-recording.md).

Direct color capture now works on Windows ARM via the vendor's x64 SDK under emulation. `tools/camera_capture.cpp` uses the SDK headers and DLL; `tools/build_camera.ps1` builds it with the Visual Studio C++ tools. Pass the vendor SDK include directory to `-SdkInclude`, put the viewer directory on PATH, and run `camera_capture.exe <output-directory>`. Close DeptrumScope first because it owns the camera exclusively. Decode the saved color frame with `python tools/decode_camera.py <output-directory>`.

Verified output is a 640×400 NV12 color frame, visually inspected with the rover and table obstacles visible. Depth bytes are saved for future analysis, but depth units/metadata are not yet validated. Some vendor image-format fields are unset; the decoder instead checks the configured YUV mode and exact frame size. Camera frames and vendor binaries stay outside Git.

`tools/supervised_step.py` executes one USB movement step, bounded to 1000 ms and speed 40, then verifies stopped/disarmed state. Commands renew every 80 ms while the step runs; the firmware still expires each command after 300 ms. It aborts immediately on reported motor errors or controller reset. Inspect a fresh camera frame before each step and capture a new frame afterward; this command does not inspect images or learn motion itself.

`tools/measure_motion.py` compares a selected rigid rover patch in two images and reports camera-plane displacement and correlation. It is not calibrated metric odometry, and rotation, occlusion or cable drag can invalidate the estimate. Synthetic translation and textureless-image tests are in `tools/test_motion_measurement.py`.

`tools/camera_pose.py` estimates the visible orange board's center and axis from an operator-selected crop and approximate heading. It is a legacy heuristic: orange wires and background objects can bias its angle, so its historical sub-degree residuals are not validated physical accuracy. A new cyan/magenta reference on the M5Stick display and `tools/marker_pose.py` separate the robot reference from that clutter; see [screen-marker calibration](docs/screen-marker-calibration.md). See [physical calibration observations](docs/physical-calibration.md) for historical measurements and limitations. This is not yet a repeatable autonomous controller.

`tools/visual_heading.py` uses the measured Q-turn gain to propose one correction from a fresh camera frame; `--execute` performs that single bounded correction and measures the result. Hardware validation reduced an 18.73° error to 2.95°. Other directions are still uncalibrated.

`camera_capture.exe <directory> <count>` records up to 300 color frames with timestamps (the default remains one RGBD snapshot). `tools/record_wheel_trial.py` records before, during and after one wheel pulse; `tools/analyze_trial.py` extracts a trajectory and reports the measured change. The camera is external ground truth for learning and evaluating the controller. It is not an input to the eventual onboard autonomous policy. Precision and smoothness are still under active calibration.

All authored source is kept here: reusable setup helpers are in `tools/setup/`, diagnostic helpers in `tools/diagnostics/`, and control/calibration tools in `tools/`. Setup scripts take local paths/device IDs as arguments. The WinUSB helper defaults to inspecting the driver; `-Install` explicitly changes the selected camera's driver. The Wi-Fi diagnostic requires `-AllowNetworkSwitch` because it temporarily interrupts normal Wi-Fi. Vendor SDKs, installed toolchains, generated binaries, recordings, credentials and flash backups remain local and are not published.

Physical feedback trials: a speed-40 forward pulse for 600 ms produced clear image displacement; 180–250 ms pulses at speeds 25–30 barely moved. A lateral pulse induced significant rotation, so ideal mecanum kinematics do not yet predict this unit accurately. A subsequent rotation reported a transient rover I2C error and disarmed; communication recovered after reset. Motion calibration is incomplete, and autonomous obstacle avoidance has not been demonstrated.

Windows 11 ARM64 detects the camera as USB VID `3251`, PID `1930`. The vendor's bundled INF supports x86/x64 only. This development computer instead uses Microsoft's signed, inbox ARM64 `winusb.inf` / `WinUSB.sys` driver, selected for this camera through SetupAPI. The vendor interface GUID `{ca3e7ab9-b4c3-4ae6-8251-579ef933890f}` is registered in the camera's Device Parameters. No unsigned driver package or driver-signature bypass was used.

Device status is OK with problem code 0. Hiwonder's DeptrumScope 3.6.17 runs under Windows x64 emulation; its log confirms `model: Aurora 930` and a successful device connection. Live depth frames still need visual confirmation: open the viewer's **2D** tab and click **Start** under **Stream & Capture**, following the [official Windows guide](https://wiki.hiwonder.com/projects/Aurora930-Pro/en/latest/docs/3.Configuration_and_Usage_in_Windows.html).

The viewer, extracted driver reference, and local installation helper are in `C:\Users\naclo\Downloads\Aurora930-Pro`. These third-party binaries are kept outside the repository. The camera is not yet connected to rover navigation or obstacle avoidance.




The optional Grove IMU 10DOF connects to a RoverC base I2C socket; the sonar
remains on the M5Stick Grove socket. A passive I2C hub cannot combine these two
interfaces. Install `Adafruit BMP280 Library@2.6.8` and its dependencies before
building firmware. `IMU` over serial and `GET /api/robot/imu` over Wi-Fi return
sensor-axis acceleration in g, angular velocity in degrees/s, magnetic field
in microtesla, pressure in Pa, and temperature in Celsius. Each sensor has a
validity flag; unavailable samples are null. These are measurements, not wheel
encoders or a calibrated position estimate. Python clients expose `imu()`.
