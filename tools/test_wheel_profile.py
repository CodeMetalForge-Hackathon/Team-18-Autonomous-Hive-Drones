import unittest
from unittest.mock import MagicMock, patch
from wheel_step import envelope, wheel_step, TrialError


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

    def test_preflight_failure_disarms_closes_and_preserves_report(self):
        link = MagicMock()
        with patch('wheel_step.serial.Serial', return_value=link), \
             patch('wheel_step.read_for', side_effect=['', 'connected=0 moving=0', 'moving=0 armed=0']), \
             patch('wheel_step.time.sleep'):
            with self.assertRaises(TrialError) as failure:
                wheel_step('fake', [40,40,40,40], 200)
        self.assertIn('Rover not ready', failure.exception.report['error'])
        self.assertEqual(failure.exception.report['commands'], [])
        self.assertEqual(link.write.call_args.args, (b'DISARM\nSTATUS\n',))
        self.assertTrue(failure.exception.report['stopped_disarmed'])
        link.close.assert_called_once()

    def test_boost_is_available_only_in_bounded_pulse_mode(self):
        for duration, ramp, speeds in [(151,0,[60]*4), (100,1,[60]*4), (100,0,[61]*4)]:
            with self.assertRaises(ValueError):
                wheel_step('nonexistent', speeds, duration, ramp, pulse=True)
        with self.assertRaises(ValueError):
            wheel_step('nonexistent', [60]*4, 100)

    def test_unacknowledged_stop_cannot_arm_a_trial(self):
        link=MagicMock()
        with patch('wheel_step.serial.Serial', return_value=link), \
             patch('wheel_step.read_for', side_effect=['', 'connected=1 moving=0 stop_ack=0', 'moving=0 armed=0 stop_ack=0']):
            with self.assertRaises(TrialError) as failure:
                wheel_step('fake',[40]*4,100)
        self.assertNotIn('stopped_disarmed',failure.exception.report)
        self.assertEqual(failure.exception.report['commands'],[])


if __name__ == '__main__':
    unittest.main()
