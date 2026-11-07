import unittest
from wheel_step import envelope, wheel_step


class WheelProfileTest(unittest.TestCase):
    def test_smooth_envelope(self):
        self.assertEqual(envelope(0, 400, 100), 0)
        self.assertEqual(envelope(50, 400, 100), 0.5)
        self.assertEqual(envelope(200, 400, 100), 1)
        self.assertEqual(envelope(350, 400, 100), 0.5)
        self.assertEqual(envelope(400, 400, 100), 0)
        self.assertEqual(envelope(500, 400, 100), 0)

    def test_invalid_commands_rejected_before_port_open(self):
        for speeds, duration, ramp in [([41, 0, 0, 0], 200, 0),
                                       ([0, 0, 0], 200, 0),
                                       ([0, 0, 0, 0], 1001, 0),
                                       ([0, 0, 0, 0], 200, 101)]:
            with self.assertRaises(ValueError):
                wheel_step('nonexistent', speeds, duration, ramp)


if __name__ == '__main__':
    unittest.main()
