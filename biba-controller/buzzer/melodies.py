"""BiBa signature melodies — R2-D2 style PWM tone sequences.

Each melody is a list of (frequency_hz, duration_ms, pause_ms) tuples.
A frequency of 0 means silence (rest note).
"""

from __future__ import annotations

# Friendly robot-pet phrases for the piezo fallback.
STARTUP: list[tuple[int, int, int]] = [
    (900, 70, 20),
    (1320, 80, 30),
    (1080, 120, 0),
]

ARM: list[tuple[int, int, int]] = [
    (960, 60, 15),
    (1380, 90, 0),
]

DISARM: list[tuple[int, int, int]] = [
    (1320, 60, 15),
    (900, 110, 0),
]

LOW_VOLTAGE: list[tuple[int, int, int]] = [
    (860, 110, 40),
    (1040, 110, 40),
    (860, 150, 0),
]

FAILSAFE: list[tuple[int, int, int]] = [
    (720, 120, 20),
    (860, 120, 20),
    (720, 180, 0),
]

SOS: list[tuple[int, int, int]] = [
    (1320, 70, 20),
    (980, 70, 20),
    (1320, 70, 50),
    (760, 160, 40),
    (980, 160, 0),
]

CONNECTED: list[tuple[int, int, int]] = [
    (1040, 60, 20),
    (1320, 80, 0),
]

DISCONNECTED: list[tuple[int, int, int]] = [
    (1180, 60, 20),
    (920, 70, 20),
    (760, 100, 0),
]

