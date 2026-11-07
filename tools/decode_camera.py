"""Decode an SDK NV12 color snapshot for external supervision."""
import argparse
import json
from pathlib import Path
from PIL import Image


def decode(folder):
    metadata = json.loads((folder / "frame-1.json").read_text())
    width, height = metadata["width"], metadata["height"]
    data = (folder / "frame-1.raw").read_bytes()
    # This SDK sometimes leaves image_format unset. Require an explicitly
    # configured RGB YUV mode (enum 31..33) as well as the exact NV12 size.
    if metadata.get("configured_rgb_mode") not in (31, 32, 33) or len(data) != width * height * 3 // 2:
        raise ValueError("Expected an NV12 frame of the reported size")
    rgb = bytearray(width * height * 3)
    clamp = lambda x: max(0, min(255, x))
    for y in range(height):
        for x in range(width):
            luma = data[y * width + x] - 16
            uv = width * height + (y // 2) * width + (x // 2) * 2
            u, v = data[uv] - 128, data[uv + 1] - 128
            offset = (y * width + x) * 3
            rgb[offset:offset + 3] = bytes((clamp((298*luma+409*v+128)>>8),
                                           clamp((298*luma-100*u-208*v+128)>>8),
                                           clamp((298*luma+516*u+128)>>8)))
    output = folder / "color.png"
    Image.frombytes("RGB", (width, height), bytes(rgb)).save(output)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    decode(parser.parse_args().folder)
