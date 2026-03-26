# Daly BMS over BLE — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a BLE transport for Daly BMS telemetry while preserving UART as a runtime-selectable fallback.

**Architecture:** Introduce a transport boundary around BMS access, keep the current UART parser logic as the baseline implementation, add a BLE-backed implementation using a tiny client adapter, and switch `main.py` to a config-driven BMS factory.

**Tech Stack:** Python 3.10, pytest, pyserial, bleak, Docker Compose

---

### Task 1: Add transport selection tests

**Files:**
- Modify: `tests/test_main.py`
- Create or Modify: `tests/test_config.py`

**Step 1: Write the failing tests**

Add tests covering:

- `config.BMS_TRANSPORT` defaults to `UART`
- invalid `BMS_TRANSPORT` falls back to `UART`
- `main._create_bms()` returns UART implementation for `UART`
- `main._create_bms()` returns BLE implementation for `BLE`

**Step 2: Run test to verify it fails**

Run: `/home/builder/biba/.venv/bin/python -m pytest tests/test_config.py tests/test_main.py -q`
Expected: FAIL because transport config and factory do not exist yet.

**Step 3: Write minimal implementation**

Add `BMS_TRANSPORT` and BLE env settings in `config.py`. Add a small `_create_bms()` helper in `main.py`.

**Step 4: Run test to verify it passes**

Run: `/home/builder/biba/.venv/bin/python -m pytest tests/test_config.py tests/test_main.py -q`
Expected: PASS for the new cases.

### Task 2: Add BLE transport unit tests

**Files:**
- Create: `tests/test_daly_ble.py`
- Modify: `biba-controller/bms/daly.py`

**Step 1: Write the failing tests**

Add tests for:

- BLE `open()` wires notifications before requests
- sending a command writes the Daly frame and returns the matching 13-byte response
- timeout returns `None`
- `read_state()` aggregates parsed telemetry the same way as UART

**Step 2: Run test to verify it fails**

Run: `/home/builder/biba/.venv/bin/python -m pytest tests/test_daly_ble.py -q`
Expected: FAIL because BLE implementation does not exist.

**Step 3: Write minimal implementation**

Add a BLE client protocol, a `Bleak` adapter, and `DalyBMSBle` that reuses frame parsing helpers.

**Step 4: Run test to verify it passes**

Run: `/home/builder/biba/.venv/bin/python -m pytest tests/test_daly_ble.py tests/test_daly.py -q`
Expected: PASS.

### Task 3: Integrate BLE transport into runtime

**Files:**
- Modify: `biba-controller/main.py`
- Modify: `tests/test_main.py`

**Step 1: Write the failing tests**

Add a test proving `main()` attempts BLE startup when configured and still returns `0` if BLE startup fails.

**Step 2: Run test to verify it fails**

Run: `/home/builder/biba/.venv/bin/python -m pytest tests/test_main.py -q`
Expected: FAIL until `main()` uses the transport factory.

**Step 3: Write minimal implementation**

Switch `main()` from direct `DalyBMS(...)` creation to `_create_bms()`.

**Step 4: Run test to verify it passes**

Run: `/home/builder/biba/.venv/bin/python -m pytest tests/test_main.py -q`
Expected: PASS.

### Task 4: Update deployment config

**Files:**
- Modify: `biba-controller/config.py`
- Modify: `biba-controller/requirements.txt`
- Modify: `docker-compose.yml`
- Modify: `docs/deployment.md`

**Step 1: Write the failing verification target**

Define the expected runtime config:

- BLE env vars are available to the container
- Linux D-Bus socket is mounted for BlueZ-backed access
- `bleak` is installed in the controller image

**Step 2: Apply minimal config changes**

Update requirements, compose, and deployment docs.

**Step 3: Run targeted verification**

Run: `/home/builder/biba/.venv/bin/python -m pytest tests/test_config.py tests/test_main.py tests/test_daly.py tests/test_daly_ble.py -q`
Expected: PASS.

### Task 5: Final verification

**Files:**
- Review only

**Step 1: Run the focused test suite**

Run: `/home/builder/biba/.venv/bin/python -m pytest tests/test_config.py tests/test_main.py tests/test_daly.py tests/test_daly_ble.py -q`

**Step 2: Run repository-wide battery-related tests if fast enough**

Run: `/home/builder/biba/.venv/bin/python -m pytest tests/test_bms_poller.py tests/test_telemetry.py -q`

**Step 3: Summarize deployment delta**

Document which env vars need to change on the robot to activate BLE.