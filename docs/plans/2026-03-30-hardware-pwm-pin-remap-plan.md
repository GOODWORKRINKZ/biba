# Hardware PWM Pin Remap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update BiBa defaults and supporting docs/tests to match the robot's new dual-motor hardware PWM wiring.

**Architecture:** Keep the existing BTS7960 hardware-PWM implementation unchanged and remap only the default RPWM/LPWM assignments. Propagate the same mapping through config defaults, compose/env defaults, tests, and wiring documentation so all sources agree.

**Tech Stack:** Python, pytest, Docker Compose, Markdown docs

---

### Task 1: Lock in the new defaults with tests

**Files:**
- Modify: `tests/test_config.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_main_voice_audition.py`

**Step 1: Write the failing test**

Update existing assertions to expect:

```python
assert module.LEFT_MOTOR_RPWM == 12
assert module.LEFT_MOTOR_LPWM == 18
assert module.RIGHT_MOTOR_RPWM == 19
assert module.RIGHT_MOTOR_LPWM == 13
```

Update main-entry tests so mocked config values and expected synth groups match the same layout.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py tests/test_main.py tests/test_main_voice_audition.py -q`
Expected: FAIL because runtime defaults still use the previous pin mapping.

**Step 3: Write minimal implementation**

Change config and deployment defaults to the new wiring.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py tests/test_main.py tests/test_main_voice_audition.py -q`
Expected: PASS

### Task 2: Update runtime and deployment defaults

**Files:**
- Modify: `biba-controller/config.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Step 1: Write the failing test**

Use Task 1's updated assertions for compose/env-backed expectations.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -q`
Expected: FAIL on compose/env default pin assertions.

**Step 3: Write minimal implementation**

Set the defaults to:

```python
LEFT_MOTOR_RPWM = 12
LEFT_MOTOR_LPWM = 18
RIGHT_MOTOR_RPWM = 19
RIGHT_MOTOR_LPWM = 13
```

Mirror the same values in `docker-compose.yml` and `.env.example`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -q`
Expected: PASS

### Task 3: Update operator-facing wiring docs

**Files:**
- Modify: `docs/wiring.md`

**Step 1: Write the failing test**

No automated test exists; use manual doc consistency review against `config.py` and `docker-compose.yml`.

**Step 2: Run verification to confirm mismatch**

Review the current wiring table and runtime example; they still describe the old `18/13` and `12/19` layout.

**Step 3: Write minimal implementation**

Update the table and explanatory text to describe the new hardware-PWM-safe mapping and remove the stale statement that dual-motor hardware PWM is impossible with current wiring.

**Step 4: Run verification**

Compare `docs/wiring.md` with the final defaults in `config.py` and `docker-compose.yml`.
Expected: all three locations describe the same layout.

### Task 4: Run focused regression verification

**Files:**
- Test: `tests/test_config.py`
- Test: `tests/test_main.py`
- Test: `tests/test_main_voice_audition.py`
- Test: `tests/test_motor_synth.py`
- Test: `tests/test_motors.py`

**Step 1: Run focused verification**

Run: `pytest tests/test_config.py tests/test_main.py tests/test_main_voice_audition.py tests/test_motor_synth.py tests/test_motors.py -q`

**Step 2: Confirm results**

Expected: PASS, with no failures related to the new pin mapping.
