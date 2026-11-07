"""Estimate the orange controller board's image-plane pose for supervision.

Requires an operator-selected crop and approximate heading. This color heuristic
is specific to this test setup, not a general robot detector or metric odometry.
It never sends motor commands. Heading is resolved modulo 180 degrees using the
provided prior; inspect the image whenever motion could exceed 90 degrees.
"""
import argparse
import json
import math

import numpy as np
from PIL import Image


def board_pose(image, box, prior_degrees):
    x, y, w, h = box
    if min(x, y) < 0 or min(w, h) < 8 or x+w > image.width or y+h > image.height:
        raise ValueError("Invalid tracking crop")
    rgb = np.asarray(image.convert("RGB"), dtype=float)[y:y+h, x:x+w]
    r, g, b = rgb.transpose(2, 0, 1)
    # Ratios retain the orange outline when camera auto-exposure darkens it.
    mask = (r > 45) & (g > 8) & (g < 155) & (r > 1.45*g) & (r > 1.8*b)
    yy, xx = np.nonzero(mask)
    if len(xx) < 35:
        raise ValueError("Too few orange board pixels")
    points = np.column_stack((xx+x, yy+y))
    center = points.mean(axis=0)
    covariance = np.cov(points.T)
    values, vectors = np.linalg.eigh(covariance)
    ratio = values[-1] / max(values[0], 1e-9)
    if ratio < 1.6:
        raise ValueError("Board orientation is ambiguous")
    axis = vectors[:, -1]
    angle = math.degrees(math.atan2(axis[1], axis[0]))
    angle = prior_degrees + ((angle-prior_degrees+90) % 180 - 90)
    return {"center_pixels": [round(float(v), 2) for v in center],
            "heading_degrees": round(angle, 2), "orange_pixels": len(xx),
            "axis_ratio": round(float(ratio), 3),
            "units": "image pixels; clockwise degrees with image-right = 0",
            "warning": "Board axis only; heading sign depends on supplied prior"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--box", nargs=4, type=int, required=True)
    parser.add_argument("--heading", type=float, required=True)
    args = parser.parse_args()
    print(json.dumps(board_pose(Image.open(args.image), args.box, args.heading), indent=2))
