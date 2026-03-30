# Motor Audio Zero-Mean Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore `MOTOR1_INVERTED=1`, `MOTOR2_INVERTED=0` and make motor-audio playback alternate direction fast enough that the average drive torque is near zero while sounds remain audible.

**Architecture:** Keep the drive path unchanged. Update deployment/config defaults back to left inverted and right normal. For audio, preserve the loud shared-channel hardware PWM path but route playback through a bipolar strategy that alternates forward/reverse direction over short slices or waveform sign so the H-bridge does not bias wheel rotation during playback.

**Tech Stack:** Python, pigpio, pytest, existing `MotorSynth` and `wav_player` audio pipeline.

---

### Task 1: Restore inversion defaults

**Files:**
- Modify: `biba-controller/config.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `docs/deployment.md`
- Test: `tests/test_config.py`

**Step 1:** Update tests to expect `MOTOR1_INVERTED=1`, `MOTOR2_INVERTED=0`.

**Step 2:** Run `pytest tests/test_config.py -q` and verify the relevant assertions fail.

**Step 3:** Update config and deployment defaults to `1/0`.

**Step 4:** Run `pytest tests/test_config.py -q` and verify it passes.

### Task 2: Add anti-roll audio regression tests

**Files:**
- Modify: `tests/test_wav_player.py`

**Step 1:** Add a failing test that shared-channel PCM playback alternates between forward and reverse directional pins instead of driving one direction only.

**Step 2:** Add a failing test that shared-channel spectral playback alternates directional pins across adjacent slots/frames so the average direction is not biased.

**Step 3:** Run targeted pytest commands and verify both tests fail for the right reason.

### Task 3: Implement zero-mean shared-channel audio

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Modify: `biba-controller/buzzer/wav_player.py`
- Review: `biba-controller/main.py`

**Step 1:** Preserve enough directional-pin metadata in `MotorSynth` to support bipolar playback on shared hardware PWM channels.

**Step 2:** Implement shared-channel bipolar playback helpers for PCM and spectral paths that alternate active direction while keeping the average torque near zero.

**Step 3:** Route `MotorSynth.play_wav()` and `MotorSynth.play_spectral()` through those helpers when shared-channel directional pairs are present.

**Step 4:** Keep legacy behavior for non-shared-channel or non-split audio paths.

### Task 4: Verify and deploy

**Files:**
- Test: `tests/test_config.py`
- Test: `tests/test_wav_player.py`
- Test: `tests/test_main.py`

**Step 1:** Run `pytest tests/test_config.py tests/test_wav_player.py tests/test_main.py -q`.

**Step 2:** Run `ruff check biba-controller/config.py biba-controller/buzzer/motor_synth.py biba-controller/buzzer/wav_player.py tests/test_config.py tests/test_wav_player.py tests/test_main.py`.

**Step 3:** Commit, push, wait for CI, and deploy via `bbupdate`.