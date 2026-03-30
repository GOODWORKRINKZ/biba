# BLHeli Melody Anti-Roll Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce wheel roll during shared-channel BLHeli melody playback while keeping melodies audible on both motors.

**Architecture:** Add a dedicated slower bipolar slice-switching path for BLHeli tone playback on shared-channel BTS7960 motor groups. Keep the existing WAV and spectral bipolar helpers unchanged, and route both mono and split BLHeli playback through the new melody-specific helper only when shared-channel directional pairs are present.

**Tech Stack:** Python, pigpio, pytest, existing `MotorSynth`, `wav_player`, and BLHeli parser.

---

### Task 1: Add failing shared-channel BLHeli anti-roll regression tests

**Files:**
- Modify: `tests/test_motor_synth.py`
- Review: `biba-controller/buzzer/motor_synth.py`

**Step 1:** Add a failing mono BLHeli regression test that verifies shared-channel melody playback switches active direction at least once during a sustained note while still producing non-zero PWM on both motors.

**Step 2:** Add a failing split BLHeli regression test with the same expectation for left/right tones.

**Step 3:** Run `pytest tests/test_motor_synth.py -q -k 'shared_pwm_channels'` and verify the new expectations fail against the current one-directional melody implementation.

### Task 2: Implement slower BLHeli melody anti-roll switching

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Review: `biba-controller/buzzer/wav_player.py`

**Step 1:** Add a dedicated BLHeli melody slice constant for shared-channel anti-roll playback.

**Step 2:** Implement a melody-specific bipolar helper that alternates direction over the new coarser slices for left and right tone playback.

**Step 3:** Route `_tone()` through that helper when shared-channel directional groups are present.

**Step 4:** Route `_split_tone()` through that helper when shared-channel directional groups are present.

**Step 5:** Keep the existing WAV/spectral bipolar helpers untouched.

### Task 3: Verify focused audio regressions

**Files:**
- Test: `tests/test_motor_synth.py`
- Test: `tests/test_wav_player.py`

**Step 1:** Run `pytest tests/test_motor_synth.py -q`.

**Step 2:** Run `pytest tests/test_wav_player.py -q`.

**Step 3:** Run `pytest tests/test_motor_synth.py tests/test_wav_player.py -q`.

**Step 4:** Run `ruff check biba-controller/buzzer/motor_synth.py tests/test_motor_synth.py`.

### Task 4: Commit, push, and deploy

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Modify: `tests/test_motor_synth.py`

**Step 1:** Commit only the verified BLHeli melody anti-roll changes.

**Step 2:** Push to `main`.

**Step 3:** Wait for the relevant GitHub Actions runs to finish successfully.

**Step 4:** Deploy with the robot-side `bbupdate` workflow.

**Step 5:** Verify robot `HEAD` and controller container health after restart.