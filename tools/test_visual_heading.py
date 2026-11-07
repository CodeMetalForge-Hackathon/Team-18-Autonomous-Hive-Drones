import unittest
from visual_heading import proposal


class HeadingProposalTest(unittest.TestCase):
    def test_measured_gain_reproduces_successful_correction(self):
        command = proposal(-16.56, 0)
        self.assertEqual(command["action"], "Q")
        self.assertTrue(120 <= command["milliseconds"] <= 160)

    def test_within_tolerance_does_not_move(self):
        self.assertEqual(proposal(-2.87, 0)["action"], "none")

    def test_wraparound(self):
        self.assertEqual(proposal(179, -179)["action"], "none")

    def test_unmeasured_direction_and_large_steps_rejected(self):
        for heading, target in [(20, 0), (0, 100), (0, float("nan")), (0, float("inf"))]:
            with self.assertRaises(ValueError):
                proposal(heading, target)


if __name__ == "__main__":
    unittest.main()
