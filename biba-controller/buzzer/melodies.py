"""BiBa signature melodies — R2-D2 style PWM tone sequences.

Each melody is a list of (frequency_hz, duration_ms, pause_ms) tuples.
A frequency of 0 means silence (rest note).
"""

from __future__ import annotations

# Signature "Би↑-Бааа↓" startup jingle
STARTUP: list[tuple[int, int, int]] = [
    (1200, 80, 20),
    (1800, 80, 60),
    (1800, 120, 10),
    (1400, 100, 10),
    (1000, 160, 0),
]

# Quick ascending sweep — armed and ready
ARM: list[tuple[int, int, int]] = [
    (800, 40, 10),
    (1200, 40, 10),
    (1600, 40, 10),
    (2200, 60, 0),
]

# Two descending tones — disarmed
DISARM: list[tuple[int, int, int]] = [
    (1500, 80, 30),
    (800, 120, 0),
]

# Aggressive alarm pulses
LOW_VOLTAGE: list[tuple[int, int, int]] = [
    (900, 120, 50),
    (900, 120, 50),
    (900, 120, 0),
]

# Single low gudok — connection lost
FAILSAFE: list[tuple[int, int, int]] = [
    (600, 300, 0),
]

# Morse SOS at 1200 Hz: ··· ——— ···
# dot=80ms dash=240ms, inter-element=80ms, inter-letter=240ms
_DOT = (1200, 80, 80)
_DASH = (1200, 240, 80)
_LETTER_GAP = (0, 160, 0)

SOS: list[tuple[int, int, int]] = [
    _DOT, _DOT, _DOT,
    _LETTER_GAP,
    _DASH, _DASH, _DASH,
    _LETTER_GAP,
    _DOT, _DOT, _DOT,
]

# Happy chirp — connection restored
CONNECTED: list[tuple[int, int, int]] = [
    (1400, 60, 30),
    (1800, 60, 0),
]

# Sad descending — connection lost notification
DISCONNECTED: list[tuple[int, int, int]] = [
    (1200, 80, 20),
    (800, 120, 20),
    (500, 160, 0),
]

# Shutdown jingle — reverse of startup
SHUTDOWN: list[tuple[int, int, int]] = [
    (1000, 80, 10),
    (1400, 80, 10),
    (1800, 60, 40),
    (1200, 60, 20),
    (800, 120, 0),
]

CATALOG: dict[str, list[tuple[int, int, int]]] = {
    "startup": STARTUP,
    "arm": ARM,
    "disarm": DISARM,
    "low_voltage": LOW_VOLTAGE,
    "failsafe": FAILSAFE,
    "sos": SOS,
    "connected": CONNECTED,
    "disconnected": DISCONNECTED,
    "shutdown": SHUTDOWN,
}


# ── BLHeli32 format melodies ──────────────────────────────────────
# Each entry: (melody_string, tempo_bpm)

