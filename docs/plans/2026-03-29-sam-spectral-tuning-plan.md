# SAM Spectral Tuning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve intelligibility of existing SAM-generated voice WAVs by tuning the spectral analyzer and player for SAM-like voiced and noisy frames without changing the assets.

**Architecture:** Keep `MotorSynth.play_spectral()` as the public entrypoint. Extend `biba-controller/buzzer/wav_player.py` with SAM-oriented frame analysis and speech-aware split-motor playback so speech peaks are preserved instead of being distributed across motors.

**Tech Stack:** Python 3.10, pigpio, software PWM evaluation path, pytest, existing spectral voice-cache pipeline.

---

### Task 1: Add failing analysis tests for SAM-like voiced frames

**Files:**
- Modify: `tests/test_wav_player.py`
- Modify: `biba-controller/buzzer/wav_player.py`

**Step 1: Write the failing test**

Add tests that describe the new analysis behavior:
- a synthetic three-component voiced frame should preserve three peaks
- shorter hop size should still produce dense overlapping frames

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py -q`
Expected: FAIL because the current defaults and peak handling do not preserve the new voiced-frame expectation.

**Step 3: Write minimal implementation**

Adjust `wav_to_peak_frames()` defaults and peak extraction so voiced SAM-like frames can retain three useful peaks.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py -q`
Expected: PASS for the new voiced-frame cases.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 2: Add failing tests for speech-aware split playback

**Files:**
- Modify: `tests/test_wav_player.py`
- Modify: `biba-controller/buzzer/wav_player.py`
- Modify: `biba-controller/buzzer/motor_synth.py`

**Step 1: Write the failing test**

Add tests describing that speech-oriented split playback should send equivalent speech content to both sides instead of distributing different peaks across motors.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py -q`
Expected: FAIL because current split playback distributes peak lists by index.

**Step 3: Write minimal implementation**

Add a speech-aware split path that mirrors or shares speech frame content across motor groups.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py -q`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 3: Add failing tests for noisy-frame handling

**Files:**
- Modify: `tests/test_wav_player.py`
- Modify: `biba-controller/buzzer/wav_player.py`

**Step 1: Write the failing test**

Add tests showing that a noisy high-band frame should not collapse into a single unstable low-band tone and instead should produce a deterministic surrogate suitable for playback.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py -q`
Expected: FAIL because current logic only extracts tonal peaks.

**Step 3: Write minimal implementation**

Add a simple noisy-frame classification and surrogate generation path.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py -q`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 4: Rebuild spectral cache and verify targeted behavior

**Files:**
- Modify: `biba-controller/voice-cache/*.json`

**Step 1: Rebuild cache**

Run the existing cache builder for `biba-controller/voice` into `biba-controller/voice-cache`.

**Step 2: Verify targeted tests**

Run: `pytest tests/test_wav_player.py tests/test_motor_synth.py -q`
Expected: PASS.

**Step 3: Verify full suite**

Run: `pytest -q`
Expected: PASS.

### Task 5: Deploy and evaluate on robot

**Files:**
- No code changes required in this step.

**Step 1: Commit and push**

Commit only after fresh verification succeeds.

**Step 2: Wait for CI image build**

Wait for the relevant GitHub Actions workflows to pass for the pushed revision.

**Step 3: Deploy through `bbupdate`**

Use the robot-side update workflow via interactive shell.

**Step 4: Verify runtime state**

Check container health, deployed revision, and effective motor env.

**Step 5: Perform listening check**

Evaluate whether arm speech is more syllable-like and whether consonant events survive better than before.