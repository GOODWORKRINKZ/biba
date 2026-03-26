# Motor Synth & BLHeli Melodies — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a BLHeli32 melody parser, convert all melodies to BLHeli format, add a library of fun melodies, enable RC-triggered melody playback via CH8, and create an EdgeTX Lua mix script for melody selection.

**Architecture:** New `blheli_parser.py` module parses BLHeli melody strings into `(freq_hz, duration_s)` tuples. Existing `melodies.py` migrated to store BLHeli format strings instead of raw tuples. `Buzzer` updated to play parsed melodies. `main.py` reads CH8 for melody selection. Lua mix script maps a switch to CH8.

**Tech Stack:** Python 3.11, pigpio, pytest, Lua (EdgeTX)

---

### Task 1: BLHeli Parser — note-to-frequency conversion

**Files:**
- Create: `biba-controller/buzzer/blheli_parser.py`
- Create: `tests/test_blheli_parser.py`

**Step 1: Write the failing tests**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && python -m pytest tests/test_blheli_parser.py::TestNoteToFreq -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'buzzer.blheli_parser'`

**Step 3: Write minimal implementation**

```python
"""BLHeli32 melody format parser.

BLHeli32 format: space-separated tokens in pairs: NOTE DURATION
  NOTE  = letter + optional '#' + octave digit, e.g. "C#5", "A4", or "P" (pause)
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


def note_to_freq(name: str, octave: int) -> float:
    """Convert note name + octave to frequency in Hz (equal temperament, A4=440)."""
    semitone = _NOTE_NAMES[name]
    midi = 12 * (octave + 1) + semitone
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))
```

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && python -m pytest tests/test_blheli_parser.py::TestNoteToFreq -v`
Expected: 5 PASSED

**Step 5: Commit**

```bash
git add biba-controller/buzzer/blheli_parser.py tests/test_blheli_parser.py
git commit -m "feat: BLHeli parser — note_to_freq"
```

---

### Task 2: BLHeli Parser — parse_blheli() full string parsing

**Files:**
- Modify: `biba-controller/buzzer/blheli_parser.py`
- Modify: `tests/test_blheli_parser.py`

**Step 1: Write the failing tests**

Add to `tests/test_blheli_parser.py`:

```python
class TestParseBlheli:
    def test_single_note(self):
        result = parse_blheli("A4 1/4", tempo_bpm=120)
        assert len(result) == 1
        freq, dur = result[0]
        assert freq == pytest.approx(440.0, abs=0.5)
        # 1/4 note at 120 BPM = 0.5s
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
        # 1/1 at 60 BPM = 4 beats * 1s/beat = 4s
        _, dur = result[0]
        assert dur == pytest.approx(4.0, abs=0.01)

    def test_sixteenth_note(self):
        result = parse_blheli("A4 1/16", tempo_bpm=120)
        # 1/16 at 120 BPM = 0.125s
        _, dur = result[0]
        assert dur == pytest.approx(0.125, abs=0.01)

    def test_empty_string_returns_empty(self):
        assert parse_blheli("") == []

    def test_invalid_note_raises(self):
        with pytest.raises(ValueError):
            parse_blheli("X4 1/4")
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && python -m pytest tests/test_blheli_parser.py::TestParseBlheli -v`
Expected: FAIL (parse_blheli not implemented)

**Step 3: Write minimal implementation**

Add to `blheli_parser.py`:

```python
_DURATION_RE = re.compile(r"^1/(\d+)$")


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

        # Parse duration
        dur_match = _DURATION_RE.match(dur_token)
        if not dur_match:
            raise ValueError(f"Invalid duration: '{dur_token}'")
        denominator = int(dur_match.group(1))
        duration_s = (4.0 / denominator) * beat_s

        # Parse note
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
```

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && python -m pytest tests/test_blheli_parser.py -v`
Expected: All PASSED

**Step 5: Commit**

```bash
git add biba-controller/buzzer/blheli_parser.py tests/test_blheli_parser.py
git commit -m "feat: BLHeli parser — parse_blheli()"
```

---

### Task 3: Melody Library — BLHeli format strings

**Files:**
- Modify: `biba-controller/buzzer/melodies.py`
- Modify: `tests/test_buzzer.py`

**Step 1: Write the failing tests**

Add to `tests/test_buzzer.py`:

```python
from buzzer.blheli_parser import parse_blheli


class TestBlheliMelodyCatalog:
    def test_blheli_catalog_has_all_system_entries(self):
        expected = {
            "startup", "arm", "disarm", "low_voltage",
            "failsafe", "sos", "connected", "disconnected", "shutdown",
        }
        assert expected.issubset(set(melodies.BLHELI_CATALOG.keys()))

    def test_blheli_catalog_has_fun_melodies(self):
        fun = {"imperial_march", "katyusha", "korobeiniki", "nokia_tune", "pacman"}
        assert fun.issubset(set(melodies.BLHELI_CATALOG.keys()))

    def test_all_blheli_melodies_parseable(self):
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
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && python -m pytest tests/test_buzzer.py::TestBlheliMelodyCatalog -v`
Expected: FAIL with `AttributeError: module 'buzzer.melodies' has no attribute 'BLHELI_CATALOG'`

**Step 3: Write the melody library**

Add to `biba-controller/buzzer/melodies.py` (keep existing `CATALOG` for backward compat, add new):

```python
# BLHeli32 format melodies: dict of name -> (melody_string, tempo_bpm)
BLHELI_CATALOG: dict[str, tuple[str, int]] = {
    # ── System melodies ────────────────────────────
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

# Fun playlist (selectable from RC transmitter) — order matters for zone mapping
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
```

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && python -m pytest tests/test_buzzer.py -v`
Expected: All PASSED (including existing tests — old CATALOG still present)

**Step 5: Commit**

```bash
git add biba-controller/buzzer/melodies.py tests/test_buzzer.py
git commit -m "feat: BLHeli melody library with fun melodies"
```

---

### Task 4: Update Buzzer to play BLHeli melodies

**Files:**
- Modify: `biba-controller/buzzer/buzzer.py`
- Modify: `tests/test_buzzer.py`

**Step 1: Write the failing tests**

Add to `tests/test_buzzer.py`:

```python
class TestBuzzerBlheli:
    def test_play_blheli_calls_tone_sequence(self):
        pi = MagicMock()
        pi.connected = True
        bz = Buzzer(pi, 17)
        with patch("time.sleep"):
            bz.play_blheli("A4 1/4 P 1/8 C5 1/4", tempo_bpm=120)
        # Should have called set_PWM_frequency for A4 and C5 (not for pause)
        freq_calls = [c.args[1] for c in pi.set_PWM_frequency.call_args_list]
        assert len(freq_calls) == 2  # two audible notes
        assert freq_calls[0] == pytest.approx(440, abs=1)

    def test_play_melody_by_name(self):
        pi = MagicMock()
        pi.connected = True
        bz = Buzzer(pi, 17)
        with patch("time.sleep"):
            bz.play_named("arm")
        assert pi.set_PWM_frequency.called
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && python -m pytest tests/test_buzzer.py::TestBuzzerBlheli -v`
Expected: FAIL with `AttributeError: 'Buzzer' object has no attribute 'play_blheli'`

**Step 3: Implement play_blheli and play_named in Buzzer**

Add to `biba-controller/buzzer/buzzer.py`:

```python
from buzzer.blheli_parser import parse_blheli
from buzzer import melodies

# In Buzzer class:

    def play_blheli(self, melody_str: str, tempo_bpm: int = 120) -> None:
        """Play a BLHeli32 format melody string (blocking). Thread-safe."""
        notes = parse_blheli(melody_str, tempo_bpm=tempo_bpm)
        with self._lock:
            for freq, duration_s in notes:
                self._tone(int(freq), int(duration_s * 1000))

    def play_named(self, name: str) -> None:
        """Play a melody from BLHELI_CATALOG by name (blocking)."""
        entry = melodies.BLHELI_CATALOG.get(name)
        if entry is None:
            return
        melody_str, tempo = entry
        self.play_blheli(melody_str, tempo_bpm=tempo)

    def play_named_async(self, name: str) -> None:
        """Play a named melody in a background thread."""
        t = threading.Thread(target=self.play_named, args=(name,), daemon=True)
        t.start()
```

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && python -m pytest tests/test_buzzer.py -v`
Expected: All PASSED

**Step 5: Commit**

```bash
git add biba-controller/buzzer/buzzer.py tests/test_buzzer.py
git commit -m "feat: Buzzer plays BLHeli melodies by name"
```

---

### Task 5: RC Melody Channel in config + main.py

**Files:**
- Modify: `biba-controller/config.py`
- Modify: `biba-controller/main.py`
- Modify: `docker-compose.yml`
- Modify: `tests/test_main.py`

**Step 1: Add config**

Add to `biba-controller/config.py`:

```python
CH_MELODY = _get_env_int("CH_MELODY", 8)
STARTUP_MELODY = os.getenv("STARTUP_MELODY", "imperial_march")
```

Add to `docker-compose.yml` environment section:

```yaml
      CH_MELODY: ${CH_MELODY:-8}
      STARTUP_MELODY: ${STARTUP_MELODY:-imperial_march}
```

**Step 2: Add melody selection to main.py**

In `main.py`, add before the main loop:

```python
from buzzer import melodies

melody_zone = -1  # current melody zone index
```

Inside the `if channels is not None:` block, add melody handling:

```python
                # Melody selection via RC channel
                melody_ch = _get_channel(channels, config.CH_MELODY)
                num_melodies = len(melodies.FUN_PLAYLIST)
                if num_melodies > 0 and melody_ch > 0.05:
                    new_zone = min(int(melody_ch * num_melodies), num_melodies - 1)
                    if new_zone != melody_zone:
                        melody_zone = new_zone
                        name = melodies.FUN_PLAYLIST[melody_zone]
                        LOGGER.info("Playing melody: %s", name)
                        buzzer.play_named_async(name)
                elif melody_ch <= 0.05:
                    melody_zone = -1
```

Change startup tone from `buzzer.startup_tone()` to:

```python
    buzzer.play_named(config.STARTUP_MELODY)
```

Also update `_NullBuzzer` to add `play_named`, `play_named_async`, `play_blheli` stubs.

**Step 3: Run all tests**

Run: `cd /home/builder/biba && python -m pytest -v`
Expected: All PASSED

**Step 4: Commit**

```bash
git add biba-controller/config.py biba-controller/main.py docker-compose.yml tests/test_main.py
git commit -m "feat: RC melody channel (CH8) with zone selection"
```

---

### Task 6: EdgeTX Lua Mix Script for Melody Selection

**Files:**
- Create: `lua/SCRIPTS/MIXES/melody.lua`

**Step 1: Write the Lua mix script**

```lua
-- BiBa Melody Selector — EdgeTX Mix Script
-- Maps a 6-position switch (SA) to output values for CH8
-- Install: copy to /SCRIPTS/MIXES/ on SD card
-- Setup: In EdgeTX model setup, add Custom Script → melody.lua on CH8

-- Config: change this to your switch (sa, sb, sc, sd, se, sf)
local SWITCH = "se"

local function output(value)
  -- EdgeTX mix scripts return -1024..1024
  -- Controller normalizes to 0.0..1.0
  return value
end

local function run()
  local sw = getValue(SWITCH)
  -- 6-pos switch: -1024, -614, -205, 205, 614, 1024
  -- Map to zones: 0=off, 1-5=melody 1-5 (etc)
  if sw < -800 then
    return output(-1024)  -- zone 0: off
  elseif sw < -400 then
    return output(-614)   -- zone 1
  elseif sw < 0 then
    return output(-205)   -- zone 2
  elseif sw < 400 then
    return output(205)    -- zone 3
  elseif sw < 800 then
    return output(614)    -- zone 4
  else
    return output(1024)   -- zone 5
  end
end

return { run=run }
```

**Step 2: Commit**

```bash
git add lua/SCRIPTS/MIXES/melody.lua
git commit -m "feat: EdgeTX melody selector Lua mix script"
```

---

### Task 7: Run full test suite & final verification

**Step 1: Run all tests**

Run: `cd /home/builder/biba && python -m pytest -v`
Expected: All tests PASSED

**Step 2: Verify no import errors**

Run: `cd /home/builder/biba/biba-controller && python -c "from buzzer.blheli_parser import parse_blheli; from buzzer.melodies import BLHELI_CATALOG, FUN_PLAYLIST; print(f'{len(BLHELI_CATALOG)} melodies, {len(FUN_PLAYLIST)} in playlist')"`
Expected: `17 melodies, 8 in playlist`

**Step 3: Final commit and push**

```bash
git push
```
