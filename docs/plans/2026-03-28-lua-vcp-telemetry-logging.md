# Lua VCP Telemetry Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add transmitter-side telemetry logging from the EdgeTX Lua telemetry screen over USB VCP when VCP is configured to `LUA`.

**Architecture:** Extend `lua/SCRIPTS/TELEMETRY/biba.lua` with a lightweight serial logger that writes compact snapshots of telemetry state through `serialWrite()`. Log both raw sensor readings and post-holdoff values so host-side captures can be matched against robot logs and the screen state the user actually sees.

**Tech Stack:** EdgeTX Lua telemetry script, pytest string-level regression tests.

---

### Task 1: Add failing regression tests

**Files:**
- Modify: `tests/test_lua_telemetry_screen.py`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write the failing test**

Add assertions that `biba.lua` declares a telemetry logging helper, configures Lua serial baud rate, and calls the logger from `run()`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -k serial -v`

Expected: FAIL because the Lua script does not yet contain serial logging helpers.

### Task 2: Implement minimal Lua VCP logger

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Add compact logging state and helpers**

Add constants for baud rate and log cadence, plus helpers to format cell lists and emit a single log line via `serialWrite()`.

**Step 2: Log telemetry snapshots from `run()`**

Capture raw values before holdoff, displayed values after holdoff, and emit a throttled line containing connection state, holdoff state, key battery values, and cell data.

**Step 3: Initialize Lua serial in `init()`**

Call `setSerialBaudrate(...)` once so VCP captures use a known rate.

### Task 3: Verify focused tests

**Files:**
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Run targeted tests**

Run: `pytest tests/test_lua_telemetry_screen.py -k serial -v`

Expected: PASS

**Step 2: Run full telemetry-screen test file**

Run: `pytest tests/test_lua_telemetry_screen.py -v`

Expected: PASS