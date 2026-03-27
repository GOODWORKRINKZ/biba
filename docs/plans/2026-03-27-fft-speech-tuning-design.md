# FFT Speech Tuning Design

## Goal

Improve intelligibility of motor-coil speech playback without replacing the current architecture immediately.

## Current State

The current spectral path in `biba-controller/buzzer/wav_player.py` reduces each analysis frame to exactly one dominant frequency plus a loudness value. That makes the output recognizable as a synthetic voice effect, but not intelligible as speech. The bottleneck is representational: real speech contains multiple simultaneous formants and fast transitions between them, while the current model emits one whistle-like tone per frame.

## Options Considered

### Option 1: Tune the current FFT vocoder

Changes:
- shorten analysis windows from 20 ms to roughly 8-12 ms
- add frame overlap (50-75%)
- extract multiple peaks per frame instead of one
- focus analysis on the speech band
- smooth frequency and amplitude transitions between frames

Pros:
- minimal architectural change
- fastest path to useful feedback on real hardware
- preserves current playback pipeline and configuration model

Cons:
- speech will remain robotic
- intelligibility gains may be limited by motor acoustics

### Option 2: Offline phrase preparation for the existing channel

Changes:
- add a preprocessing script for voice assets
- generate slower, clearer, band-limited speech assets tailored to the FFT path
- audition multiple variants and keep the most intelligible ones

Pros:
- likely best ratio of effort to practical clarity for short robot phrases
- no hard real-time complexity increase

Cons:
- becomes a content pipeline, not just an algorithm fix
- each phrase may need hand tuning

### Option 3: Replace the one-peak model with a richer speech vocoder

Changes:
- multi-tone band vocoder, or
- LPC/formant-style approximation, or
- several simultaneous carriers driven by band energy

Pros:
- best long-term model for intelligible speech

Cons:
- substantially higher complexity
- unclear whether the motor hardware will justify the extra complexity

## Recommendation

Implement Option 1 first.

Reasoning:
- it is the lowest-cost experiment that directly tests whether the problem is mostly parameterization or the one-peak model itself
- it keeps existing code structure intact
- it creates reusable machinery for later options, especially offline phrase preparation

If Option 1 produces only marginal gains, move to Option 2 next. Option 3 is reserved for later only if the first two approaches do not provide acceptable intelligibility.

## Chosen First Experiment

The first implementation pass will add:
- configurable `frame_ms`
- configurable `hop_ms`
- configurable `n_peaks`
- extraction of multiple dominant peaks per frame
- multi-tone playback per frame
- basic amplitude thresholding and deterministic peak ordering

This is intentionally limited. More advanced smoothing, envelope tracking, and phrase preprocessing are deferred until the first hardware evaluation.

## Architecture

### Analysis

`wav_to_tones` will be replaced or extended with a multi-peak analysis function that emits frames containing several tones rather than one. Each analysis frame will include a duration and an ordered list of peaks with `(frequency, duty)` pairs.

### Playback

The current `play_tone_sequence` assumes one frequency at a time. The new playback layer will instead schedule several tones per frame, likely by time-slicing or frame subdivision, because a single motor PWM pin cannot emit several independent frequencies simultaneously. The first pass will favor simple deterministic time slicing over more complex synthesis.

### API Shape

The spectral API should remain callable from `MotorSynth.play_spectral(path)`. Internally it may switch from `list[tuple[int, int, int]]` to a richer frame structure, but callers above `wav_player.py` should not need to care.

## Risks

- Time slicing several peaks may improve intelligibility less than expected.
- Very short frames may make the output noisier if peak selection is unstable.
- More spectral detail may increase harshness unless peak filtering is conservative.

## Testing Strategy

- unit tests for peak extraction on synthetic tones with 1 and 2 known frequencies
- regression tests for silence and low-energy frames
- playback tests to confirm multi-peak frames schedule expected PWM calls
- existing spectral tests updated to reflect the new frame format if needed

## Success Criteria

- code supports multi-peak spectral analysis with overlap
- tests cover the new analysis and playback behavior
- real hardware output is at least more syllable-like than the current one-peak mode
- no regression to startup/arm event playback stability