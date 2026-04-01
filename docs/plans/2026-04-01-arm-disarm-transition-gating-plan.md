# Arm/Disarm Transition Gating Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Delay motor-control activation after arm and delay disarm-tone playback after motor shutdown so arm/disarm tones are not masked by motor state transitions.

**Architecture:** Add two small time-based guards in the main control loop: an arm audio hold window that suppresses `control_active` for 250 ms after arming, and a disarm settle window that keeps the drive at zero for 120 ms before playing the disarm sound. Keep `MotorSynth` unchanged and validate ordering with focused `test_main.py` coverage.

**Tech Stack:** Python 3.10, pytest, existing main loop state machine in `biba-controller/main.py`

---

### Task 1: Add failing transition-order tests

**Files:**
- Modify: `tests/test_main.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**
Add focused tests that prove:
- on arm, sound is triggered before `set_control_active(True)` becomes possible
- on disarm, drive is already held at zero and the disarm sound is delayed by the settle window

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_main.py -q`
Expected: FAIL in the new arm/disarm ordering assertions.

### Task 2: Implement minimal transition guards

**Files:**
- Modify: `biba-controller/main.py`
- Test: `tests/test_main.py`

**Step 1: Write minimal implementation**
Add arm/disarm guard timestamps and apply them in the main loop so:
- arm tone starts immediately, but motor audio control remains disabled for 250 ms
- disarm sets motor output to zero immediately and defers sound playback for 120 ms

**Step 2: Run focused tests**
Run: `pytest tests/test_main.py -q`
Expected: PASS

### Task 3: Verify full repository

**Files:**
- Test: `tests/test_main.py`
- Test: repository-wide

**Step 1: Run full suite**
Run: `pytest -q`
Expected: PASS
