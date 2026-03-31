# Disarm Synth Audibility Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the synth `disarm` event more audible and playful by rewriting only the `disarm` melody as a descending companion to `arm`.

**Architecture:** Keep the current synth playback pipeline untouched and change only the `disarm` catalog entries in `melodies.py`. Validate the new phrase through tests first, then update the melody, run focused regressions, and deploy through the normal BiBa update path.

**Tech Stack:** Python 3.10, pytest, pigpio-backed synth playback, BLHeli melody parser, Docker Compose deployment on the robot.

---

### Task 1: Add failing expectations for the new disarm phrase

**Files:**
- Modify: `tests/test_buzzer.py`
- Test: `tests/test_buzzer.py`

**Step 1: Write the failing test**

Add or update a focused test that asserts the `disarm` mono and split BLHeli entries are short descending responses that stay near the `arm` energy profile.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_buzzer.py -k disarm -q`
Expected: FAIL because the current `disarm` melody still uses the old weaker phrase.

**Step 3: Write minimal implementation**

Do not change implementation in this task.

**Step 4: Run test to verify it fails correctly**

Run: `python -m pytest tests/test_buzzer.py -k disarm -q`
Expected: FAIL on the exact melody expectation, not because of parser or syntax errors.

**Step 5: Commit**

Do not commit yet.

### Task 2: Rewrite the disarm melody in the catalog

**Files:**
- Modify: `biba-controller/buzzer/melodies.py`
- Test: `tests/test_buzzer.py`

**Step 1: Write the minimal implementation**

Replace only the `disarm` entries in `BLHELI_CATALOG` and `SPLIT_BLHELI_CATALOG` with the approved descending companion phrase.

**Step 2: Run focused tests**

Run: `python -m pytest tests/test_buzzer.py -k disarm -q`
Expected: PASS.

**Step 3: Check parseability and range safety**

Run: `python -m pytest tests/test_buzzer.py -q`
Expected: PASS.

**Step 4: Commit**

Do not commit yet.

### Task 3: Run synth regressions

**Files:**
- Test: `tests/test_motor_synth.py`
- Test: `tests/test_main.py`

**Step 1: Run targeted synth tests**

Run: `python -m pytest tests/test_motor_synth.py -q`
Expected: PASS.

**Step 2: Run broader affected regression**

Run: `python -m pytest tests/test_buzzer.py tests/test_motor_synth.py tests/test_main.py -q`
Expected: PASS.

**Step 3: Investigate only if regressions fail**

If something fails, fix only behavior directly caused by the melody rewrite.

### Task 4: Deploy the validated change

**Files:**
- Verify: `docker-compose.yml`
- Verify runtime on robot

**Step 1: Run final local verification**

Run: `python -m pytest tests/test_buzzer.py tests/test_motor_synth.py tests/test_main.py -q`
Expected: PASS.

**Step 2: Commit the change**

Use a focused commit message such as `feat: retune disarm synth phrase`.

**Step 3: Push and wait for CI**

Wait for the relevant GitHub Actions runs to succeed.

**Step 4: Deploy through the normal robot workflow**

Run the robot-side `bbupdate` alias and verify the container becomes healthy.

**Step 5: Confirm runtime state**

Verify:

- deployed git revision
- healthy controller container
- `SOUND_MODE=synth`
- `BTS7960_PWM_MODE=SOFTWARE`

**Step 6: Hardware validation**

Listen to the real `disarm` event and compare it directly against `arm`.