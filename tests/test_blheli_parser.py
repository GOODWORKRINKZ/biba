"""Tests for BLHeli32 melody format parser."""

from __future__ import annotations

import pytest

from buzzer.blheli_parser import note_to_freq, parse_blheli


class TestNoteToFreq:
    def test_a4_is_440(self):
        assert note_to_freq("A", 4) == pytest.approx(440.0, abs=0.5)

    def test_c4_is_middle_c(self):
        assert note_to_freq("C", 4) == pytest.approx(261.6, abs=0.5)

    def test_c_sharp_4(self):
        assert note_to_freq("C#", 4) == pytest.approx(277.2, abs=0.5)

    def test_b7_high(self):
        assert note_to_freq("B", 7) == pytest.approx(3951.1, abs=1.0)

    def test_octave_doubles_frequency(self):
        f4 = note_to_freq("A", 4)
        f5 = note_to_freq("A", 5)
        assert f5 == pytest.approx(f4 * 2, abs=1.0)


class TestParseBlheli:
    def test_single_note(self):
        result = parse_blheli("A4 1/4", tempo_bpm=120)
        assert len(result) == 1
        freq, dur = result[0]
        assert freq == pytest.approx(440.0, abs=0.5)
        assert dur == pytest.approx(0.5, abs=0.01)

    def test_pause(self):
        result = parse_blheli("P 1/8", tempo_bpm=120)
        assert len(result) == 1
        freq, dur = result[0]
        assert freq == 0.0
        assert dur == pytest.approx(0.25, abs=0.01)

    def test_multiple_notes(self):
        result = parse_blheli("C5 1/4 E5 1/4 G5 1/4")
        assert len(result) == 3
        assert all(f > 0 for f, _ in result)

    def test_sharp_notes(self):
        result = parse_blheli("F#5 1/4 C#6 1/8")
        assert len(result) == 2

    def test_whole_note_duration(self):
        result = parse_blheli("A4 1/1", tempo_bpm=60)
        _, dur = result[0]
        assert dur == pytest.approx(4.0, abs=0.01)

    def test_sixteenth_note(self):
        result = parse_blheli("A4 1/16", tempo_bpm=120)
        _, dur = result[0]
        assert dur == pytest.approx(0.125, abs=0.01)

    def test_empty_string_returns_empty(self):
        assert parse_blheli("") == []

    def test_invalid_note_raises(self):
        with pytest.raises(ValueError):
            parse_blheli("X4 1/4")
