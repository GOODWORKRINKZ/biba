from __future__ import annotations

from unittest.mock import MagicMock, patch

import config


class TestMotorSynth:
    def _make_synth(self, pwm_mode="HARDWARE"):
        pi = MagicMock()
        from buzzer.motor_synth import MotorSynth
        synth = MotorSynth(pi, [18, 13, 12, 19], pwm_mode=pwm_mode)
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

    def test_play_blheli_on_shared_pwm_channels_does_not_drive_dropped_comp_pins(self):
        pi = MagicMock()
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [12, 19],
            comp_pins=[18, 13],
            pwm_mode="HARDWARE",
            left_pwm_pins=[12],
            left_comp_pins=[18],
            right_pwm_pins=[19],
            right_comp_pins=[13],
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.hardware_PWM.reset_mock()

        with patch("buzzer.motor_synth.parse_blheli", return_value=[(440.0, 0.12)]):
            synth.play_blheli("ignored", tempo_bpm=120)

        non_zero_calls = [entry.args for entry in pi.hardware_PWM.call_args_list if entry.args[1] > 0]
        assert any(args[0] == 12 and args[1] == 440 for args in non_zero_calls)
        assert any(args[0] == 19 and args[1] == 440 for args in non_zero_calls)
        assert all(args[0] != 18 for args in non_zero_calls)
        assert all(args[0] != 13 for args in non_zero_calls)

    def test_play_blheli_on_shared_pwm_channels_uses_software_pwm_when_requested(self):
        pi = MagicMock()
        pi.get_PWM_real_range.return_value = 255
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [12, 19],
            comp_pins=[18, 13],
            left_pwm_pins=[12],
            left_comp_pins=[18],
            right_pwm_pins=[19],
            right_comp_pins=[13],
            pwm_mode="SOFTWARE",
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.hardware_PWM.reset_mock()
        pi.set_PWM_frequency.reset_mock()
        pi.set_PWM_dutycycle.reset_mock()

        with patch("buzzer.motor_synth.parse_blheli", return_value=[(440.0, 0.12)]):
            synth.play_blheli("ignored", tempo_bpm=120)

        pi.hardware_PWM.assert_not_called()
        pi.set_PWM_frequency.assert_any_call(12, 396)
        pi.set_PWM_frequency.assert_any_call(18, 484)
        pi.set_PWM_frequency.assert_any_call(19, 396)
        pi.set_PWM_frequency.assert_any_call(13, 484)
        non_zero_calls = [entry.args for entry in pi.set_PWM_dutycycle.call_args_list if entry.args[1] > 0]
        assert any(args[0] == 12 for args in non_zero_calls)
        assert any(args[0] == 18 for args in non_zero_calls)
        assert any(args[0] == 19 for args in non_zero_calls)
        assert any(args[0] == 13 for args in non_zero_calls)

    @patch("time.sleep")
    def test_software_pwm_mode_uses_louder_default_duty_cycle(self, mock_sleep):
        synth, pi = self._make_synth(pwm_mode="SOFTWARE")

        pi.set_PWM_dutycycle.reset_mock()

        synth.play([(1000, 100, 50)])

        non_zero_calls = [entry.args for entry in pi.set_PWM_dutycycle.call_args_list if entry.args[1] > 0]
        assert non_zero_calls
        assert (18, 63) in non_zero_calls

    def test_software_pwm_mode_constructor_preserves_existing_drive_pwm_state(self):
        pi = MagicMock()
        pi.get_PWM_real_range.return_value = 25
        pi.get_PWM_frequency.return_value = config.PWM_FREQUENCY_HZ
        pi.get_PWM_range.return_value = 25
        from buzzer.motor_synth import MotorSynth

        MotorSynth(
            pi,
            [12, 19],
            comp_pins=[18, 13],
            left_pwm_pins=[12],
            left_comp_pins=[18],
            right_pwm_pins=[19],
            right_comp_pins=[13],
            pwm_mode="SOFTWARE",
        )

        assert (12, 255) not in [call.args for call in pi.set_PWM_range.call_args_list]
        pi.set_PWM_frequency.assert_any_call(12, config.PWM_FREQUENCY_HZ)
        pi.set_PWM_frequency.assert_any_call(18, config.PWM_FREQUENCY_HZ)
        pi.set_PWM_frequency.assert_any_call(19, config.PWM_FREQUENCY_HZ)
        pi.set_PWM_frequency.assert_any_call(13, config.PWM_FREQUENCY_HZ)
        pi.set_PWM_range.assert_any_call(12, 25)
        pi.set_PWM_range.assert_any_call(18, 25)
        pi.set_PWM_range.assert_any_call(19, 25)
        pi.set_PWM_range.assert_any_call(13, 25)

    def test_software_pwm_mode_restores_drive_pwm_state_after_melody(self):
        pi = MagicMock()
        pi.get_PWM_real_range.return_value = 25
        pi.get_PWM_frequency.return_value = config.PWM_FREQUENCY_HZ
        pi.get_PWM_range.return_value = 25
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [12, 19],
            comp_pins=[18, 13],
            left_pwm_pins=[12],
            left_comp_pins=[18],
            right_pwm_pins=[19],
            right_comp_pins=[13],
            pwm_mode="SOFTWARE",
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.set_PWM_frequency.reset_mock()
        pi.set_PWM_range.reset_mock()
        pi.set_PWM_dutycycle.reset_mock()

        with patch("buzzer.motor_synth.parse_blheli", return_value=[(440.0, 0.12)]):
            synth.play_blheli("ignored", tempo_bpm=120)

        pi.set_PWM_frequency.assert_any_call(12, 396)
        pi.set_PWM_frequency.assert_any_call(12, config.PWM_FREQUENCY_HZ)
        pi.set_PWM_range.assert_any_call(12, 255)
        pi.set_PWM_range.assert_any_call(12, 25)
        pi.set_PWM_frequency.assert_any_call(18, config.PWM_FREQUENCY_HZ)
        pi.set_PWM_frequency.assert_any_call(19, config.PWM_FREQUENCY_HZ)
        pi.set_PWM_frequency.assert_any_call(13, config.PWM_FREQUENCY_HZ)
        pi.set_PWM_range.assert_any_call(18, 25)
        pi.set_PWM_range.assert_any_call(19, 25)
        pi.set_PWM_range.assert_any_call(13, 25)

    def test_play_split_blheli_on_shared_pwm_channels_does_not_drive_dropped_comp_pins(self):
        pi = MagicMock()
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [12, 19],
            comp_pins=[18, 13],
            pwm_mode="HARDWARE",
            left_pwm_pins=[12],
            left_comp_pins=[18],
            right_pwm_pins=[19],
            right_comp_pins=[13],
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.hardware_PWM.reset_mock()

        with patch(
            "buzzer.motor_synth.parse_blheli",
            side_effect=[[(523.0, 0.12)], [(392.0, 0.12)]],
        ):
            synth.play_split_blheli("left", "right", tempo_bpm=120)

        non_zero_calls = [entry.args for entry in pi.hardware_PWM.call_args_list if entry.args[1] > 0]
        assert any(args[0] == 12 and args[1] == 523 for args in non_zero_calls)
        assert any(args[0] == 19 and args[1] == 392 for args in non_zero_calls)
        assert all(args[0] != 18 for args in non_zero_calls)
        assert all(args[0] != 13 for args in non_zero_calls)

    def test_play_split_blheli_on_shared_pwm_channels_keeps_both_pins_active_in_software_mode(self):
        pi = MagicMock()
        pi.get_PWM_real_range.return_value = 255
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [12, 19],
            comp_pins=[18, 13],
            left_pwm_pins=[12],
            left_comp_pins=[18],
            right_pwm_pins=[19],
            right_comp_pins=[13],
            pwm_mode="SOFTWARE",
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.hardware_PWM.reset_mock()
        pi.set_PWM_frequency.reset_mock()
        pi.set_PWM_dutycycle.reset_mock()

        with patch(
            "buzzer.motor_synth.parse_blheli",
            side_effect=[[(523.0, 0.12)], [(392.0, 0.12)]],
        ):
            synth.play_split_blheli("left", "right", tempo_bpm=120)

        pi.hardware_PWM.assert_not_called()
        pi.set_PWM_frequency.assert_any_call(12, 471)
        pi.set_PWM_frequency.assert_any_call(18, 576)
        pi.set_PWM_frequency.assert_any_call(19, 353)
        pi.set_PWM_frequency.assert_any_call(13, 431)
        non_zero_calls = [entry.args for entry in pi.set_PWM_dutycycle.call_args_list if entry.args[1] > 0]
        assert any(args[0] == 12 for args in non_zero_calls)
        assert any(args[0] == 18 for args in non_zero_calls)
        assert any(args[0] == 19 for args in non_zero_calls)
        assert any(args[0] == 13 for args in non_zero_calls)

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
            pwm_mode="HARDWARE",
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

    def test_play_named_prefers_split_catalog_entry(self, monkeypatch):
        pi = MagicMock()
        from buzzer import melodies
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [12, 19],
            comp_pins=[18, 13],
            pwm_mode="HARDWARE",
            left_pwm_pins=[12],
            left_comp_pins=[18],
            right_pwm_pins=[19],
            right_comp_pins=[13],
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.hardware_PWM.reset_mock()
        monkeypatch.setitem(melodies.SPLIT_BLHELI_CATALOG, "poly_test", ("C5 1/8", "E5 1/8", 120))
        monkeypatch.setitem(melodies.BLHELI_CATALOG, "poly_test", ("A4 1/8", 120))

        synth.play_named("poly_test")

        non_zero_calls = [call.args for call in pi.hardware_PWM.call_args_list if call.args[1] > 0]
        assert any(args[0] == 12 and args[1] == 523 for args in non_zero_calls)
        assert any(args[0] == 19 and args[1] == 659 for args in non_zero_calls)

    def test_play_named_falls_back_to_mono_when_split_missing(self, monkeypatch):
        pi = MagicMock()
        from buzzer import melodies
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [12, 19],
            comp_pins=[18, 13],
            pwm_mode="HARDWARE",
            left_pwm_pins=[12],
            left_comp_pins=[18],
            right_pwm_pins=[19],
            right_comp_pins=[13],
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.hardware_PWM.reset_mock()
        monkeypatch.setitem(melodies.BLHELI_CATALOG, "mono_test", ("A4 1/8 C5 1/8", 120))

        synth.play_named("mono_test")

        non_zero_calls = [call.args for call in pi.hardware_PWM.call_args_list if call.args[1] > 0]
        assert any(args[0] == 12 for args in non_zero_calls)
        assert any(args[0] == 19 for args in non_zero_calls)
        assert {args[1] for args in non_zero_calls if args[0] == 12} == {args[1] for args in non_zero_calls if args[0] == 19}

    def test_play_manual_split_pwm_routes_pwm_and_comp_groups_independently_in_software_mode(self):
        pi = MagicMock()
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [18, 19],
            comp_pins=[12, 13],
            left_pwm_pins=[18],
            left_comp_pins=[12],
            right_pwm_pins=[19],
            right_comp_pins=[13],
            pwm_mode="SOFTWARE",
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.set_PWM_frequency.reset_mock()
        pi.set_PWM_dutycycle.reset_mock()

        synth.play_manual_split_pwm(1000, 400_000, 1200, 550_000, 250)

        pi.set_PWM_frequency.assert_any_call(18, 1000)
        pi.set_PWM_frequency.assert_any_call(19, 1000)
        pi.set_PWM_frequency.assert_any_call(12, 1200)
        pi.set_PWM_frequency.assert_any_call(13, 1200)
        non_zero_calls = [entry.args for entry in pi.set_PWM_dutycycle.call_args_list if entry.args[1] > 0]
        assert any(args[0] == 18 for args in non_zero_calls)
        assert any(args[0] == 19 for args in non_zero_calls)
        assert any(args[0] == 12 for args in non_zero_calls)
        assert any(args[0] == 13 for args in non_zero_calls)

    def test_system_polyphonic_melodies_exist(self):
        from buzzer import melodies

        expected = {
            "biba_signature",
            "startup",
            "arm",
            "disarm",
            "low_voltage",
            "failsafe",
            "sos",
            "connected",
            "disconnected",
            "shutdown",
            "trim_enter",
            "trim_exit",
        }

        assert expected.issubset(melodies.SPLIT_BLHELI_CATALOG)

    def test_fun_playlist_melodies_have_split_versions(self):
        from buzzer import melodies

        assert set(melodies.FUN_PLAYLIST).issubset(melodies.SPLIT_BLHELI_CATALOG)

    def test_play_named_startup_uses_distinct_left_and_right_frequencies(self):
        pi = MagicMock()
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [12, 19],
            comp_pins=[18, 13],
            pwm_mode="HARDWARE",
            left_pwm_pins=[12],
            left_comp_pins=[18],
            right_pwm_pins=[19],
            right_comp_pins=[13],
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.hardware_PWM.reset_mock()

        synth.play_named("startup")

        non_zero_calls = [call.args for call in pi.hardware_PWM.call_args_list if call.args[1] > 0]
        left_freqs = {args[1] for args in non_zero_calls if args[0] == 12}
        right_freqs = {args[1] for args in non_zero_calls if args[0] == 19}
        assert left_freqs
        assert right_freqs
        assert left_freqs != right_freqs

    def test_play_named_fun_melody_uses_distinct_left_and_right_frequencies(self):
        pi = MagicMock()
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [12, 19],
            comp_pins=[18, 13],
            pwm_mode="HARDWARE",
            left_pwm_pins=[12],
            left_comp_pins=[18],
            right_pwm_pins=[19],
            right_comp_pins=[13],
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.hardware_PWM.reset_mock()

        synth.play_named("mario")

        non_zero_calls = [call.args for call in pi.hardware_PWM.call_args_list if call.args[1] > 0]
        left_freqs = {args[1] for args in non_zero_calls if args[0] == 12}
        right_freqs = {args[1] for args in non_zero_calls if args[0] == 19}
        assert left_freqs
        assert right_freqs
        assert left_freqs != right_freqs

    def test_play_named_sos_uses_distinct_left_and_right_alarm_lines(self):
        pi = MagicMock()
        from buzzer.motor_synth import MotorSynth

        synth = MotorSynth(
            pi,
            [12, 19],
            comp_pins=[18, 13],
            pwm_mode="HARDWARE",
            left_pwm_pins=[12],
            left_comp_pins=[18],
            right_pwm_pins=[19],
            right_comp_pins=[13],
        )
        synth._wait_or_interrupted = lambda _delay: False
        pi.hardware_PWM.reset_mock()

        synth.play_named("sos")

        non_zero_calls = [call.args for call in pi.hardware_PWM.call_args_list if call.args[1] > 0]
        left_freqs = {args[1] for args in non_zero_calls if args[0] == 12}
        right_freqs = {args[1] for args in non_zero_calls if args[0] == 19}
        assert left_freqs
        assert right_freqs
        assert left_freqs != right_freqs

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
