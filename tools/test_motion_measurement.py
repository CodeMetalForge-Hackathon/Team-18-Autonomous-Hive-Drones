import unittest
import numpy as np
from PIL import Image
from measure_motion import translation


class MotionMeasurementTest(unittest.TestCase):
    def test_known_translation_with_brightness_change(self):
        noise=np.random.default_rng(7).integers(20,180,(70,90),dtype=np.uint8)
        a=Image.fromarray(noise)
        b=Image.new("L",a.size,100)
        patch=Image.fromarray(noise[20:45,25:55]+20)
        b.paste(patch,(32,16))
        result=translation(a,b,(25,20,30,25),12)
        self.assertEqual((result["dx_pixels"],result["dy_pixels"]),(7,-4))
        self.assertGreater(result["correlation"],0.99)

    def test_blank_patch_is_rejected(self):
        blank=Image.new("L",(50,50),100)
        with self.assertRaises(ValueError):
            translation(blank,blank,(10,10,20,20))


if __name__ == "__main__":
    unittest.main()
