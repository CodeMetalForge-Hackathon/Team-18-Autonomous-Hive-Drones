import json
from pathlib import Path
import tempfile
import unittest
from analyze_trial import analyze


class TrialAnalysisTest(unittest.TestCase):
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
