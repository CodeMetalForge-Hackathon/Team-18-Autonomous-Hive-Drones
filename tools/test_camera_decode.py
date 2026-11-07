import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from decode_camera import decode


class CameraDecodeTest(unittest.TestCase):
    def test_nv12_matches_integer_bt601(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'frame-1.json').write_text(json.dumps({'width':2, 'height':2, 'configured_rgb_mode':33}))
            (folder/'frame-1.raw').write_bytes(bytes([16, 235, 81, 145, 90, 240]))
            output = decode(folder, quiet=True)
            with Image.open(output) as image:
                for actual, y in zip(image.get_flattened_data(), [16,235,81,145]):
                    c, u, v = y-16, 90-128, 240-128
                    expected = tuple(max(0,min(255,n>>8)) for n in
                        (298*c+409*v+128, 298*c-100*u-208*v+128, 298*c+516*u+128))
                    self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
