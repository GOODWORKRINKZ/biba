# Wheel Current Telemetry Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a clean BIBA wheel-current telemetry contract so controller and Lua UI code use canonical left and right wheel-current values instead of raw CRSF carrier fields.

**Architecture:** Add a small controller-side domain layer that converts wheel current into canonical `mA` values, route CRSF carrier encoding through a dedicated transport adapter, and add a Lua-side BIBA sensor adapter so screen rendering and telemetry logging consume only normalized BIBA semantics. Keep the first iteration compatible with the current GPS-based CRSF carrier mapping while isolating all carrier-specific quirks to the adapter layers.

**Tech Stack:** Python 3.10, pytest, CRSF telemetry encoding, Lua telemetry screen script, existing BIBA controller main loop.

---

### Task 1: Lock the canonical wheel-current contract in Python tests

**Files:**
- Modify: `tests/test_telemetry.py`
- Modify: `biba-controller/crsf/telemetry.py`

**Step 1: Write the failing test**

Add focused tests for a new controller-side canonical representation that proves:

- left and right wheel-current values are represented in `mA`
- identical amp inputs produce identical canonical `mA` outputs
- no CRSF carrier offset exists in the canonical representation

Example test shape:

```python
def test_build_biba_system_metrics_uses_symmetric_wheel_current_ma() -> None:
    metrics = build_biba_system_metrics(
        cpu_percent=11.0,
        memory_percent=22.0,
        left_motor_current_a=1.234,
        right_motor_current_a=1.234,
    )

    assert metrics.left_wheel_current_ma == 1234
    assert metrics.right_wheel_current_ma == 1234
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_telemetry.py -q -k "wheel_current or system_metrics"`

Expected: FAIL because no canonical BIBA telemetry representation exists yet.

**Step 3: Write minimal implementation**

In `biba-controller/crsf/telemetry.py`:

- add a small canonical telemetry data structure or helper for BIBA system metrics
- convert left and right wheel current from amps to `mA`
- centralize rounding and clamping rules

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_telemetry.py -q -k "wheel_current or system_metrics"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 2: Move CRSF carrier quirks behind a dedicated Python adapter

**Files:**
- Modify: `tests/test_telemetry.py`
- Modify: `biba-controller/crsf/telemetry.py`
- Modify: `biba-controller/main.py`

**Step 1: Write the failing test**

Add tests proving:

- canonical left wheel current is encoded into the chosen carrier field by the adapter
- canonical right wheel current is encoded into the chosen carrier field by the adapter
- any right-side altitude offset is applied only during transport encoding

Example test shape:

```python
def test_send_system_stats_encodes_transport_from_canonical_metrics() -> None:
    telemetry = CRSFTelemetry(FakeSerial())
    metrics = BIBASystemMetrics(
        cpu_percent=30,
        memory_percent=40,
        left_wheel_current_ma=1500,
        right_wheel_current_ma=2700,
    )

    telemetry.send_system_stats(metrics)

    # Assert encoded GPS payload fields match the current carrier contract.
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_telemetry.py -q -k "encodes_transport or gps"`

Expected: FAIL because transport encoding is not isolated from semantic value construction today.

**Step 3: Write minimal implementation**

In `biba-controller/crsf/telemetry.py` and `biba-controller/main.py`:

- change the telemetry send path to accept canonical BIBA metrics
- keep the current CRSF GPS carrier mapping, but isolate it in one encoding function
- keep existing external behavior compatible

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_telemetry.py -q -k "encodes_transport or gps"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 3: Add Lua adapter tests for canonical wheel-current reads

**Files:**
- Modify: `tests/test_lua_telemetry_screen.py`
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`

**Step 1: Write the failing test**

Add tests that require the Lua script to expose adapter functions for wheel current and system stats, and verify that those functions normalize carrier values before returning them.

Example test targets:

- `read_left_wheel_current_ma()` exists
- `read_right_wheel_current_ma()` exists
- the adapter normalizes the right-side carrier-specific offset
- UI-oriented helpers no longer need raw `Alt` or `Hdg` semantics

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_lua_telemetry_screen.py -q -k "wheel_current or adapter"`

Expected: FAIL because the Lua script currently reads raw carrier fields directly.

**Step 3: Write minimal implementation**

In `lua/SCRIPTS/TELEMETRY/biba.lua`:

- add narrow BIBA adapter functions for left and right wheel current
- normalize the current carrier values to canonical `mA`
- keep raw sensor access confined to the adapter section

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_lua_telemetry_screen.py -q -k "wheel_current or adapter"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 4: Refactor Lua UI and logging to consume only canonical adapter values

**Files:**
- Modify: `tests/test_lua_telemetry_screen.py`
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`

**Step 1: Write the failing test**

Add tests proving:

- wheel-current display logic uses the BIBA adapter helpers rather than direct carrier reads
- telemetry logging paths also use canonical wheel-current values
- left and right values are formatted identically in `mA`

Suggested assertions:

- screen helpers reference `read_left_wheel_current_ma()` and `read_right_wheel_current_ma()`
- direct `sensor("Hdg", 0)` and `sensor("Alt", 0)` reads are absent from UI-specific wheel-current code paths

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_lua_telemetry_screen.py -q -k "logging or display or current"`

Expected: FAIL because the current UI path still couples directly to carrier fields.

**Step 3: Write minimal implementation**

In `lua/SCRIPTS/TELEMETRY/biba.lua`:

- update current display helpers to use the new adapter-returned values
- update telemetry logging helpers to log canonical wheel-current values
- preserve existing screen behavior outside this cleanup

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_lua_telemetry_screen.py -q -k "logging or display or current"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 5: Add regression coverage for compatibility and safe fallback behavior

**Files:**
- Modify: `tests/test_telemetry.py`
- Modify: `tests/test_lua_telemetry_screen.py`
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Modify: `biba-controller/crsf/telemetry.py`

**Step 1: Write the failing test**

Add regression tests proving:

- current CRSF carrier compatibility remains unchanged externally
- missing or invalid wheel-current carrier values degrade to `0 mA`
- no mixed-unit or offset-leaking behavior reaches the UI layer

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_telemetry.py tests/test_lua_telemetry_screen.py -q -k "fallback or compatibility or current"`

Expected: FAIL if fallback behavior or compatibility handling is incomplete.

**Step 3: Write minimal implementation**

Adjust the Python and Lua adapter code so:

- carrier compatibility stays intact
- decoding failures return safe defaults
- transport offsets cannot leak past the adapter boundary

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_telemetry.py tests/test_lua_telemetry_screen.py -q -k "fallback or compatibility or current"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 6: Document the new semantic boundary

**Files:**
- Modify: `README.md`
- Modify: `docs/telemetry-investigation-2026-03-28.md` if it references the old wheel-current interpretation directly

**Step 1: Write the failing documentation check**

Review the docs for statements that still imply the UI directly consumes wheel current from raw `Hdg` and `Alt` semantics.

Expected finding: existing docs may describe the old transport detail as if it were the semantic contract.

**Step 2: Update the docs**

Document that:

- BIBA now treats left and right wheel current as canonical semantic values
- CRSF carrier mapping is a compatibility detail, not the domain contract
- the Lua screen reads normalized BIBA values rather than raw carrier meaning

**Step 3: Run focused verification**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_telemetry.py tests/test_lua_telemetry_screen.py -q`

Expected: PASS.

**Step 4: Commit**

Do not commit unless explicitly requested.