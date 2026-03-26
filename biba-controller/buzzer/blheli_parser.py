"""BLHeli32 melody format parser.

BLHeli32 format: space-separated tokens in pairs — NOTE DURATION.
  NOTE     = letter + optional '#' + octave digit, e.g. "C#5", "A4", or "P" (pause)
  DURATION = fraction string, e.g. "1/4", "1/8", "1/16"

Example: "A4 1/4 C#5 1/8 P 1/8 E5 1/4"
"""

from __future__ import annotations

import re

_NOTE_NAMES = {
    "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
    "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11,
}

_NOTE_RE = re.compile(r"^([A-G]#?)(\d)$")
_DURATION_RE = re.compile(r"^1/(\d+)$")


def note_to_freq(name: str, octave: int) -> float:
    """Convert note name + octave to frequency in Hz (equal temperament, A4=440)."""
    semitone = _NOTE_NAMES[name]
    midi = 12 * (octave + 1) + semitone
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def parse_blheli(melody_str: str, tempo_bpm: int = 120) -> list[tuple[float, float]]:
    """Parse a BLHeli32 melody string into (frequency_hz, duration_s) pairs."""
    tokens = melody_str.split()
    if not tokens:
        return []

    beat_s = 60.0 / tempo_bpm
    result: list[tuple[float, float]] = []
    i = 0

    while i < len(tokens):
        note_token = tokens[i]
        i += 1
        if i >= len(tokens):
            raise ValueError(f"Missing duration after note '{note_token}'")
        dur_token = tokens[i]
        i += 1

        dur_match = _DURATION_RE.match(dur_token)
        if not dur_match:
            raise ValueError(f"Invalid duration: '{dur_token}'")
        denominator = int(dur_match.group(1))
        duration_s = (4.0 / denominator) * beat_s

        if note_token == "P":
            result.append((0.0, duration_s))
            continue

        note_match = _NOTE_RE.match(note_token)
        if not note_match:
            raise ValueError(f"Invalid note: '{note_token}'")
        name = note_match.group(1)
        octave = int(note_match.group(2))
        freq = note_to_freq(name, octave)
        result.append((freq, duration_s))

    return result
