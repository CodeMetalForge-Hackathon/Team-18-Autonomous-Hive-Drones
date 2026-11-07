"""Decode an SDK NV12 color snapshot for external supervision."""
import argparse
import json
from pathlib import Path
from PIL import Image
import numpy as np


def decode(folder, quiet=False):
    metadata = json.loads((folder / "frame-1.json").read_text())
    width, height = metadata["width"], metadata["height"]
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("NV12 requires positive even dimensions")
    data = (folder / "frame-1.raw").read_bytes()
    # This SDK sometimes leaves image_format unset. Require an explicitly
    # configured RGB YUV mode (enum 31..33) as well as the exact NV12 size.
    if metadata.get("configured_rgb_mode") not in (31, 32, 33) or len(data) != width * height * 3 // 2:
        raise ValueError("Expected an NV12 frame of the reported size")
    pixels = np.frombuffer(data, dtype=np.uint8).astype(np.int32)
    luma = pixels[:width*height].reshape(height, width)-16
    uv = pixels[width*height:].reshape(height//2, width//2, 2)-128
    uv = uv.repeat(2, axis=0).repeat(2, axis=1)
    u, v = uv[:, :, 0], uv[:, :, 1]
    rgb = np.stack(((298*luma+409*v+128)>>8,
                    (298*luma-100*u-208*v+128)>>8,
                    (298*luma+516*u+128)>>8), axis=-1)
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    output = folder / "color.png"
    Image.fromarray(rgb).save(output)
    if not quiet:
        print(output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    decode(parser.parse_args().folder)
