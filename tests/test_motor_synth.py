from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestMotorSynth:
    def _make_synth(self):
        pi = MagicMock()
        from buzzer.motor_synth import MotorSynth
        synth = MotorSynth(pi, [18, 13, 12, 19])
        return synth, pi

    def test_initializes_all_motor_pwm_pins(self):
        synth, pi = self._make_synth()
        del synth
        assert pi.set_mode.call_count == 4

    @patch("time.sleep")
    def test_play_uses_hardware_pwm_for_audible_note(self, mock_sleep):
        synth, pi = self._make_synth()
        synth.play([(1000, 100, 50)])
        assert pi.hardware_PWM.call_count >= 8
        pi.hardware_PWM.assert_any_call(18, 1000, 50000)

    @patch("time.sleep")
    def test_play_silence_note_turns_outputs_off(self, mock_sleep):
        synth, pi = self._make_synth()
        synth.play([(0, 100, 0)])
        pi.hardware_PWM.assert_any_call(18, 0, 0)
        pi.hardware_PWM.assert_any_call(19, 0, 0)

    @patch("time.sleep")
    def test_play_blheli_uses_parsed_sequence(self, mock_sleep):
        synth, pi = self._make_synth()
        synth.play_blheli("A4 1/4 P 1/8 C5 1/4", tempo_bpm=120)
        pi.hardware_PWM.assert_any_call(18, 440, 50000)

    @patch("time.sleep")
    def test_play_named_plays_arm(self, mock_sleep):
        synth, pi = self._make_synth()
        synth.play_named("arm")
        assert pi.hardware_PWM.called

    @patch("time.sleep")
    def test_play_named_unknown_does_nothing(self, mock_sleep):
        synth, pi = self._make_synth()
        pi.hardware_PWM.reset_mock()
        synth.play_named("nonexistent_melody_xyz")
        pi.hardware_PWM.assert_not_called()
