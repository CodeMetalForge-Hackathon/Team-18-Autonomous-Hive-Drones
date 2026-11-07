import unittest

from PIL import Image, ImageDraw

from camera_pose import board_pose


class BoardPoseTest(unittest.TestCase):
    def test_rotated_board_and_heading_disambiguation(self):
        board = Image.new("RGB", (120, 120), "white")
        ImageDraw.Draw(board).rectangle((30, 53, 90, 67), fill=(210, 70, 25))
        board = board.rotate(30)
        pose = board_pose(board, (10, 10, 100, 100), -25)
        self.assertAlmostEqual(pose["heading_degrees"], -30, delta=2)
        reverse = board_pose(board, (10, 10, 100, 100), 150)
        self.assertAlmostEqual(reverse["heading_degrees"], 150, delta=2)
        self.assertAlmostEqual(pose["center_pixels"][0], 60, delta=2)

    def test_no_board_rejected(self):
        with self.assertRaises(ValueError):
            board_pose(Image.new("RGB", (100, 100), "white"), (0, 0, 100, 100), 0)

    def test_dark_board_remains_trackable(self):
        board = Image.new("RGB", (120, 120), (70, 70, 70))
        ImageDraw.Draw(board).rectangle((30, 53, 90, 67), fill=(65, 23, 8))
        pose = board_pose(board, (10, 10, 100, 100), 0)
        self.assertAlmostEqual(pose['heading_degrees'], 0, delta=1)

    def test_round_patch_has_no_heading(self):
        image = Image.new("RGB", (100, 100), "white")
        ImageDraw.Draw(image).ellipse((25, 25, 75, 75), fill=(210, 70, 25))
        with self.assertRaises(ValueError):
            board_pose(image, (0, 0, 100, 100), 0)


if __name__ == "__main__":
    unittest.main()
