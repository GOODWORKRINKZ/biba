# Synth Percent Detune Design

**Status:** approved for implementation

## Goal

Replace the fixed absolute software synth detune with a percentage-based detune for all synth playback.

## Scope

In scope:
- software detune logic in `biba-controller/buzzer/motor_synth.py`
- synth playback only
- mono and split BLHeli playback
- deployment to the robot after verification

Out of scope:
- voice, spectral, PCM, FFT playback redesign
- event melody rewrite

## Decision

- Use a global percentage-based detune for the entire synth path.
- Baseline detune percent: `20%` of the center frequency.
- Keep a small minimum floor to avoid vanishing low-note deltas.

## Detune Formula

For a requested synth center frequency `f`:

- `delta_hz = max(min_detune_hz, round(f * detune_percent))`
- split the delta symmetrically across forward/reverse pins
- when the delta is odd, keep the pair balanced with a one-hertz difference between the two sides

This preserves the current "difference tone" model while making the absolute detune scale with note height.

## Initial Tuning

- `detune_percent = 0.20`
- `min_detune_hz = 60`

Expected examples:
- `440 Hz` -> `delta = 88` -> `396 / 484`
- `523 Hz` -> `delta = 105` -> `471 / 576`
- `392 Hz` -> `delta = 78` -> `353 / 431`

## Rationale

The current fixed absolute detune is acceptable for some notes but weak on quieter lower system sounds such as `disarm`.

Percentage scaling keeps the audible difference larger for higher notes while the minimum floor prevents low notes from collapsing into too-small separations.

## Testing

Testing should update the synth detune expectations directly:
- mono software synth frequency pair tests
- split software synth frequency pair tests
- restore-state behavior after playback

Then run focused synth tests, full pytest, and deploy through the standard GitHub and `bbupdate` flow.