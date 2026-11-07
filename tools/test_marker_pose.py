import unittest
from PIL import Image, ImageDraw
from marker_pose import marker_pose


class MarkerPoseTest(unittest.TestCase):
    def test_angle_ignores_orange_wire_and_smaller_reflections(self):
        image=Image.new('RGB',(120,100),'white')
        draw=ImageDraw.Draw(image)
        draw.rectangle((20,30,30,40),fill=(0,200,200))
        draw.rectangle((70,50,80,60),fill=(200,0,200))
        draw.line((5,80,100,10),fill=(220,60,10),width=5)
        draw.rectangle((100,70,101,71),fill=(0,200,200))
        result=marker_pose(image,(0,0,120,100))
        self.assertAlmostEqual(result['heading_degrees'],21.801,places=2)
        self.assertEqual(result['center_pixels'],[50,45])
        reverse=marker_pose(image,(0,0,120,100),'cyan')
        self.assertAlmostEqual(reverse['heading_degrees'],-158.199,places=2)

    def test_missing_reference_rejected(self):
        with self.assertRaises(ValueError):
            marker_pose(Image.new('RGB',(100,100),'white'),(0,0,100,100))

    def test_camera_blue_response_does_not_require_red(self):
        image=Image.new('RGB',(100,80),'white')
        draw=ImageDraw.Draw(image)
        draw.rectangle((20,20,30,30),fill=(0,140,180))
        draw.rectangle((60,20,70,30),fill=(5,5,140))
        result=marker_pose(image,(0,0,100,80))
        self.assertEqual(result['heading_degrees'],0)


if __name__ == '__main__':
    unittest.main()
