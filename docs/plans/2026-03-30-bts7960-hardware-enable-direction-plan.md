# BTS7960 Hardware PWM Enable-Direction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the BTS7960 hardware-PWM path so the current robot wiring works in `HARDWARE` mode by using `REN` and `LEN` as direction selectors and shared hardware PWM for duty.

**Architecture:** Keep `DifferentialDrive` and `SpeedRamp` unchanged. Update only the BTS7960 hardware-mode pin semantics: both PWM pins get the same hardware duty, while `REN/LEN` decide forward, reverse, or zero. Software mode remains as-is for compatibility and tests.

**Tech Stack:** Python, pytest, pigpio, Docker Compose, Markdown docs

---

### Task 1: Lock in new hardware semantics with failing tests

**Files:**
- Modify: `tests/test_motors.py`

**Step 1: Write the failing test**

Update the hardware-mode BTS7960 tests to expect:

```python
driver.set_speed(0.5)
assert pi.hardware_pwm_calls[-2:] == [(18, 20000, 500000), (13, 20000, 500000)]
assert pi.write_calls[-2:] == [(23, 1), (24, 0)]
```

Add matching expectations for reverse and stop.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motors.py -q`
Expected: FAIL because the current hardware path still drives `RPWM` and `LPWM` independently and keeps both enable pins high.

**Step 3: Write minimal implementation**

Change only the BTS7960 hardware mode implementation in `biba-controller/motors/driver.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motors.py -q`
Expected: PASS

### Task 2: Restore hardware mode as the default configuration

**Files:**
- Modify: `biba-controller/config.py`
- Modify: `tests/test_config.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Step 1: Write the failing test**

Update config expectations back to:

```python
assert module.BTS7960_PWM_MODE == "HARDWARE"
```

and equivalent compose/env assertions.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -q`
Expected: FAIL because local fallback edits still set the default to `SOFTWARE`.

**Step 3: Write minimal implementation**

Restore `HARDWARE` defaults in runtime and deployment config.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -q`
Expected: PASS

### Task 3: Update docs to match the new driver model

**Files:**
- Modify: `docs/deployment.md`
- Modify: `docs/wiring.md`

**Step 1: Review the mismatch**

Current docs describe the current wiring as incompatible with BTS7960 hardware mode.

**Step 2: Write minimal implementation**

Document that:

- movement uses `BTS7960_PWM_MODE=HARDWARE`
- the hardware path now uses `REN/LEN` for direction
- ramping still controls smooth stop and reversal above the driver layer

**Step 3: Run verification**

Compare docs against final behavior in `biba-controller/motors/driver.py` and config defaults.
Expected: no stale `SOFTWARE` recommendation remains for the current robot wiring.

### Task 4: Run focused regression verification

**Files:**
- Test: `tests/test_motors.py`
- Test: `tests/test_ramping.py`
- Test: `tests/test_config.py`
- Test: `tests/test_main.py`
- Test: `tests/test_main_voice_audition.py`
- Test: `tests/test_motor_synth.py`

**Step 1: Run focused verification**

Run: `pytest tests/test_motors.py tests/test_ramping.py tests/test_config.py tests/test_main.py tests/test_main_voice_audition.py tests/test_motor_synth.py -q`

**Step 2: Confirm results**

Expected: PASS, with hardware-mode tests covering the new low-level semantics and no regressions in ramping or motor-synth setup.