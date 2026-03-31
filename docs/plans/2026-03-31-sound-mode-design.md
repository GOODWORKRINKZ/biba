# Sound Mode Design

## Goal

Replace the temporary voice-first audio routing with an explicit runtime sound mode parameter so the controller can run in one of three intentional modes:

- `voice`: direct WAV playback
- `spectral_voice`: FFT-derived motor speech playback
- `synth`: named synthetic melodies and tones only

The immediate operational goal is to run the robot in `synth` mode so all system sounds stop using voice WAV assets without deleting the existing voice pipeline.

## Current Problem

The controller currently treats voice playback as the primary path for most system events and falls back to synth sounds only when voice playback is disabled or unavailable. That creates two issues:

1. The runtime behavior is hard to reason about because the active backend is inferred indirectly from several `*_VOICE_ENABLED` flags and method availability.
2. Temporarily disabling all voice playback requires scattered config changes instead of one intentional mode switch.

## Decision

Introduce a single configuration parameter:

- `SOUND_MODE=voice|spectral_voice|synth`

This mode determines which backend is used for system event sounds:

- `voice` uses `play_wav` and `play_wav_async`
- `spectral_voice` uses `play_spectral` and `play_spectral_async`
- `synth` uses `play_named` and `play_named_async`

## Event Mapping

When `SOUND_MODE=synth`, system events map to existing synth names:

- `startup` -> `STARTUP_MELODY` if configured, otherwise `startup`
- `arm` -> `arm`
- `disarm` -> `disarm`
- `connected` -> `connected`
- `disconnected` -> `disconnected`
- `failsafe` -> `failsafe`
- `low_voltage` -> `low_voltage`
- `sos` remains on the dedicated SOS synth path already used by the beacon manager

This keeps startup behavior configurable while moving all system notifications off WAV assets.

## Runtime Shape

Add a small audio backend selection layer in `main.py`:

- one helper to resolve synth event names
- one blocking helper for system event playback
- one async helper for system event playback

The existing event handlers should call these helpers instead of making their own voice-first decisions.

## Compatibility Rules

- `voice audition mode` remains voice-specific and should ignore `SOUND_MODE`, because it is a diagnostic path for auditioning voice candidates.
- Existing voice asset config stays in place so voice and spectral voice modes remain usable.
- Existing `*_VOICE_ENABLED` flags remain meaningful only for whether a particular voice event is allowed when the mode is voice-based.

## Testing Strategy

Add tests that prove:

1. `SOUND_MODE=voice` routes through `play_wav`
2. `SOUND_MODE=spectral_voice` routes through `play_spectral`
3. `SOUND_MODE=synth` routes through named synth playback and avoids WAV/spectral paths
4. Main-loop startup and runtime events honor the selected sound mode

## Non-Goals

- Removing the voice pipeline
- Changing voice audition behavior
- Redesigning individual synth melodies
- Touching Docker or deployment flow as part of this logic change