BLHELI_CATALOG: dict[str, tuple[str, int]] = {
    # ── System melodies ────────────────────────────
    "biba_signature": (
        "B5 1/16 E6 1/16 E6 1/8 D6 1/8 A5 1/8",
        168,
    ),
    "startup": (
        "C5 1/16 E5 1/16 E5 1/8 D5 1/8 C5 1/8",
        150,
    ),
    "arm": (
        "C5 1/16 E5 1/16 G5 1/16 C6 1/8",
        180,
    ),
    "disarm": (
        "G5 1/8 D5 1/4",
        120,
    ),
    "low_voltage": (
        "A5 1/8 P 1/16 A5 1/8 P 1/16 A5 1/8",
        160,
    ),
    "failsafe": (
        "D4 1/2",
        120,
    ),
    "sos": (
        "E6 1/16 E6 1/16 E6 1/16 P 1/8 E6 1/4 E6 1/4 E6 1/4 P 1/8 E6 1/16 E6 1/16 E6 1/16",
        100,
    ),
    "connected": (
        "E5 1/16 A5 1/16",
        160,
    ),
    "disconnected": (
        "E5 1/16 C5 1/8 A4 1/8",
        140,
    ),
    "shutdown": (
        "C5 1/8 D5 1/8 E5 1/16 C5 1/16 A4 1/4",
        140,
    ),
    "trim_enter": (
        "E5 1/16 G5 1/16 B5 1/8 C6 1/8",
        176,
    ),
    "trim_exit": (
        "C6 1/16 A5 1/16 F5 1/8 G5 1/8",
        172,
    ),
    # ── Fun melodies ───────────────────────────────
    "imperial_march": (
        "G4 1/4 G4 1/4 G4 1/4 D#4 1/8 A#4 1/16 G4 1/4 D#4 1/8 A#4 1/16 G4 1/2 "
        "D5 1/4 D5 1/4 D5 1/4 D#5 1/8 A#4 1/16 F#4 1/4 D#4 1/8 A#4 1/16 G4 1/2",
        104,
    ),
    "katyusha": (
        "D5 1/4 E5 1/8 F5 1/8 G5 1/4 G5 1/8 F5 1/8 E5 1/4 E5 1/4 "
        "A4 1/4 D5 1/8 C5 1/8 A4 1/4 A4 1/8 G4 1/8 F4 1/2",
        120,
    ),
    "korobeiniki": (
        "E5 1/4 B4 1/8 C5 1/8 D5 1/4 C5 1/8 B4 1/8 A4 1/4 A4 1/8 C5 1/8 "
        "E5 1/4 D5 1/8 C5 1/8 B4 1/4 B4 1/8 C5 1/8 D5 1/4 E5 1/4 "
        "C5 1/4 A4 1/4 A4 1/2",
        140,
    ),
    "axel_f": (
        "F5 1/8 G#5 1/4 F5 1/16 F5 1/16 A#5 1/8 F5 1/8 D#5 1/8 "
        "F5 1/8 C6 1/4 F5 1/16 F5 1/16 C#6 1/8 C6 1/8 G#5 1/8 "
        "F5 1/8 C6 1/8 F6 1/8 F5 1/16 D#5 1/16 D#5 1/8 C5 1/8 G5 1/8 F5 1/4",
        108,
    ),
    "nokia_tune": (
        "E6 1/8 D6 1/8 F#5 1/4 G#5 1/4 C#6 1/8 B5 1/8 D5 1/4 E5 1/4 "
        "B5 1/8 A5 1/8 C#5 1/4 E5 1/4 A5 1/2",
        180,
    ),
    "pacman": (
        "B4 1/16 B5 1/16 F#5 1/16 D#5 1/16 B5 1/16 F#5 1/8 D#5 1/8 "
        "C5 1/16 C6 1/16 G5 1/16 E5 1/16 C6 1/16 G5 1/8 E5 1/8",
        160,
    ),
    "mario": (
        "E5 1/8 E5 1/8 P 1/8 E5 1/8 P 1/8 C5 1/8 E5 1/4 G5 1/4 P 1/4 G4 1/4",
        200,
    ),
    "take_on_me": (
        "F#4 1/8 F#4 1/8 D4 1/8 B3 1/8 P 1/8 B3 1/8 P 1/8 E4 1/8 "
        "P 1/8 E4 1/8 P 1/8 E4 1/8 G#4 1/8 G#4 1/8 A4 1/8 B4 1/8",
        160,
    ),
}


SPLIT_BLHELI_CATALOG: dict[str, tuple[str, str, int]] = {
    "trim_enter": (
        "E5 1/16 G5 1/16 B5 1/8 C6 1/8",
        "B5 1/16 D6 1/16 E6 1/8 G6 1/8",
        176,
    ),
    "trim_exit": (
        "C6 1/16 A5 1/16 F5 1/8 E5 1/8",
        "A5 1/16 F5 1/16 D5 1/8 C5 1/8",
        172,
    ),
}

# Fun playlist — selectable from RC transmitter; order = zone mapping
FUN_PLAYLIST: list[str] = [
    "imperial_march",
    "katyusha",
    "korobeiniki",
    "axel_f",
    "nokia_tune",
    "pacman",
    "mario",
    "take_on_me",
]
