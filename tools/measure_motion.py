"""Measure camera-plane translation of a selected rover patch, not metric odometry.

Use a fixed external camera and a tight rectangle around rigid rover features.
Large rotations, occlusion, lighting changes and background clutter can invalidate
the estimate. Inspect before/after images before accepting it as calibration.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image


def translation(before, after, box, radius=35):
    a = np.asarray(before.convert("L"), dtype=np.float64)
    b = np.asarray(after.convert("L"), dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError("Image dimensions differ")
    x, y, w, h = box
    if min(x, y) < 0 or min(w, h) < 8 or x+w > a.shape[1] or y+h > a.shape[0]:
        raise ValueError("Invalid tracking rectangle")
    template = a[y:y+h, x:x+w]
    template = template - template.mean()
    norm = np.linalg.norm(template)
    if norm < 1:
        raise ValueError("Tracking rectangle has no texture")
    best = (-2.0, 0, 0)
    for dy in range(-radius, radius+1):
        for dx in range(-radius, radius+1):
            if min(x+dx, y+dy)<0 or x+dx+w>b.shape[1] or y+dy+h>b.shape[0]:
                continue
            patch = b[y+dy:y+dy+h, x+dx:x+dx+w]
            patch = patch - patch.mean()
            denominator = norm * np.linalg.norm(patch)
            score = float(np.sum(template*patch)/denominator) if denominator else -2
            if score > best[0]:
                best = (score, dx, dy)
    score, dx, dy = best
    return {"dx_pixels": dx, "dy_pixels": dy, "correlation": round(score, 5),
            "search_boundary": abs(dx)==radius or abs(dy)==radius,
            "units": "image pixels; uncalibrated", "box": list(box)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--box", type=int, nargs=4, required=True, metavar=("X", "Y", "W", "H"))
    parser.add_argument("--radius", type=int, default=35)
    args = parser.parse_args()
    print(json.dumps(translation(Image.open(args.before), Image.open(args.after), args.box, args.radius), indent=2))
