# Motor Synth Software Detune Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Apply the validated BTS7960 software-PWM synth model in code by driving each motor with a fixed symmetric detune pair around the requested note, using a default detune delta of 80 Hz and no modulation.

**Architecture:** Keep hardware-PWM behavior unchanged. In software mode, when a motor has forward and reverse synth pins, treat the requested note as the center frequency and drive the two bridge inputs with `note - delta/2` and `note + delta/2`. Preserve existing split-melody support by applying the same per-motor detune model independently to left and right note streams.

**Tech Stack:** Python, pigpio, pytest, unittest.mock.

---

### Task 1: Add failing tests for software detune playback

**Files:**
- Modify: `tests/test_motor_synth.py`

**Step 1:** Add a failing test covering mono BLHeli playback in software mode with left/right motor groups and complementary pins.

**Step 2:** Assert that a requested `440 Hz` note drives each motor as `400 Hz` on forward pins and `500 Hz` on reverse pins when the mocked pigpio reports those quantized frequencies.

**Step 3:** Add a failing test covering split BLHeli playback in software mode, asserting that left and right requested notes are independently detuned across each motor's forward/reverse pins rather than duplicated onto both directions.

### Task 2: Implement minimal software detune model

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Modify: `biba-controller/config.py`

**Step 1:** Add a config-backed detune delta setting with default `80`.

**Step 2:** Add a helper that applies a center frequency as a symmetric forward/reverse pair for one motor in software mode.

**Step 3:** Route mono tones and split tones through that helper only for software mode with available complementary pins.

**Step 4:** Keep hardware mode, restore logic, and existing public APIs unchanged.

### Task 3: Verify and clean up

**Files:**
- Modify: `tests/test_motor_synth.py` if assertions need small corrections after green

**Step 1:** Run focused motor synth tests and confirm the new tests go red then green.

**Step 2:** Run the broader relevant test set to confirm no regressions in synth, config, and main wiring.

**Step 3:** Leave modulation out of scope for this change.