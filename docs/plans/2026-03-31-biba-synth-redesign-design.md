# BiBa Synth Redesign Design

**Status:** approved for implementation

## Goal

Redesign the synth-only system sounds around a distinct BiBa identity while removing legacy synth behavior that is no longer relevant to the current robot wiring and runtime mode.

The redesign keeps voice, spectral voice, PCM, and FFT playback intact, but treats synth as a separate product surface with its own constraints and sound language.

## Runtime Scope

In scope:
- `SOUND_MODE=synth`
- two-motor split synth playback
- current BTS7960 wiring: left `12/18`, right `19/13`
- software PWM mode with the current per-motor detune model
- rewrite of the synth event catalog
- cleanup of legacy synth output-driving paths that do not serve the current production mode

Out of scope:
- voice playback redesign
- spectral / FFT / PCM redesign
- deep refactor of WAV tooling
- preserving the old synth melodies

## Production Assumptions

- The production robot runs `BTS7960_PWM_MODE=SOFTWARE`.
- The production robot runs `SOUND_MODE=synth`.
- The synth path should optimize for audibility and recognizability on coarse pigpio software-PWM frequency buckets rather than ideal musical pitch accuracy.
- Split playback is preferred for system sounds because the robot has two independently drivable motors.

## Sound Identity

BiBa should sound like a clever robot-pet, not a generic buzzer.

The core personality is:
- short expressive phrases
- two-syllable or three-syllable gestures
- recognizable `bi-ba`, `ba-bi`, and `bi-bi-ba` shapes
- friendly for normal events, harsher for alarms

The design intentionally abandons the old melody set. System events should become a coherent sound vocabulary rather than a collection of unrelated beeps.

## Hardware-Constrained Musical Model

The synth vocabulary must be written for real software-PWM behavior:
- keep phrases short
- avoid high, dense arpeggios
- prefer low-to-mid bands that remain audible and stable
- prefer contour and rhythm over exact harmonic richness
- use split left/right playback as a compositional tool
- rely on the existing per-motor frequency-difference model for timbre

This means the system sounds are designed around stable frequency regions, not around exact note names alone.

## Target Event Families

- `startup`: a signature BiBa introduction, friendly and identity-defining
- `arm`: a compact affirmative `bi-ba!`
- `disarm`: a softer descending release
- `connected`: short happy acknowledgement
- `disconnected`: short disappointed drop
- `low_voltage`: persistent, readable warning without becoming a shrill alarm
- `failsafe`: more severe, lower, and more forceful than other events
- `sos`: a distinct BiBa distress signal, not a literal reuse of the previous Morse-like pattern
- `trim_enter` / `trim_exit`: service gestures that still fit the same voice
- `shutdown`: a closing gesture that feels like the inverse of startup without needing to mirror it literally

## Code Cleanup Direction

`MotorSynth` should remain capable of:
- mono BLHeli playback
- split BLHeli playback
- software detune playback for forward/reverse pins
- WAV and spectral playback paths for other sound modes

`MotorSynth` should stop carrying legacy synth behavior that is irrelevant to current production synth playback.

The main cleanup target is the old hardware shared-channel fallback that alternates motor directions in time slices. That behavior is not part of the current production synth model and creates unnecessary branching in the synth tone path.

## Testing Strategy

Testing should prove:
- legacy hardware shared-channel synth fallback is removed or no longer selected for the supported synth path
- synth event names still resolve correctly through runtime callers
- the new catalog preserves required event coverage
- split synth playback remains preferred when available
- no regressions are introduced in voice or spectral routing

## Deployment Strategy

Implement in small verified steps:
- rewrite tests first where behavior changes
- update synth logic minimally
- replace catalog entries with the new BiBa vocabulary
- run focused and broader regressions
- deploy through the standard GitHub + GHCR + `bbupdate` flow