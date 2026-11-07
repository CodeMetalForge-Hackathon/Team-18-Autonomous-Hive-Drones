"""One camera-feedback heading correction in a manually cleared test area.

Default: capture and propose only. --execute authorizes one bounded rotation,
then a second capture to measure the result. No path planning, repeated motion,
or connection to the onboard navigator. Current calibration supports Q only.
"""
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import time
import uuid

from PIL import Image

from camera_pose import board_pose
from decode_camera import decode
from supervised_step import step
from camera_shared import CONFIG, snapshot


# Independently inspected camera measurements; see physical-calibration.md.
Q_SAMPLES = [(200, 22.33), (300, 33.59), (150, 22.87), (180, 25.22), (120, 13.69)]
Q_GAIN = statistics.median(degrees / ms for ms, degrees in Q_SAMPLES)


def proposal(heading, target, tolerance=5):
    if not all(math.isfinite(v) for v in (heading, target, tolerance)) or not 0 < tolerance <= 10:
        raise ValueError("Invalid heading or tolerance")
    error = (target-heading+180) % 360-180
    if abs(error) <= tolerance:
        return {"action": "none", "error_degrees": error}
    if error < 0:
        raise ValueError("E rotation is not yet calibrated; no command issued")
    if error > 35:
        raise ValueError("Requested correction exceeds the 35 degree test limit")
    ms = round(error/Q_GAIN/10)*10
    if not 60 <= ms <= 250:
        raise ValueError("Correction outside the calibrated 60–250 ms step limit")
    return {"action": "Q", "speed": 40, "milliseconds": ms,
            "error_degrees": error, "gain_degrees_per_ms": Q_GAIN}


def capture(executable, folder, environment, box, heading):
    # Unique folders prevent a failed capture from reusing an old image.
    folder.mkdir(parents=True, exist_ok=False)
    if CONFIG.exists():
        snapshot(folder)
    else:
        process = subprocess.run([str(executable), str(folder)], env=environment,
                                 capture_output=True, timeout=25)
        (folder/"capture.log").write_bytes(process.stdout + process.stderr)
        if process.returncode:
            raise RuntimeError(f"Camera capture failed; inspect {folder/'capture.log'}")
    decode(folder)
    with Image.open(folder/"color.png") as image:
        return board_pose(image, box, heading)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-exe", type=Path, required=True)
    parser.add_argument("--dll-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--box", nargs=4, type=int, required=True)
    parser.add_argument("--heading", type=float, required=True)
    parser.add_argument("--target", type=float, required=True)
    parser.add_argument("--port", default="COM5")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    run = args.output/(time.strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    environment = dict(os.environ)
    environment["PATH"] = str(args.dll_directory)+os.pathsep+environment.get("PATH", "")
    report = {"executed": False, "target_degrees": args.target,
              "scope": "external supervision; one rotation in manually cleared area"}
    try:
        report["before"] = capture(args.camera_exe, run/"before", environment,
                                    args.box, args.heading)
        command = proposal(report["before"]["heading_degrees"], args.target)
        report["proposal"] = command
        if args.execute and command["action"] != "none":
            # Serial arming happens only after fresh capture and valid proposal.
            # step always attempts disarm, including on reported motor errors.
            report["attempted"] = True
            step(args.port, command["action"], command["speed"], command["milliseconds"])
            report["executed"] = True
            report["after"] = capture(args.camera_exe, run/"after", environment,
                                       args.box, args.target)
            residual = (args.target-report["after"]["heading_degrees"]+180)%360-180
            report["residual_degrees"] = residual
            report["improved"] = abs(residual) < abs(command["error_degrees"])
            report["within_5_degrees"] = abs(residual) <= 5
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (run/"report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        print(f"REPORT {run/'report.json'}")


if __name__ == "__main__":
    main()
