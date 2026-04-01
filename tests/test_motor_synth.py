from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestMotorSynth:
    def _make_pi(self) -> MagicMock:
        pi = MagicMock()
        pi.get_PWM_frequency.return_value = 200
        pi.get_PWM_range.return_value = 255
        return pi

    def _make_synth(self):
        pi = self._make_pi()
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [18, 19],
            comp_pins=[12, 13],
            pwm_mode="SOFTWARE",
            left_pwm_pins=[18],
            left_comp_pins=[12],
            right_pwm_pins=[19],
            right_comp_pins=[13],
        )
        return synth, pi

    def test_initializes_all_motor_pwm_pins_and_groups(self):
        synth, pi = self._make_synth()

        assert synth._pwm_mode == "SOFTWARE"
        assert synth.duty_cycle == 250_000
        assert synth.left_pwm_pins == [18]
        assert synth.left_comp_pins == [12]
        assert synth.right_pwm_pins == [19]
        assert synth.right_comp_pins == [13]
        assert synth.pwm_pins == [18, 19]
        assert synth.comp_pins == [12, 13]
        assert synth._raw_left_comp_pins == [12]
        assert synth._raw_right_comp_pins == [13]
        assert pi.set_mode.call_count == 4

    def test_frequency_pair_uses_twenty_percent_total_delta(self):
        from buzzer.motor_synth import MotorSynth

        assert MotorSynth._frequency_pair_for_note(1000) == (900, 1100)
        assert MotorSynth._frequency_pair_for_note(440) == (396, 484)
        assert MotorSynth._frequency_pair_for_note(0) == (0, 0)

    def test_scale_software_duty_maps_twenty_five_percent_to_quarter_range(self):
        from buzzer.motor_synth import MotorSynth

        assert MotorSynth._scale_software_duty(250_000) == 64

    def test_apply_motor_pwm_writes_direct_lpwm_and_rpwm_values(self):
        synth, pi = self._make_synth()

        pi.set_PWM_range.reset_mock()
        pi.set_PWM_frequency.reset_mock()
        pi.set_PWM_dutycycle.reset_mock()

        synth._apply_motor_pwm(18, 12, 1000, 400_000, 1200, 400_000)

        assert pi.set_PWM_range.call_args_list == [((18, 255),), ((12, 255),)]
        assert pi.set_PWM_frequency.call_args_list == [((18, 1000),), ((12, 1200),)]
        assert pi.set_PWM_dutycycle.call_args_list == [((18, 102),), ((12, 102),)]

    def test_play_manual_split_pwm_uses_confirmed_direct_pattern(self):
        synth, pi = self._make_synth()
        synth._wait_or_interrupted = lambda _delay: False

        pi.set_PWM_range.reset_mock()
        pi.set_PWM_frequency.reset_mock()
        pi.set_PWM_dutycycle.reset_mock()

        synth.play_manual_split_pwm(1000, 400_000, 1200, 550_000, 250)

        pi.set_PWM_frequency.assert_any_call(18, 1000)
        pi.set_PWM_frequency.assert_any_call(19, 1000)
        pi.set_PWM_frequency.assert_any_call(12, 1200)
        pi.set_PWM_frequency.assert_any_call(13, 1200)
        non_zero_calls = [call.args for call in pi.set_PWM_dutycycle.call_args_list if call.args[1] > 0]
        assert (18, 102) in non_zero_calls
        assert (19, 102) in non_zero_calls
        assert (12, 140) in non_zero_calls
        assert (13, 140) in non_zero_calls

    def test_play_applies_same_synth_note_to_both_motors(self):
        synth, pi = self._make_synth()
        synth._wait_or_interrupted = lambda _delay: False

        pi.set_PWM_frequency.reset_mock()

        synth.play([(1000, 100, 0)])

        expected = {
            (18, 900),
            (12, 1100),
            (19, 900),
            (13, 1100),
        }
        observed = {call.args for call in pi.set_PWM_frequency.call_args_list if call.args[1] in {900, 1100}}
        assert expected.issubset(observed)

    def test_play_blheli_uses_parsed_sequence_on_both_motors(self):
        synth, pi = self._make_synth()
        synth._wait_or_interrupted = lambda _delay: False

        pi.set_PWM_frequency.reset_mock()

        with patch("buzzer.motor_synth.parse_blheli", return_value=[(440.0, 0.12)]):
            synth.play_blheli("ignored", tempo_bpm=120)

        expected = {
            (18, 396),
            (12, 484),
            (19, 396),
            (13, 484),
        }
        observed = {call.args for call in pi.set_PWM_frequency.call_args_list if call.args[1] in {396, 484}}
        assert expected.issubset(observed)

    def test_play_split_blheli_uses_independent_left_and_right_notes(self):
        synth, pi = self._make_synth()
        synth._wait_or_interrupted = lambda _delay: False

        pi.set_PWM_frequency.reset_mock()

        with patch(
            "buzzer.motor_synth.parse_blheli",
            side_effect=[[(523.0, 0.12)], [(392.0, 0.12)]],
        ):
            synth.play_split_blheli("left", "right", tempo_bpm=120)

        expected = {
            (18, 471),
            (12, 576),
            (19, 353),
            (13, 431),
        }
        observed = {call.args for call in pi.set_PWM_frequency.call_args_list if call.args[1] in {471, 576, 353, 431}}
        assert expected.issubset(observed)

    def test_play_named_uses_current_catalog_split_entry(self, monkeypatch):
        synth, pi = self._make_synth()
        synth._wait_or_interrupted = lambda _delay: False

        from buzzer import melodies

        pi.set_PWM_frequency.reset_mock()
        monkeypatch.setitem(melodies.CATALOG, "poly_test", ("C5 1/8", "E5 1/8", 120))

        synth.play_named("poly_test")

        expected = {
            (18, 471),
            (12, 576),
            (19, 593),
            (13, 725),
        }
        observed = {call.args for call in pi.set_PWM_frequency.call_args_list if call.args[1] in {471, 576, 593, 725}}
        assert expected.issubset(observed)

    def test_play_named_ignores_names_missing_from_unified_catalog(self, monkeypatch):
        synth, pi = self._make_synth()
        synth._wait_or_interrupted = lambda _delay: False

        from buzzer import melodies

        pi.set_PWM_frequency.reset_mock()
        monkeypatch.delitem(melodies.CATALOG, "mono_test", raising=False)

        synth.play_named("mono_test")

        pi.set_PWM_frequency.assert_not_called()

    def test_play_named_unknown_does_nothing(self):
        synth, pi = self._make_synth()

        pi.set_PWM_frequency.reset_mock()

        synth.play_named("nonexistent_melody_xyz")

        pi.set_PWM_frequency.assert_not_called()

    def test_control_priority_blocks_and_interrupts_playback(self):
        synth, pi = self._make_synth()

        synth.set_control_active(True)
        pi.set_PWM_frequency.reset_mock()
        synth.play([(1000, 100, 0)])
        pi.set_PWM_frequency.assert_not_called()

        synth.set_control_active(False)

        def interrupt_playback(_delay):
            synth.set_control_active(True)
            return True

        synth._wait_or_interrupted = interrupt_playback
        pi.set_PWM_frequency.reset_mock()

        synth.play([(1000, 100, 0), (1200, 100, 0)])

        observed = [call.args for call in pi.set_PWM_frequency.call_args_list]
        assert (18, 900) in observed
        assert (18, 1080) not in observed

    def test_wav_and_spectral_are_temporary_noops(self):
        synth, pi = self._make_synth()

        pi.set_PWM_frequency.reset_mock()
        synth.play_wav("ignored.wav")
        synth.play_spectral("ignored.wav")

        pi.set_PWM_frequency.assert_not_called()
