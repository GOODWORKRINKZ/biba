# IMU Drive Modes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add BMI160/BMI166-backed `manual`, `stabilized`, and `heading_hold` drive modes selected by `CH7`, while keeping the existing manual path intact and observable.

**Architecture:** Add a dedicated IMU backend plus an assisted-drive wrapper above the existing differential-drive layer. `stabilized` uses a gyro-Z yaw-rate controller, and `heading_hold` reuses that inner loop with a short-horizon heading latch when steering returns to neutral.

**Tech Stack:** Python 3.10, `smbus2`, pytest, existing CRSF/Lua telemetry stack.

---

### Task 1: Add Config Surface

**Files:**
- Modify: `biba-controller/config.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Test: `tests/test_config.py`

Add controller config for drive-mode selection and IMU bring-up: `CH_DRIVE_MODE`, three-position thresholds, mode labels, IMU enable flag, I2C address, sample rate, stale timeout, bias calibration time, steering deadband, and controller gains.

### Task 2: Add IMU Backend

**Files:**
- Create: `biba-controller/imu/__init__.py`
- Create: `biba-controller/imu/bmi160.py`
- Test: `tests/test_bmi160.py`

Add a small IMU abstraction with a BMI160/BMI166-capable I2C backend, chip-ID validation, sample conversion, bias calibration support, and safe fallback behavior.

### Task 3: Add Assisted Controller

**Files:**
- Create: `biba-controller/motors/assisted_drive.py`
- Test: `tests/test_assisted_drive.py`

Implement `manual`, `stabilized`, and `heading_hold` drive logic above the existing `DifferentialDrive` mix/ramp layer, including steering deadband, reset rules, clamping, and stale-IMU fallback.

### Task 4: Integrate Main Loop

**Files:**
- Modify: `biba-controller/main.py`
- Test: `tests/test_main.py`

Create the IMU and assisted-drive objects during startup, parse `CH7` into drive modes, route drive requests through the assisted controller, and log enough IMU state to validate robot-side visibility.

### Task 5: Update Telemetry UI

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

Update the local status badge row to show the active drive mode and align the Lua-side transmitter channel mapping with the new `CH7` mode switch and `CH8` beacon switch.

### Task 6: Update Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/deployment.md`
- Modify: `docs/wiring.md`

Document CH7 mode switching, IMU wiring on I2C, the new environment variables, and the limitation that IMU-only heading hold is short-horizon and not true absolute vector hold.