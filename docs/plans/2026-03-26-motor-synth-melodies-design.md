# Motor Synth & BLHeli Melodies — Design Document

## Summary

Replace the piezo buzzer with motor-based sound playback using hardware PWM. Add a library of melodies in BLHeli32-compatible format. Allow melody selection from RC transmitter via a dedicated channel. Create an EdgeTX Lua script for melody browsing/triggering.

## Problem

1. Piezo buzzer is quiet and boring
2. Software PWM caps at ~8 kHz — audible motor whine at low throttle
3. No way to play music from the transmitter
4. Melodies use an internal `(freq, duration, pause)` format — not shareable with the FPV community

## Design

### 1. BLHeli Melody Format

BLHeli32 format: `NOTE OCTAVE DURATION`, space-separated. Example:

```
D5 1/4 E5 1/8 P 1/8 F#5 1/4
```

- Notes: `C C# D D# E F F# G G# A A# B`
- Octaves: `4`–`7`
- Durations: `1/1 1/2 1/4 1/8 1/16`
- `P` = pause (rest)

A parser converts these into `list[tuple[float, float]]` = `(frequency_hz, duration_s)` for playback.

### 2. Melody Library

All melodies stored as BLHeli format strings in `biba-controller/buzzer/melodies.py`. System melodies (arm, disarm, etc.) converted from `(freq, dur_ms, pause_ms)` tuples to BLHeli strings. New fun melodies added:

| Key | Name | Use |
|-----|------|-----|
| `startup` | Imperial March | Auto-play on boot |
| `arm` | Quick ascending sweep | On arm |
| `disarm` | Two descending tones | On disarm |
| `low_voltage` | Triple alarm | Low battery |
| `failsafe` | Single low tone | Connection lost |
| `sos` | Morse SOS | Beacon |
| `connected` | Happy chirp | Link restored |
| `disconnected` | Sad descend | Link lost |
| `shutdown` | Reverse startup | On shutdown |
| `imperial_march` | Imperial March (Star Wars) | Fun / startup option |
| `katyusha` | Катюша | Fun |
| `korobeiniki` | Korobeiniki (Tetris) | Fun |
| `axel_f` | Axel F (Beverly Hills Cop) | Fun |
| `nokia_tune` | Nokia Tune | Fun |
| `mario` | Super Mario Bros | Fun |
| `take_on_me` | Take On Me (A-Ha) | Fun |
| `pacman` | Pac-Man | Fun |

Startup melody configurable via env var `STARTUP_MELODY` (default: `imperial_march`).

Optional two-channel polyphony is supported through explicit split melody entries, where a named sound can define separate left and right BLHeli parts. If a split entry is absent, playback falls back to the mono melody.

### 3. BLHeli Parser (`biba-controller/buzzer/blheli_parser.py`)

```python
def parse_blheli(melody_str: str, tempo_bpm: int = 120) -> list[tuple[float, float]]:
    """Parse BLHeli32 melody string into (freq_hz, duration_s) pairs."""
```

Note-to-frequency conversion uses standard equal temperament: $f = 440 \times 2^{(n-69)/12}$ where $n$ is the MIDI note number.

### 4. MotorSynth (replaces Buzzer)

`biba-controller/buzzer/motor_synth.py` — same interface as `Buzzer`, but uses `pi.hardware_PWM(pin, freq, duty)` instead of software PWM.

- Same `play()` / `play_async()` / convenience methods
- Uses any GPIO pin capable of hardware PWM (currently: buzzer pin GPIO 17 — software PWM only)
- **Phase 1**: Keep buzzer pin (GPIO 17) with software PWM (no hardware change needed)
- **Phase 2** (future, after GPIO rewiring): Switch to hardware PWM on motor pins for true ultrasonic 20 kHz

### 5. RC Channel for Melody Selection

**Channel**: CH8 (free), configurable via `CH_MELODY` env var.

**Scheme**: Channel value 0.0–1.0 divided into N zones. Each zone = one melody from the fun playlist.
- Zone boundaries: `melody_index = floor(channel_value * num_melodies)`
- Channel at 0.0 = no melody / stop
- Any change in zone triggers melody playback

### 6. Lua Script (`lua/SCRIPTS/MIXES/melody.lua`)

EdgeTX mix script that writes to the melody channel. Uses a **6-position switch** (or 3-position + logic) mapped to CH8:

- Position 0: Off
- Position 1–7: Melody 1–7

The existing telemetry screen `biba.lua` stays unchanged.

### 7. Config Changes

New env vars in `config.py` and `docker-compose.yml`:

```
CH_MELODY=8
STARTUP_MELODY=imperial_march
```

## Out of Scope

- Hardware PWM migration for motor drive — future phase (requires GPIO rewiring)
- Downloading melodies from the internet at runtime
- RTTTL format support (BLHeli only)

## Testing

- BLHeli parser: unit tests for note parsing, duration, octave, sharps, pauses
- Melody catalog: all entries parseable without error
- MotorSynth: mock pigpio, verify `play()` calls correct sequence
- RC channel melody selection: zone calculation, edge cases
