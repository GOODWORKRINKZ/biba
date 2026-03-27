# FFT Speech Tuning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve speech intelligibility of the current motor-coil FFT playback by upgrading the one-peak spectral model to a short-window, overlapping, multi-peak analysis and playback path.

**Architecture:** Keep `MotorSynth.play_spectral()` as the public entrypoint, but change the internals of `wav_player.py` to analyze several dominant peaks per frame and play them deterministically. Preserve the existing fallback PCM path and keep the first pass intentionally narrow.

**Tech Stack:** Python 3.10, pigpio hardware PWM, pytest, existing `wav_player.py` spectral code.

---

### Task 1: Add failing tests for multi-peak spectral analysis

**Files:**
- Modify: `tests/test_wav_player.py`
- Modify: `biba-controller/buzzer/wav_player.py`

**Step 1: Write the failing test**

Add tests that describe the new analysis behavior:
- two simultaneous synthetic tones should produce at least two extracted peaks in a frame
- overlapping frames should produce more frames than non-overlapping analysis for the same input

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py -q`
Expected: FAIL because current code extracts only one peak and has no hop-size concept.

**Step 3: Write minimal implementation**

Add a new analysis helper in `biba-controller/buzzer/wav_player.py` that:
- accepts `frame_ms`, `hop_ms`, and `n_peaks`
- scans magnitudes and returns several peaks per frame

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py -q`
Expected: PASS for the new analysis cases.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 2: Add failing tests for multi-peak playback scheduling

**Files:**
- Modify: `tests/test_wav_player.py`
- Modify: `biba-controller/buzzer/wav_player.py`

**Step 1: Write the failing test**

Add tests describing a frame structure like:

```python
frames = [
    ([(500, 120000), (900, 80000)], 10),
]
```

Verify playback issues PWM calls for both peaks within the frame budget and then cleans up.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py -q`
Expected: FAIL because current playback supports only one `(freq, duty, duration)` tuple per frame.

**Step 3: Write minimal implementation**

Implement a new multi-peak playback helper or adapt `play_tone_sequence` so each frame can schedule several tones deterministically.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py -q`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 3: Integrate the new spectral frame format into MotorSynth

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Modify: `tests/test_wav_player.py`

**Step 1: Write the failing test**

Add or adapt an integration test asserting that `MotorSynth.play_spectral()` still drives hardware PWM when given a valid WAV under the new analysis path.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py -q`
Expected: FAIL if the new frame format is not yet wired through `MotorSynth`.

**Step 3: Write minimal implementation**

Update `MotorSynth.play_spectral()` to call the new analysis and playback helpers without changing its public signature.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py -q`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 4: Verify non-spectral regressions stay green

**Files:**
- Modify only if tests require it.

**Step 1: Run focused tests**

Run: `pytest tests/test_wav_player.py tests/test_motor_synth.py -q`
Expected: PASS.

**Step 2: Run broader non-serial test suite**

Run: `pytest tests/ -q --ignore=tests/test_main.py --ignore=tests/test_bms_poller.py --ignore=tests/test_crsf.py --ignore=tests/test_daly.py --ignore=tests/test_daly_ble.py --ignore=tests/test_telemetry.py`
Expected: PASS.

**Step 3: Run lint**

Run: `/home/builder/biba/.venv/bin/ruff check biba-controller/ tests/`
Expected: PASS.

### Task 5: Prepare the hardware evaluation follow-up

**Files:**
- No code required unless adding temporary tuning knobs is justified.

**Step 1: Keep tunable constants visible**

Expose or keep clearly grouped:
- `frame_ms`
- `hop_ms`
- `n_peaks`
- speech band limits

**Step 2: Record next experiment choices**

After hardware feedback, choose one:
- add smoothing and peak hysteresis
- add offline phrase preparation pipeline
- stop and escalate to a richer speech vocoder

Plan complete and saved to `docs/plans/2026-03-27-fft-speech-tuning-plan.md`. Next, I’ll execute the first option in this session with TDD.