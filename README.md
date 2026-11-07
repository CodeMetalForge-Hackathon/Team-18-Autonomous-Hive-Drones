# Team 18 — RoverC Pro

Hardware: M5StickC Plus SE (ESP32-PICO-D4) on the RoverC Pro base. Windows USB port: COM5 on the development computer.

## Tabletop simulator

[simulator/](simulator/README.md) contains a local 3D tabletop rover simulator, editable arenas, bounded controller ROMs, and an automatic Claude Code Opus → sortie → dock → observation → revised ROM loop. Continuous replay includes archived maps, published debriefs and ROM diffs. The simulator is separate from physical motor control; simulated sensor/odometry assumptions are not hardware measurements.

```bash
cd simulator
python3 server.py
```

Open http://localhost:8765. Python 3.10+, Node.js and an authenticated recent Claude Code CLI are required for automatic Opus experiments; manual simulation does not call a model. Local recordings and credentials are excluded from Git. See the simulator's [public-repository notes](simulator/README.md#public-repository-and-local-data) and [third-party notices](simulator/THIRD_PARTY_NOTICES.md).

## Wireless control

The M5Stick creates a WPA2-protected Wi-Fi network whose name and generated password appear on its screen. Join that network from a phone or laptop, then open **http://192.168.4.1**. No router or internet service is required. The password is saved on the device across reboots, not in this repository; USB serial command `WIFI` prints connection information.

Click **Arm driving**, then hold a direction button (or arrow key; Q/E rotate). Releasing stops movement. STOP/Space, leaving the page, button B, or a lost control connection stops and disarms the rover. One browser owns driving at a time. Commands carry a session token and sequence number so a delayed command cannot override a newer stop.

A separate FreeRTOS task checks the motor deadline every 10 ms and stops on button B or 300 ms without a renewed movement command. Motor I2C operations are serialized with a mutex. This keeps the stop timer independent of HTTP handling; bus latency can add to the stop time. Autonomous navigation remains disabled without the sonar driver.

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

## Onboard movement tests and navigation

`firmware/roverc-test/roverc-test.ino` uses M5Unified and M5GFX. The Plus SE has no IMU, so IMU initialization is disabled. Rover communication uses I2C bus 0 (M5Unified reserves bus 1 for internal peripherals), SDA GPIO 0, SCL GPIO 26, and I2C address 0x38, following M5Stack's RoverC Pro example.

The firmware stops all motors at startup. It does not move automatically or command the gripper.

- Lift the rover so its wheels are clear before testing.
- Click button A to move the whole rover at speed 20 for 200 milliseconds, then stop. Successive clicks test forward, reverse, strafe left/right, and rotate left/right. The screen shows the next direction. No USB connection is needed for these tests.
- Hold button A to request autonomous mode. It currently refuses to start because the physical sonar model and connection have not been supplied.
- Button B stops all motors.
- The screen reports whether the rover responds on I2C.
- USB serial commands are terminated by a newline.

Keep the rear power switch within reach. The timed stop runs on the M5Stick; switching off the base is the fallback if the controller hangs. Movement tests execute known motor commands; they do not measure or learn displacement. Speed and timing still need calibration on the actual surface.

`Navigator.h` is an onboard reactive obstacle-avoidance policy. With a valid forward-facing sonar, it drives forward, stops at 300 mm, and turns in 120 ms pulses until two distinct readings show at least 500 mm clearance. It stops on invalid/stale readings (over 200 ms old) or after three seconds of unsuccessful turning. This is local avoidance, not mapping, path planning, or a trained policy. A single front sonar cannot detect every side obstacle or drop-off.

`Sonar.h` deliberately returns invalid data until the actual sensor model, voltage and wiring are known. Do not substitute clear-distance constants. The eventual driver must timestamp successful physical readings and return invalid data for errors/no echo. The camera is for external supervision only and is not an input to the onboard agent. Autonomous mode will run without a laptop once a real sensor driver is implemented; the 300 ms USB command expiry applies to manual driving.

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

Windows 11 ARM64 detects the camera as USB VID `3251`, PID `1930`. The vendor's bundled INF supports x86/x64 only. This development computer instead uses Microsoft's signed, inbox ARM64 `winusb.inf` / `WinUSB.sys` driver, selected for this camera through SetupAPI. The vendor interface GUID `{ca3e7ab9-b4c3-4ae6-8251-579ef933890f}` is registered in the camera's Device Parameters. No unsigned driver package or driver-signature bypass was used.

Device status is OK with problem code 0. Hiwonder's DeptrumScope 3.6.17 runs under Windows x64 emulation; its log confirms `model: Aurora 930` and a successful device connection. Live depth frames still need visual confirmation: open the viewer's **2D** tab and click **Start** under **Stream & Capture**, following the [official Windows guide](https://wiki.hiwonder.com/projects/Aurora930-Pro/en/latest/docs/3.Configuration_and_Usage_in_Windows.html).

The viewer, extracted driver reference, and local installation helper are in `C:\Users\naclo\Downloads\Aurora930-Pro`. These third-party binaries are kept outside the repository. The camera is not yet connected to rover navigation or obstacle avoidance.



