# Motor Synth Two-Channel Polyphony Design

## Summary

Extend the motor melody system so any named BLHeli melody can optionally define separate left and right parts. When both parts are defined and the runtime has split left/right motor groups, playback becomes true two-channel polyphony. When a melody has no split definition, playback remains mono through the existing path.

## Problem

1. The current system only supports explicit two-channel BLHeli playback for a tiny subset of melodies.
2. Most named sounds still collapse to one melody line played on both motors.
3. We want richer left/right musical motion without breaking existing mono behavior.
4. The code should not require every catalog entry to be converted immediately.

## Requirements

1. System melodies and fun melodies may define independent left and right parts.
2. Mono melodies must keep working unchanged.
3. Runtime selection must prefer split playback only when a split definition exists and the synth has split motor groups.
4. The data format must be simple enough to author by hand in `melodies.py`.
5. Existing audio safeguards for shared-channel zero-mean playback must continue to apply.

## Design

### 1. Catalog Model

Keep the existing mono catalog:

- `BLHELI_CATALOG: dict[str, tuple[str, int]]`

Expand the split catalog into the primary source of optional polyphonic definitions:

- `SPLIT_BLHELI_CATALOG: dict[str, tuple[str, str, int]]`

Each split entry remains:

```python
name: (left_melody_str, right_melody_str, tempo_bpm)
```

This avoids a risky catalog migration and directly matches the desired fallback rule:

- split entry exists -> play polyphonic left/right parts
- split entry missing -> fall back to mono entry

### 2. Playback Routing

`MotorSynth.play_named()` already checks `SPLIT_BLHELI_CATALOG` before `BLHELI_CATALOG`. We keep that routing model and broaden its usage from two trim-only sounds to the full catalog.

Runtime rules:

1. If `name` exists in `SPLIT_BLHELI_CATALOG` and the synth has split motor groups, call `play_split_blheli()`.
2. Otherwise, if `name` exists in `BLHELI_CATALOG`, call `play_blheli()`.
3. Otherwise, do nothing.

No automatic harmonization, transposition, or voice generation is introduced.

### 3. Melody Authoring Strategy

Each target melody gets a hand-authored left and right part.

Authoring guidelines:

1. The left voice should usually carry the main melody or lower support line.
2. The right voice may carry harmony, pedal tones, call-and-response, or octave doubling.
3. Rhythmic alignment should remain simple: note durations should be chosen so both parts can be zipped safely by the existing `play_split_blheli()` implementation.
4. If one side needs silence, use `P` notes explicitly instead of omitting phrases.

### 4. Catalog Coverage

Target full split coverage for:

System melodies:

- `biba_signature`
- `startup`
- `arm`
- `disarm`
- `low_voltage`
- `failsafe`
- `sos`
- `connected`
- `disconnected`
- `shutdown`
- `trim_enter`
- `trim_exit`

Fun melodies:

- `imperial_march`
- `katyusha`
- `korobeiniki`
- `axel_f`
- `nokia_tune`
- `pacman`
- `mario`
- `take_on_me`

Mono fallback remains permanent and valid for any future melodies not yet split-authored.

### 5. Compatibility and Safety

This design does not change:

1. BLHeli parsing rules.
2. Mono playback behavior.
3. WAV or spectral playback.
4. Shared-channel bipolar anti-roll logic.

Therefore the behavioral surface is narrow:

- data additions in `melodies.py`
- selection assertions in tests
- representative playback tests for split routing

## Testing

### Unit Tests

Add or extend tests to verify:

1. Split melodies are selected when present.
2. Mono fallback still works when split data is absent.
3. Representative system melody split entries energize left and right motors with different frequencies.
4. Representative fun melody split entries energize left and right motors with different frequencies.

### Regression Safety

Keep current tests for:

1. mono BLHeli playback
2. shared-channel bipolar alternation
3. WAV/spectral zero-mean behavior

## Out of Scope

1. Automatic harmony generation.
2. More than two voices.
3. New melody storage formats outside BLHeli strings.
4. Rewriting WAV/spectral voice assets.