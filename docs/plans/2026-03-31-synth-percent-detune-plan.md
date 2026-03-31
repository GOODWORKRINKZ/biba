# Synth Percent Detune Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the fixed absolute software synth detune with a percentage-based detune for all synth playback and deploy the verified change to the robot.

**Architecture:** Keep the existing synth routing intact but change the detune helper to compute a delta from `20%` of the requested frequency, protected by a small minimum floor. Update the synth tests to lock down the new detune pairs, then verify the whole repo and deploy through GitHub Actions plus `bbupdate`.

**Tech Stack:** Python, pigpio, pytest, unittest.mock.

---

### Task 1: Update detune expectations in tests

**Files:**
- Modify: `tests/test_motor_synth.py`

**Step 1:** Change the mono software synth expectations from fixed-80 detune pairs to percentage-based pairs.

**Step 2:** Change the split software synth expectations to the new percentage-based pairs.

**Step 3:** Update any restore-state assertion that still assumes the old fixed detune values.

**Step 4:** Run focused synth tests to verify they fail for the old implementation.

### Task 2: Implement percentage detune

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`

**Step 1:** Replace the fixed detune constant with a percentage constant and a minimum floor.

**Step 2:** Update the detune helper to calculate the delta from the center frequency.

**Step 3:** Keep the result symmetric and integer-safe for forward/reverse pin pairs.

**Step 4:** Run the focused synth tests to verify the new implementation passes.

### Task 3: Verify, push, and deploy

**Files:**
- No additional source files expected unless regressions surface

**Step 1:** Run full `pytest -q`.

**Step 2:** Commit the verified change.

**Step 3:** Push the revision to GitHub.

**Step 4:** Wait for the controller image workflows to complete successfully.

**Step 5:** Deploy to the robot with `bbupdate`.

**Step 6:** Verify robot health, deployed revision, and runtime environment.