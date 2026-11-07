import json
from pathlib import Path
import tempfile
import unittest
from analyze_trial import analyze, pose_statistics


class TrialAnalysisTest(unittest.TestCase):
    def test_stationary_heading_noise_handles_angle_wrap(self):
        rows=[{'center_pixels':[10,20], 'heading_degrees':angle} for angle in [179.9,-179.9,180.0]]
        pose,noise=pose_statistics(rows)
        self.assertAlmostEqual(pose[2],180)
        self.assertLess(noise[2],0.1)

    def test_jitter_is_visible_in_measurement_statistics(self):
        rows=[{'center_pixels':[10,20], 'heading_degrees':angle} for angle in [0,8,-8]]
        _,noise=pose_statistics(rows)
        self.assertGreater(noise[2],2)

    def test_motor_fault_is_not_training_data(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'trial.json').write_text(json.dumps({'error':'MOTOR_ERROR'}))
            with self.assertRaisesRegex(ValueError, 'cannot be used'):
                analyze(folder, (0,0,100,100), 0)

    def test_stop_write_errors_are_not_training_data(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'trial.json').write_text(json.dumps({'stopped_disarmed':True,
                'status_before':'MOTOR_DIAG error_count=1',
                'final_status':'MOTOR_DIAG error_count=2'}))
            with self.assertRaisesRegex(ValueError, 'error count increased'):
                analyze(folder, (0,0,100,100), 0)


if __name__ == '__main__':
    unittest.main()
