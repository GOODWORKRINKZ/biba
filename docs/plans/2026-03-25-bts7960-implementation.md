# BTS7960 Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add configurable dual-BTS7960 motor driver support without breaking the existing PWM+DIR path.

**Architecture:** Keep `DifferentialDrive` unchanged and add a dedicated BTS7960 motor driver class behind the same `set_speed`/`stop` interface. Select between motor driver implementations in `main.py` using configuration.

**Tech Stack:** Python 3.11, pigpio, pytest, Docker Compose

---

### Task 1: Add failing BTS7960 motor tests

**Files:**
- Modify: `tests/test_motors.py`

**Step 1: Write the failing test**

Add tests for BTS7960 initialization, forward output, reverse output, stop output, and inversion.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motors.py -v`

**Step 3: Write minimal implementation**

Add `BTS7960MotorDriver` in `biba-controller/motors/driver.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motors.py -v`

### Task 2: Add driver-type configuration support

**Files:**
- Modify: `biba-controller/config.py`
- Modify: `tests/test_config.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Step 1: Write the failing test**

Add config tests for `MOTOR_DRIVER_TYPE` and BTS7960 pin overrides.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`

**Step 3: Write minimal implementation**

Add new env-backed config variables and expose them in compose/env example.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`

### Task 3: Select the correct motor driver in runtime

**Files:**
- Modify: `biba-controller/main.py`
- Modify: `tests/test_main.py`

**Step 1: Write the failing test**

Add runtime selection coverage for BTS7960 creation path.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`

**Step 3: Write minimal implementation**

Create motors from config-selected driver type and keep the drive interface unchanged.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -v`

### Task 4: Update docs for BTS7960 wiring

**Files:**
- Modify: `docs/wiring.md`
- Modify: `README.md`
- Modify: `docs/deployment.md`

**Step 1: Update wiring docs**

Describe the BTS7960 default mapping and the meaning of the new env vars.

**Step 2: Verify docs are consistent**

Check paths and variable names match code and compose.

### Task 5: Run focused verification

**Files:**
- Test: `tests/test_motors.py`
- Test: `tests/test_config.py`
- Test: `tests/test_main.py`

**Step 1: Run targeted tests**

Run: `pytest tests/test_motors.py tests/test_config.py tests/test_main.py -v`

**Step 2: Run full test suite if targeted tests pass**

Run: `pytest -v`

**Step 3: Summarize follow-up hardware actions**

Document that physical pin wiring may still be overridden via env vars if the bench rig differs from defaults.