import io
import unittest
from camera_recorder import HEADER, read_frame


class CameraStreamTest(unittest.TestCase):
    def test_frame_protocol(self):
        payload = bytes(640*400*3//2)
        header = HEADER.pack(b'FRM1', 640, 400, len(payload), 123, 456)
        metadata, actual = read_frame(io.BytesIO(header+payload))
        self.assertEqual(actual, payload)
        self.assertEqual(metadata['timestamp'], 123)
        self.assertEqual(metadata['host_time_ms'], 456)

    def test_bad_or_truncated_frame_fails(self):
        with self.assertRaises(ValueError):
            read_frame(io.BytesIO(HEADER.pack(b'FAIL',640,400,384000,0,0)))
        with self.assertRaises(EOFError):
            read_frame(io.BytesIO(HEADER.pack(b'FRM1',640,400,384000,0,0)))


if __name__ == '__main__':
    unittest.main()
