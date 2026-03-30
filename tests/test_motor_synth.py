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

    def test_play_named_trim_enter_uses_split_left_and_right_groups(self):
        pi = MagicMock()
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [18, 12],
            left_pwm_pins=[18],
            right_pwm_pins=[12],
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.hardware_PWM.reset_mock()

        synth.play_named("trim_enter")

        non_zero_calls = [call.args for call in pi.hardware_PWM.call_args_list if call.args[1] > 0]
        left_calls = [args for args in non_zero_calls if args[0] == 18]
        right_calls = [args for args in non_zero_calls if args[0] == 12]

        assert left_calls
        assert right_calls
        assert left_calls[0][1] != right_calls[0][1]

    @patch("time.sleep")
    def test_play_named_unknown_does_nothing(self, mock_sleep):
        synth, pi = self._make_synth()
        pi.hardware_PWM.reset_mock()
        synth.play_named("nonexistent_melody_xyz")
        pi.hardware_PWM.assert_not_called()

    def test_set_control_active_only_turns_outputs_off_on_state_change(self):
        synth, pi = self._make_synth()
        pi.hardware_PWM.reset_mock()

        synth.set_control_active(True)
        first_call_count = pi.hardware_PWM.call_count

        synth.set_control_active(True)

        assert first_call_count > 0
        assert pi.hardware_PWM.call_count == first_call_count

    def test_control_priority_interrupts_active_playback(self):
        synth, pi = self._make_synth()
        pi.hardware_PWM.reset_mock()

        def interrupt_playback(_delay):
            synth.set_control_active(True)
            return True

        synth._wait_or_interrupted = interrupt_playback

        synth.play([(1000, 100, 0), (1200, 100, 0)])

        pi.hardware_PWM.assert_any_call(18, 1000, 50000)
        assert (18, 1200, 50000) not in [call.args for call in pi.hardware_PWM.call_args_list]

    @patch("time.sleep")
    def test_control_priority_blocks_new_melodies(self, mock_sleep):
        synth, pi = self._make_synth()
        synth.set_control_active(True)
        pi.hardware_PWM.reset_mock()

        synth.play_named("arm")

        pi.hardware_PWM.assert_not_called()
