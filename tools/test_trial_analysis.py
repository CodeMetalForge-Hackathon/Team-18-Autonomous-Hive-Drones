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


if __name__ == '__main__':
    unittest.main()
