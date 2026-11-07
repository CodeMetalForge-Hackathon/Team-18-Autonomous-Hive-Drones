# External-camera motion observations

Measured on 2026-11-07 with the USB-tethered RoverC Pro on the current tabletop.
These are supervision measurements, **not parameters validated for onboard
autonomy**. The external camera never supplies observations to `Navigator`.

`tools/camera_pose.py` measures the orange controller board's centroid and long
axis within a manually selected crop. Coordinates are image pixels; positive
angles turn clockwise from image-right. An operator supplies an approximate
heading to resolve the axis's 180-degree ambiguity. Perspective makes these
image angles different from physical yaw; they are not calibrated world units.
The board center is above and offset from the ground contact point.

All pulses below used speed 40. Each completed with the firmware reporting
`connected=1 moving=0 armed=0`. Every subsequent pulse followed inspection of a
new camera frame. Raw images stay outside Git in the development computer's
`roverc-tools/calibration` directory.

| Frame after pulse | Command | Duration ms | Board x | Board y | Image heading |
|---|---|---:|---:|---:|---:|
| resume-before | baseline | — | 433.33 | 150.82 | -56.07° |
| q-200 | Q | 200 | 425.19 | 147.00 | -33.74° |
| q-300 | Q | 300 | 417.49 | 136.49 | -0.15° |
| east-f-400 | F | 400 | 440.77 | 115.07 | -32.72° |
| reverse-400 | B | 400 | 407.14 | 140.62 | -19.39° |
| correct-q-150 | Q | 150 | 409.99 | 136.21 | 3.48° |
| correct-f-200 | F | 200 | 437.23 | 131.85 | -24.27° |
| correct-q-180 | Q | 180 | 427.86 | 134.83 | 0.95° |

## What this establishes

- Q consistently increased image heading in these trials, about 112–152 image
  degrees/second. It also translated the board; it is not a perfect in-place turn.
- F moved the robot but introduced significant negative heading drift. Pulse
  duration alone did not predict translation reliably. A fixed ideal mecanum
  model is not yet justified.
- One measured feedback correction succeeded: after F200 changed heading from
  +3.48° to -24.27°, Q180 brought it back to +0.95°. The combined step advanced
  the board about 18 pixels right with about 1 pixel upward displacement.
- This demonstrates a single supervised move–observe–correct sequence, not
  repeatable autonomous navigation or a general learned controller.

The commands match the motor signs in M5Stack's
[official RoverC example](https://github.com/m5stack/M5-ProductExampleCodes/blob/master/Application/RoverC_PRO_Arduino_Alone/RoverC.cpp).
Uneven traction, a wheel/motor problem and tether forces remain possible causes
of drift; the current observations do not identify which. Next work should
check repeatability and individual-wheel behavior before changing motor gains.
Sonar identification and a real sensor driver are still required for the
device-only obstacle-avoidance policy.

Example measurement (manually select a crop containing only the board):

```powershell
python tools/camera_pose.py ../roverc-tools/calibration/correct-q-180/color.png --box 395 100 90 85 --heading 0
python -m unittest discover -s tools -p test_camera_pose.py
```
