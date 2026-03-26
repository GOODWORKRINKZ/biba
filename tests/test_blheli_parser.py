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
