# SAM Spectral Tuning Design

## Goal

Improve speech intelligibility for existing SAM-generated WAV assets without changing the assets themselves.

## Current State

The current spectral path already extracts multiple peaks per frame, but it still loses too much of SAM's structure:
- only two peaks are kept per frame
- peaks are split across left and right motors
- playback time-slices peaks aggressively, which turns formants into chatter
- noisy consonants collapse into unstable tonal fragments

This is especially harmful for SAM because the source waveform is already a compact synthetic speech model built from a few simultaneous carriers plus noise. Over-reducing it again strips away the cues that make it recognizable.

## Constraints

- Keep existing WAV assets unchanged.
- Prioritize intelligibility over stereo separation or balanced energy across motors.
- Work within the current software PWM evaluation setup.
- Preserve the public `MotorSynth.play_spectral(path)` entrypoint.

## Options Considered

### Option 1: Parameter-only tuning

Changes:
- shorten frame and hop sizes
- increase number of extracted peaks
- retune thresholds and smoothing

Pros:
- lowest implementation cost
- useful baseline experiment

Cons:
- still treats all frames as the same kind of signal
- likely weak for noisy consonants

### Option 2: SAM-aware spectral tuning

Changes:
- raise voiced-frame peak count to three
- classify frames as voiced or noisy
- stabilize voiced peaks more aggressively
- stop splitting speech peaks across motors during playback
- use a simple noisy-frame surrogate instead of forcing a fake dominant tone

Pros:
- best match to the known structure of SAM output
- preserves more phonetic information without changing assets
- still fits inside the existing spectral playback architecture

Cons:
- more logic in both analysis and playback
- noisy-frame heuristics will need tuning on hardware

### Option 3: Richer vocoder replacement

Changes:
- replace peak scheduling with a more complete speech model

Pros:
- highest ceiling for intelligibility

Cons:
- much larger change
- not justified before tuning the existing path for the known SAM signal model

## Recommendation

Implement Option 2.

Reasoning:
- SAM output is already structured like a small formant synthesizer, so preserving a few stable carriers is more valuable than generic FFT peak picking
- intelligibility matters more than left/right differentiation in the current evaluation phase
- this keeps the public API intact while improving both analysis and playback behavior where the information is currently lost

## Proposed Changes

### Analysis

Tune `wav_to_peak_frames` toward SAM-like speech:
- increase default `n_peaks` from 2 to 3
- shorten default frame size from 12 ms to roughly 8-10 ms
- shorten default hop from 6 ms to roughly 3-4 ms
- classify each frame as voiced or noisy using simple signal heuristics such as peak structure and zero-crossing density
- for voiced frames, keep up to three stable peaks with stronger frequency snapping and duty smoothing
- for noisy frames, avoid pretending there is a strong single pitch; instead emit a simplified upper-band surrogate pattern that better preserves consonant events

### Playback

For speech playback under split motor groups:
- do not distribute different speech peaks across left and right motors
- instead feed both sides the same speech-oriented frame content so intelligibility is preserved
- keep deterministic slot-based playback, but favor stable voiced peaks over maximum spectral variety when the frame budget is tight
- allow noisy frames to use a simple dense upper-band pattern rather than a set of unstable tonal peaks

### API Shape

Keep `MotorSynth.play_spectral(path)` unchanged.

Internally, speech-oriented frame metadata can become richer than the current `list[(freq, duty)]`, but callers above `wav_player.py` should not need to know about the change.

## Risks

- noisy-frame detection may be too aggressive and reduce voiced detail
- shorter windows may increase jitter if stabilization is not strong enough
- identical left/right speech playback may reduce perceived spatial richness, but that is acceptable for this phase because intelligibility is the priority

## Testing Strategy

- unit tests for three-component voiced frames
- unit tests for noisy-frame detection or surrogate generation
- regression tests that voiced-frame stabilization reduces unnecessary jitter
- playback tests verifying speech frames are not split across motors in the split-motor path
- regression checks on `arm_begin.wav` to confirm more useful structure survives analysis

## Success Criteria

- the analyzer preserves more of SAM's carrier structure per frame
- speech playback no longer loses formants by splitting them across motors
- consonant-like events are represented more clearly than with the current tonal-only reduction
- existing spectral playback entrypoints remain intact