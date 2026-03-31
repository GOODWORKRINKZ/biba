# Motor Test API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a robot-side HTTP motor test endpoint and simple control page that independently drive left and right PWM frequency and duty for a bounded duration.

**Architecture:** Add a small standard-library HTTP module that owns request parsing, HTML serving, and a synchronous executor built around the existing `MotorSynth` split-output path. Integrate the server into `main.py` only when pigpio-backed motor audio is available, and expose configuration through existing env-driven config and compose settings.

**Tech Stack:** Python standard library `http.server`, existing `MotorSynth`, pytest, Docker Compose.

---

### Task 1: Add failing config tests

**Files:**
- Modify: `tests/test_config.py`
- Modify: `biba-controller/config.py`

**Step 1: Write the failing test**

Add tests asserting:

- motor test API is enabled by default
- default host is `0.0.0.0`
- default port is `8765`
- environment overrides are respected

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -q`
Expected: FAIL because motor test API config does not exist yet.

**Step 3: Write minimal implementation**

Add config values for enable flag, host, and port.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -q`
Expected: PASS.

### Task 2: Add failing motor test module tests

**Files:**
- Create: `tests/test_motor_test_api.py`
- Create: `biba-controller/motor_test_api.py`

**Step 1: Write the failing test**

Add tests for:

- payload validation success
- payload validation failure on out-of-range values
- duty percent conversion to `MotorSynth` duty range
- executor calls motor synth and always stops
- executor rejects concurrent activation

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_test_api.py -q`
Expected: FAIL because the module and behavior do not exist yet.

**Step 3: Write minimal implementation**

Implement:

- payload dataclass or equivalent parser
- executor with lock and `finally: synth.off()`
- helpers for HTML and JSON response data

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motor_test_api.py -q`
Expected: PASS.

### Task 3: Expose a public bounded split-output method on MotorSynth

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Modify: `tests/test_motor_synth.py`
- Test: `tests/test_motor_test_api.py`

**Step 1: Write the failing test**

Add a focused test proving a public method can apply independent left and right frequency/duty, wait for duration, and stop output.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_synth.py tests/test_motor_test_api.py -q`
Expected: FAIL because the public method does not exist.

**Step 3: Write minimal implementation**

Add one public `MotorSynth` method that wraps the existing split apply path and duration wait.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motor_synth.py tests/test_motor_test_api.py -q`
Expected: PASS.

### Task 4: Add failing main integration tests

**Files:**
- Modify: `tests/test_main.py`
- Modify: `biba-controller/main.py`

**Step 1: Write the failing test**

Add tests asserting:

- the HTTP server starts when pigpio-backed buzzer exists
- the server is not created in telemetry-only mode
- shutdown closes the motor test server cleanly

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -q`
Expected: FAIL because `main.py` does not create or shut down the server.

**Step 3: Write minimal implementation**

Wire the server into controller startup and cleanup.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -q`
Expected: PASS.

### Task 5: Add compose exposure and document runtime usage

**Files:**
- Modify: `docker-compose.yml`
- Modify: `README.md`

**Step 1: Write the minimal docs/config change**

Document the endpoint and publish the configured port from the controller service.

**Step 2: Verify compose syntax remains valid**

Run: `docker compose config`
Expected: valid rendered compose output.

### Task 6: Run focused regression coverage

**Files:**
- Test: `tests/test_config.py`
- Test: `tests/test_motor_test_api.py`
- Test: `tests/test_motor_synth.py`
- Test: `tests/test_main.py`

**Step 1: Run focused tests**

Run: `pytest tests/test_config.py tests/test_motor_test_api.py tests/test_motor_synth.py tests/test_main.py -q`
Expected: PASS.

**Step 2: Run broader suite if focused coverage is green**

Run: `pytest -q`
Expected: PASS.

### Task 7: Deploy through the robot update workflow

**Files:**
- No additional source changes expected

**Step 1: Push the branch revision to GitHub**

Push the implementation branch so GitHub Actions builds the updated controller image.

**Step 2: Wait for the relevant Actions run**

Use `gh run watch ... --exit-status` for the image-building workflow and confirm the revision matches the pushed commit.

**Step 3: Update the robot**

Run the robot-side `bbupdate` alias through interactive SSH.

**Step 4: Verify deployment**

Confirm:

- controller container is healthy
- robot repo HEAD matches the pushed revision
- published motor test port is reachable
- `/motor-test` loads and a short test command returns success