SHUTDOWN: list[tuple[int, int, int]] = [
    (1180, 60, 20),
    (980, 70, 20),
    (760, 120, 0),
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
        "F4 1/16 A4 1/16 G4 1/8 D#4 1/8 A4 1/8",
        156,
    ),
    "startup": (
        "F4 1/16 A4 1/16 G4 1/8 F4 1/8 D#4 1/8",
        152,
    ),
    "arm": (
        "F4 1/16 A4 1/8",
        176,
    ),
    "disarm": (
        "G4 1/16 D#4 1/8",
        176,
    ),
    "low_voltage": (
        "D#4 1/8 P 1/16 F4 1/8 P 1/16 D#4 1/8",
        150,
    ),
    "failsafe": (
        "D4 1/8 F4 1/8 D4 1/4",
        124,
    ),
    "sos": (
        "A4 1/16 F4 1/16 A4 1/16 P 1/16 D#4 1/8 D#4 1/8 P 1/16 A4 1/16 F4 1/16",
        132,
    ),
    "connected": (
        "G4 1/16 A4 1/16",
        168,
    ),
    "disconnected": (
        "G4 1/16 F4 1/16 D#4 1/8",
        144,
    ),
    "shutdown": (
        "G4 1/16 F4 1/16 D#4 1/8 D4 1/8",
        138,
    ),
    "trim_enter": (
        "F4 1/16 G4 1/16 A4 1/8",
        172,
    ),
    "trim_exit": (
        "A4 1/16 G4 1/16 F4 1/8",
        168,
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
    "biba_signature": (
        "G4 1/16 A#4 1/16 G4 1/8 F4 1/8 D#4 1/8",
        "D#4 1/16 F4 1/16 D#4 1/8 G4 1/8 A#4 1/8",
        156,
    ),
    "startup": (
        "F4 1/16 A4 1/16 G4 1/8 F4 1/8",
        "D#4 1/16 F4 1/16 D#4 1/8 G4 1/8",
        152,
    ),
    "arm": (
        "F4 1/16 A4 1/8",
        "D#4 1/16 G4 1/8",
        176,
    ),
    "disarm": (
        "G4 1/16 D#4 1/8",
        "A4 1/16 F4 1/8",
        176,
    ),
    "low_voltage": (
        "D#4 1/8 P 1/16 F4 1/8 P 1/16 D#4 1/8",
        "F4 1/8 P 1/16 D#4 1/8 P 1/16 F4 1/8",
        150,
    ),
    "failsafe": (
        "D4 1/8 F4 1/8 D4 1/4",
        "F4 1/8 D#4 1/8 D4 1/4",
        124,
    ),
    "sos": (
        "A4 1/16 F4 1/16 A4 1/16 P 1/16 D#4 1/8 P 1/16 A4 1/16",
        "F4 1/16 D#4 1/16 F4 1/16 P 1/16 G4 1/8 P 1/16 F4 1/16",
        132,
    ),
    "connected": (
        "G4 1/16 A4 1/16",
        "D#4 1/16 F4 1/16",
        168,
    ),
    "disconnected": (
        "G4 1/16 F4 1/16 D#4 1/8",
        "F4 1/16 D#4 1/16 D4 1/8",
        144,
    ),
    "shutdown": (
        "G4 1/16 F4 1/16 D#4 1/8 D4 1/8",
        "F4 1/16 D#4 1/16 D4 1/8 D#4 1/8",
        138,
    ),
    "trim_enter": (
        "F4 1/16 G4 1/16 A4 1/8",
        "D#4 1/16 F4 1/16 G4 1/8",
        172,
    ),
    "trim_exit": (
        "A4 1/16 G4 1/16 F4 1/8",
        "G4 1/16 F4 1/16 D#4 1/8",
        168,
    ),
    "imperial_march": (
        "G4 1/4 G4 1/4 G4 1/4 D#4 1/8 A#4 1/16 G4 1/4 D#4 1/8 A#4 1/16 G4 1/2 D5 1/4 D5 1/4 D5 1/4 D#5 1/8 A#4 1/16 F#4 1/4 D#4 1/8 A#4 1/16 G4 1/2",
        "D4 1/4 D4 1/4 D4 1/4 A#3 1/8 F4 1/16 D4 1/4 A#3 1/8 F4 1/16 D4 1/2 G4 1/4 G4 1/4 G4 1/4 A#4 1/8 F4 1/16 C4 1/4 A#3 1/8 F4 1/16 D4 1/2",
        104,
    ),
    "katyusha": (
        "D5 1/4 E5 1/8 F5 1/8 G5 1/4 G5 1/8 F5 1/8 E5 1/4 E5 1/4 A4 1/4 D5 1/8 C5 1/8 A4 1/4 A4 1/8 G4 1/8 F4 1/2",
        "A4 1/4 C5 1/8 D5 1/8 E5 1/4 E5 1/8 D5 1/8 C5 1/4 C5 1/4 E4 1/4 A4 1/8 G4 1/8 E4 1/4 E4 1/8 D4 1/8 C4 1/2",
        120,
    ),
    "korobeiniki": (
        "E5 1/4 B4 1/8 C5 1/8 D5 1/4 C5 1/8 B4 1/8 A4 1/4 A4 1/8 C5 1/8 E5 1/4 D5 1/8 C5 1/8 B4 1/4 B4 1/8 C5 1/8 D5 1/4 E5 1/4 C5 1/4 A4 1/4 A4 1/2",
        "C5 1/4 G4 1/8 A4 1/8 B4 1/4 A4 1/8 G4 1/8 F4 1/4 F4 1/8 A4 1/8 C5 1/4 B4 1/8 A4 1/8 G4 1/4 G4 1/8 A4 1/8 B4 1/4 C5 1/4 A4 1/4 F4 1/4 F4 1/2",
        140,
    ),
    "axel_f": (
        "F5 1/8 G#5 1/4 F5 1/16 F5 1/16 A#5 1/8 F5 1/8 D#5 1/8 F5 1/8 C6 1/4 F5 1/16 F5 1/16 C#6 1/8 C6 1/8 G#5 1/8 F5 1/8 C6 1/8 F6 1/8 F5 1/16 D#5 1/16 D#5 1/8 C5 1/8 G5 1/8 F5 1/4",
        "C5 1/8 D#5 1/4 C5 1/16 C5 1/16 F5 1/8 C5 1/8 A#4 1/8 C5 1/8 G5 1/4 C5 1/16 C5 1/16 G#5 1/8 G5 1/8 D#5 1/8 C5 1/8 G5 1/8 C6 1/8 C5 1/16 A#4 1/16 A#4 1/8 G4 1/8 D#5 1/8 C5 1/4",
        108,
    ),
    "nokia_tune": (
        "E6 1/8 D6 1/8 F#5 1/4 G#5 1/4 C#6 1/8 B5 1/8 D5 1/4 E5 1/4 B5 1/8 A5 1/8 C#5 1/4 E5 1/4 A5 1/2",
        "B5 1/8 A5 1/8 C#5 1/4 E5 1/4 G#5 1/8 F#5 1/8 A4 1/4 B4 1/4 F#5 1/8 E5 1/8 G#4 1/4 B4 1/4 E5 1/2",
        180,
    ),
    "pacman": (
        "B4 1/16 B5 1/16 F#5 1/16 D#5 1/16 B5 1/16 F#5 1/8 D#5 1/8 C5 1/16 C6 1/16 G5 1/16 E5 1/16 C6 1/16 G5 1/8 E5 1/8",
        "F#4 1/16 F#5 1/16 D#5 1/16 B4 1/16 F#5 1/16 D#5 1/8 B4 1/8 G4 1/16 G5 1/16 E5 1/16 C5 1/16 G5 1/16 E5 1/8 C5 1/8",
        160,
    ),
    "mario": (
        "E5 1/8 E5 1/8 P 1/8 E5 1/8 P 1/8 C5 1/8 E5 1/4 G5 1/4 P 1/4 G4 1/4",
        "C4 1/8 C4 1/8 P 1/8 C4 1/8 P 1/8 G3 1/8 C4 1/4 E4 1/4 P 1/4 E3 1/4",
        200,
    ),
    "take_on_me": (
        "F#4 1/8 F#4 1/8 D4 1/8 B3 1/8 P 1/8 B3 1/8 P 1/8 E4 1/8 P 1/8 E4 1/8 P 1/8 E4 1/8 G#4 1/8 G#4 1/8 A4 1/8 B4 1/8",
        "D4 1/8 D4 1/8 B3 1/8 G#3 1/8 P 1/8 G#3 1/8 P 1/8 C#4 1/8 P 1/8 C#4 1/8 P 1/8 C#4 1/8 E4 1/8 E4 1/8 F#4 1/8 G#4 1/8",
        160,
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
