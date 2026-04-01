"""Tests for buzzer melodies, Buzzer class, and BeaconManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from buzzer import melodies
from buzzer.beacon import BeaconManager


# ── melodies catalog ───────────────────────────────────────────────

class TestMelodies:
    def test_catalog_has_all_named_entries(self):
        expected = {
            "startup", "arm", "disarm", "low_voltage",
            "failsafe", "sos", "connected", "disconnected", "shutdown",
        }
        assert expected.issubset(set(melodies.CATALOG.keys()))

    def test_each_melody_is_split_blheli_tuple(self):
        for name, entry in melodies.CATALOG.items():
            assert isinstance(entry, tuple), f"{name} is not a tuple"
            assert len(entry) == 3, f"{name} must be (left, right, tempo)"
            left, right, tempo = entry
            assert isinstance(left, str) and left
            assert isinstance(right, str) and right
            assert isinstance(tempo, int) and tempo > 0

    def test_sos_has_multiple_audible_notes(self):
        from buzzer.blheli_parser import parse_blheli

        left, right, tempo = melodies.CATALOG["sos"]
        audible = [freq for freq, _duration in parse_blheli(left, tempo_bpm=tempo) if freq > 0]
        audible += [freq for freq, _duration in parse_blheli(right, tempo_bpm=tempo) if freq > 0]
        assert len(audible) >= 4

    def test_startup_begins_and_ends_with_audible(self):
        from buzzer.blheli_parser import parse_blheli

        left, _right, tempo = melodies.CATALOG["startup"]
        notes = [freq for freq, _duration in parse_blheli(left, tempo_bpm=tempo)]
        assert notes[0] > 0
        assert notes[-1] > 0


# ── BeaconManager ──────────────────────────────────────────────────

class TestBeaconManager:
    def test_no_sos_when_connected(self):
        bm = BeaconManager(delay_s=5.0, enabled=True)
        bm.on_connected()
        assert bm.should_sos(100.0) is False

    def test_no_sos_before_delay(self):
        bm = BeaconManager(delay_s=300.0, enabled=True)
        bm.on_failsafe(1000.0)
        assert bm.should_sos(1100.0) is False  # only 100s, need 300

    def test_sos_after_delay(self):
        bm = BeaconManager(delay_s=10.0, enabled=True)
        bm.on_failsafe(100.0)
        assert bm.should_sos(111.0) is True  # 11s > 10s delay

    def test_sos_not_repeated_within_interval(self):
        bm = BeaconManager(delay_s=1.0, enabled=True)
        bm.on_failsafe(0.0)
        assert bm.should_sos(2.0) is True
        assert bm.should_sos(3.0) is False  # too soon (interval = 8s)
        assert bm.should_sos(11.0) is True  # 8+ seconds later

    def test_sos_disabled(self):
        bm = BeaconManager(delay_s=1.0, enabled=False)
        bm.on_failsafe(0.0)
        assert bm.should_sos(100.0) is False

    def test_manual_toggle_triggers_sos(self):
        bm = BeaconManager(delay_s=9999.0, enabled=True)
        bm.set_manual(True)
        assert bm.should_sos(1.0) is True

    def test_connected_resets_failsafe(self):
        bm = BeaconManager(delay_s=5.0, enabled=True)
        bm.on_failsafe(0.0)
        bm.on_connected()
        assert bm.should_sos(100.0) is False

    def test_manual_off_stops_sos(self):
        bm = BeaconManager(delay_s=9999.0, enabled=True)
        bm.set_manual(True)
        bm.should_sos(1.0)  # consume
        bm.set_manual(False)
        assert bm.should_sos(100.0) is False


# ── Buzzer with melodies ───────────────────────────────────────────

class TestBuzzerMelodies:
    def _make_buzzer(self):
        pi = MagicMock()
        from buzzer.buzzer import Buzzer
        buzzer = Buzzer(pi, 17)
        return buzzer, pi

    @patch("time.sleep")
    def test_play_calls_pwm(self, mock_sleep):
        buzzer, pi = self._make_buzzer()
        buzzer.play([(1000, 100, 50)])
        pi.set_PWM_frequency.assert_called_with(17, 1000)
        pi.set_PWM_dutycycle.assert_any_call(17, 128)

    @patch("time.sleep")
    def test_play_silence_note(self, mock_sleep):
        buzzer, pi = self._make_buzzer()
        buzzer.play([(0, 100, 0)])
        # silence note should not set frequency, only dutycycle 0
        pi.set_PWM_frequency.assert_not_called()

    @patch("time.sleep")
    def test_startup_tone_plays_startup_melody(self, mock_sleep):
        buzzer, pi = self._make_buzzer()
        buzzer.startup_tone()

        from buzzer.blheli_parser import parse_blheli

        left, _right, tempo = melodies.CATALOG["startup"]
        expected_count = len([freq for freq, _dur in parse_blheli(left, tempo_bpm=tempo) if freq > 0])
        assert pi.set_PWM_frequency.call_count == expected_count

    @patch("time.sleep")
    def test_sos_beacon_plays_all_notes(self, mock_sleep):
        buzzer, pi = self._make_buzzer()
        buzzer.sos_beacon()

        from buzzer.blheli_parser import parse_blheli

        left, _right, tempo = melodies.CATALOG["sos"]
        audible = [freq for freq, _dur in parse_blheli(left, tempo_bpm=tempo) if freq > 0]
        assert pi.set_PWM_frequency.call_count == len(audible)


# ── BLHeli melody catalog ─────────────────────────────────────────

class TestBlheliMelodyCatalog:
    def test_disarm_is_short_descending_reply_to_arm(self):
        from buzzer.blheli_parser import parse_blheli

        arm_left, arm_right, arm_tempo = melodies.CATALOG["arm"]
        disarm_left, disarm_right, disarm_tempo = melodies.CATALOG["disarm"]

        assert disarm_tempo == arm_tempo == 176
        assert disarm_left == "G4 1/16 D#4 1/8"
        assert disarm_right == "A4 1/16 F4 1/8"

        arm_left_notes = [freq for freq, _duration in parse_blheli(arm_left, tempo_bpm=arm_tempo) if freq > 0]
        arm_right_notes = [freq for freq, _duration in parse_blheli(arm_right, tempo_bpm=arm_tempo) if freq > 0]
        disarm_left_notes = [freq for freq, _duration in parse_blheli(disarm_left, tempo_bpm=disarm_tempo) if freq > 0]
        disarm_right_notes = [freq for freq, _duration in parse_blheli(disarm_right, tempo_bpm=disarm_tempo) if freq > 0]

        assert arm_left_notes[0] < arm_left_notes[1]
        assert arm_right_notes[0] < arm_right_notes[1]
        assert disarm_left_notes[0] > disarm_left_notes[1]
        assert disarm_right_notes[0] > disarm_right_notes[1]

    def test_system_blheli_entries_stay_in_software_pwm_friendly_band(self):
        from buzzer.blheli_parser import parse_blheli

        system_entries = {
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

        for name in system_entries:
            left, right, tempo = melodies.CATALOG[name]
            for melody_str in (left, right):
                for freq, _duration in parse_blheli(melody_str, tempo_bpm=tempo):
                    if freq <= 0:
                        continue
                    assert 250 <= freq <= 500, f"{name} uses synth-unfriendly frequency {freq}"

    def test_catalog_has_trim_transition_entries(self):
        for name in ("trim_enter", "trim_exit"):
            left, right, tempo = melodies.CATALOG[name]
            assert left
            assert right
            assert tempo > 0

    def test_catalog_has_biba_signature(self):
        assert "biba_signature" in melodies.CATALOG

    def test_blheli_catalog_has_fun_melodies(self):
        fun = {"imperial_march", "katyusha", "korobeiniki", "nokia_tune", "pacman"}
        assert fun.issubset(set(melodies.CATALOG.keys()))

    def test_all_blheli_melodies_parseable(self):
        from buzzer.blheli_parser import parse_blheli
        for name, (left, right, tempo) in melodies.CATALOG.items():
            for melody_str in (left, right):
                notes = parse_blheli(melody_str, tempo_bpm=tempo)
                assert len(notes) > 0, f"{name} parsed to empty"
                for freq, dur in notes:
                    assert freq >= 0, f"{name}: negative freq {freq}"
                    assert dur > 0, f"{name}: non-positive duration {dur}"

    def test_fun_playlist_only_has_fun_melodies(self):
        system = {"startup", "arm", "disarm", "low_voltage", "failsafe",
                  "sos", "connected", "disconnected", "shutdown"}
        for name in melodies.FUN_PLAYLIST:
            assert name not in system, f"{name} is a system melody"
            assert name in melodies.CATALOG, f"{name} not in catalog"


# ── Buzzer BLHeli playback ─────────────────────────────────────────

class TestBuzzerBlheli:
    def _make_buzzer(self):
        pi = MagicMock()
        from buzzer.buzzer import Buzzer
        return Buzzer(pi, 17), pi

    @patch("time.sleep")
    def test_play_blheli_calls_tone_sequence(self, mock_sleep):
        buzzer, pi = self._make_buzzer()
        buzzer.play_blheli("A4 1/4 P 1/8 C5 1/4", tempo_bpm=120)
        freq_calls = [c.args[1] for c in pi.set_PWM_frequency.call_args_list]
        assert len(freq_calls) == 2  # two audible notes (pause skipped)
        assert freq_calls[0] == pytest.approx(440, abs=1)

    @patch("time.sleep")
    def test_play_named_plays_arm(self, mock_sleep):
        buzzer, pi = self._make_buzzer()
        buzzer.play_named("arm")
        assert pi.set_PWM_frequency.called

    @patch("time.sleep")
    def test_play_named_unknown_does_nothing(self, mock_sleep):
        buzzer, pi = self._make_buzzer()
        buzzer.play_named("nonexistent_melody_xyz")
        pi.set_PWM_frequency.assert_not_called()
