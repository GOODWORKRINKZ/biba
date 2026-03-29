# Speech Band Range Design

## Goal

Expand the default spectral speech analysis band so motor-voice playback captures the full arming phrase and similar voice prompts more reliably.

## Context

The current split spectral voice path uses the default speech analysis band from [biba-controller/buzzer/wav_player.py](/home/builder/biba/biba-controller/buzzer/wav_player.py). Measured analysis of [biba-controller/voice/arm_begin.wav](/home/builder/biba/biba-controller/voice/arm_begin.wav) shows useful peaks down to about 129 Hz and up to about 775 Hz, while the current defaults are narrower at 150..800 Hz.

## Decision

Change the default speech analysis range from 150..800 Hz to 100..1200 Hz.

## Rationale

- 100 Hz covers the observed low end of the arming phrase with margin.
- 1200 Hz gives extra headroom for brighter consonants and future voice assets without opening the band excessively.
- The change stays local to the spectral speech analysis defaults and does not add new runtime configuration.

## Impact

- Default `wav_to_peak_frames(...)` analysis becomes less likely to discard useful low and upper-mid speech content.
- Existing voice caches must be rebuilt so the new band is reflected in generated peak-frame JSON.
- Tests that encode the previous narrower speech band must be updated to assert the new defaults.