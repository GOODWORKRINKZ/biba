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
        assert set(melodies.CATALOG.keys()) == expected

    def test_each_melody_is_non_empty_list_of_tuples(self):
        for name, seq in melodies.CATALOG.items():
            assert isinstance(seq, list), f"{name} is not a list"
            assert len(seq) > 0, f"{name} is empty"
            for note in seq:
                assert len(note) == 3, f"{name} has bad tuple: {note}"
                freq, dur, pause = note
                assert isinstance(freq, int) and freq >= 0
                assert isinstance(dur, int) and dur > 0
                assert isinstance(pause, int) and pause >= 0

    def test_sos_has_correct_structure(self):
        # ··· ——— ··· = 3 dots + gap + 3 dashes + gap + 3 dots = 11 notes
        assert len(melodies.SOS) == 11

    def test_startup_begins_and_ends_with_audible(self):
        assert melodies.STARTUP[0][0] > 0
        assert melodies.STARTUP[-1][0] > 0


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
        # Should have been called multiple times for the melody
        assert pi.set_PWM_frequency.call_count == len(melodies.STARTUP)

    @patch("time.sleep")
    def test_sos_beacon_plays_all_notes(self, mock_sleep):
        buzzer, pi = self._make_buzzer()
        buzzer.sos_beacon()
        audible = [n for n in melodies.SOS if n[0] > 0]
        assert pi.set_PWM_frequency.call_count == len(audible)


# ── BLHeli melody catalog ─────────────────────────────────────────

class TestBlheliMelodyCatalog:
    def test_blheli_catalog_has_all_system_entries(self):
        expected = {
            "startup", "arm", "disarm", "low_voltage",
            "failsafe", "sos", "connected", "disconnected", "shutdown",
        }
        assert expected.issubset(set(melodies.BLHELI_CATALOG.keys()))

    def test_blheli_catalog_has_biba_signature(self):
        assert "biba_signature" in melodies.BLHELI_CATALOG

    def test_blheli_catalog_has_fun_melodies(self):
        fun = {"imperial_march", "katyusha", "korobeiniki", "nokia_tune", "pacman"}
        assert fun.issubset(set(melodies.BLHELI_CATALOG.keys()))

    def test_all_blheli_melodies_parseable(self):
        from buzzer.blheli_parser import parse_blheli
        for name, (melody_str, tempo) in melodies.BLHELI_CATALOG.items():
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
            assert name in melodies.BLHELI_CATALOG, f"{name} not in catalog"


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
