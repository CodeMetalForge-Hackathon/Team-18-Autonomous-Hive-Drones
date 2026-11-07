# Screen reference for camera-supervised calibration

The original `camera_pose.py` detector used the orange board's color and a
principal axis. Wires and background objects could bias that axis. Its reported
angle residuals must not be treated as validated physical yaw accuracy.

The new `MARKER` firmware command stops/disarms motion and shows large cyan and
magenta blocks at opposite ends of the M5Stick display. `UI` also stops/disarms
and restores the normal status screen. Serial control and the physical stop
button continue to work while the reference is displayed.

`tools/camera_marker.py` enables the reference; `--restore-ui` restores status.
`tools/marker_pose.py` finds the two separate color regions and computes their
centers, separation and directed axis. Its `--front` option specifies which
display end points toward the gripper. This must be established from a camera
view, not assumed from the display rotation setting. Missing or implausibly
close markers are rejected.

`tools/analyze_trial.py --marker-front cyan|magenta` measures recorded trials
using this reference instead of the older detector. Do not mix calibration
samples from the two detector versions. The markers still measure an image
projection, not metric world position or physical yaw. Check stationary-frame
variation and camera placement before claiming precision.

On the initial stationary trial, 36 frames produced standard deviations of
0.028/0.052 image pixels for the marker center and 0.338 degrees for the marker
axis. This is a repeatability measurement, not an absolute physical-yaw
calibration. On this mounted display, the cyan marker is toward the gripper.
The camera renders the magenta panel region predominantly blue, so detection
uses its observed blue/green contrast. After clearing the wires and correcting
that color model, another stationary trial measured about 0.3 degrees of angle
variation and under 0.04 pixels of center variation. Recordings with over 20%
missing detections or over 2 degrees of resting angle variation are rejected;
rejected analyses are marked invalid rather than leaving stale accepted data.

The camera remains an external calibration/supervision tool. The screen marker
does not send camera data to the onboard autonomous controller.

## Bounded higher-speed characterization

The separate serial `PULSE <milliseconds> <w0> <w1> <w2> <w3>` command permits
wheel values in [-60,60] for 20–150 ms. It requires arming, refuses to overlap an
active movement, and uses the independent on-device stop task. The host sends
the pulse once and checks the timed-stop response. This permits testing motor
breakaway and steering headroom without raising ordinary driving limits.
`DRIVE` and `WHEELS` remain limited to 40.

The underlying hardware protocol supports signed motor values up to 127;
see the [M5Stack register reference](https://docs.m5stack.com/en/protocol/K036-B/I2C).
These calibration pulse limits are our smaller test bounds, not a manufacturer
claim about precise speed. Use `record_wheel_trial.py --pulse` to record one
such trial, with a freshly inspected clear area.

The motor controller now reports `stop_ack` separately: it means all four zero
speed writes were acknowledged on I2C, not that an encoder measured zero wheel
speed. Failed stops remain pending and the independent task retries them;
arming requires acknowledgement. Repeated STOP/DISARM calls do not resend
already-acknowledged zero commands unnecessarily. Actual motion is still
checked with the external camera.
