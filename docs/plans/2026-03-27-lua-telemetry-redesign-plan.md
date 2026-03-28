# Lua Telemetry Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the Lua telemetry screen so it matches the approved handset mockup, displays all required battery and system values, and shows total and wheel currents in milliamps.

**Architecture:** Keep the existing telemetry producers and sensor mappings intact, and concentrate the change inside `lua/SCRIPTS/TELEMETRY/biba.lua`. Add focused tests in `tests/test_lua_telemetry_screen.py` so the new layout, milliamps formatting, and wheel-direction behavior are protected before any manual radio-side verification.

**Tech Stack:** Lua telemetry widget for EdgeTX/OpenTX, existing CRSF telemetry mapping, Python pytest checks for source inspection.

---

### Task 1: Lock the approved screen contract in tests

**Files:**
- Modify: `tests/test_lua_telemetry_screen.py`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write the failing test**

```python
def test_draw_compact_formats_total_current_in_milliamps() -> None:
    body = _extract_function(_lua_source(), "draw_compact")
    assert "mA" in body


def test_draw_wide_formats_wheel_currents_in_milliamps() -> None:
    body = _extract_function(_lua_source(), "draw_wide")
    assert "mA" in body
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: FAIL because current layout still formats currents in amps.

**Step 3: Write minimal implementation**

Add assertions that define the new contract for:
- `mA` formatting
- presence of `RQly`/quality
- continued use of cell data and wheel-current fields

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_lua_telemetry_screen.py
git commit -m "test: lock telemetry screen redesign contract"
```

### Task 2: Add display-format helpers for the redesigned screen

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write the failing test**

```python
def test_lua_declares_current_format_helper() -> None:
    source = _lua_source()
    assert "format_current_ma" in source
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: FAIL because the helper does not exist.

**Step 3: Write minimal implementation**

Add small helpers in `biba.lua` for:
- converting amps to rounded milliamps
- formatting milliamps compactly for labels
- optionally formatting quality/status text consistently

Example:

```lua
local function to_ma(current_a)
  return math.floor((current_a or 0) * 1000 + 0.5)
end

local function format_current_ma(current_a)
  return string.format("%dmA", to_ma(current_a))
end
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add lua/SCRIPTS/TELEMETRY/biba.lua tests/test_lua_telemetry_screen.py
git commit -m "feat: add telemetry current formatting helpers"
```

### Task 3: Repair `run()` data flow before redesigning layout

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write the failing test**

```python
def test_run_calls_only_one_draw_branch_and_passes_motor_currents() -> None:
    body = _extract_function(_lua_source(), "run")
    assert "if sw() >= 212 and sh() >= 128 then" in body
    assert "draw_wide(voltage, current, pct, rssi, rqly, cell_src, cells, mn, mx, delta, left_spd, right_spd, cpu, ram, left_current, right_current)" in body
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: FAIL because `run()` currently contains mismatched draw calls.

**Step 3: Write minimal implementation**

Refactor `run()` so it:
- reads the same sensor set once
- applies battery holdoff once
- calls either `draw_wide(...)` or `draw_compact(...)`
- passes the full argument list to both branches

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add lua/SCRIPTS/TELEMETRY/biba.lua tests/test_lua_telemetry_screen.py
git commit -m "fix: normalize telemetry screen draw dispatch"
```

### Task 4: Rebuild the wheel renderer to match the approved sketch

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write the failing test**

```python
def test_draw_wheel_keeps_forward_and_reverse_branches() -> None:
    body = _extract_function(_lua_source(), "draw_wheel")
    assert "if spd > 0 then" in body
    assert "else" in body
```
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: FAIL if the renderer has not yet been updated to the new implementation contract.

**Step 3: Write minimal implementation**

Replace the current filled-bar wheel visual with a wheel shape closer to the approved mockup while preserving three direction states:
- idle
- forward
- reverse

Keep speed intensity tied to arrow count or another minimal scaling method that still resembles the sketch.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add lua/SCRIPTS/TELEMETRY/biba.lua tests/test_lua_telemetry_screen.py
git commit -m "feat: redraw telemetry wheel indicators"
```

### Task 5: Rebuild the compact telemetry layout

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write the failing test**

```python
def test_draw_compact_uses_quality_cells_and_milliamps() -> None:
    body = _extract_function(_lua_source(), "draw_compact")
    assert "rqly" in body.lower()
    assert "format_current_ma" in body
    assert "cells[i]" in body
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: FAIL because compact layout still follows the old structure.

**Step 3: Write minimal implementation**

Recompose `draw_compact()` so it shows:
- quality in the header
- pack voltage
- `SOC%`
- total current in `mA`
- `CPU%` and `RAM%`
- left and right wheel current in `mA`
- all six cells
- redesigned wheels on both sides

Drop or demote older secondary stats that no longer fit the approved screen.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add lua/SCRIPTS/TELEMETRY/biba.lua tests/test_lua_telemetry_screen.py
git commit -m "feat: redesign compact telemetry layout"
```

### Task 6: Rebuild the wide telemetry layout

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write the failing test**

```python
def test_draw_wide_uses_quality_cells_and_milliamps() -> None:
    body = _extract_function(_lua_source(), "draw_wide")
    assert "rqly" in body.lower()
    assert "format_current_ma" in body
    assert "C%d" in body or "cells[i]" in body
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: FAIL because wide layout still formats currents in amps and follows the old geometry.

**Step 3: Write minimal implementation**

Recompose `draw_wide()` to mirror the approved design with more breathing room:
- status line with quality
- primary battery block with pack voltage, `SOC%`, total current in `mA`
- dedicated block for all cell voltages
- system stats row
- wheel-current row or side labels in `mA`
- redesigned left/right wheel visuals

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add lua/SCRIPTS/TELEMETRY/biba.lua tests/test_lua_telemetry_screen.py
git commit -m "feat: redesign wide telemetry layout"
```

### Task 7: Verify the telemetry screen end to end

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Modify: `tests/test_lua_telemetry_screen.py`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write the failing test**

```python
def test_run_preserves_quality_and_motor_current_reads() -> None:
    body = _extract_function(_lua_source(), "run")
    assert "RQly" in body
    assert "read_motor_currents()" in body
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: FAIL if any redesign step dropped an essential read or draw field.

**Step 3: Write minimal implementation**

Do final cleanup so the screen remains stable across:
- connected startup holdoff
- battery fallback mode
- disconnected mode
- compact and wide resolutions

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add lua/SCRIPTS/TELEMETRY/biba.lua tests/test_lua_telemetry_screen.py
git commit -m "test: verify telemetry redesign stability"
```

### Task 8: Perform manual radio-side verification

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`

**Step 1: Prepare the verification checklist**

```text
1. Compact screen shows quality, all cells, pack voltage, CPU%, RAM%, total current mA, SOC%, left current mA, right current mA.
2. Wide screen shows the same set without overlapping text.
3. Wheels show no arrows at idle.
4. Wheels switch arrow direction correctly for forward and reverse.
5. Holdoff and no-link states remain readable.
```

**Step 2: Run the manual verification**

Run: inspect on EdgeTX/OpenTX hardware or emulator.
Expected: The rendered screen matches the approved sketch closely enough to read all mandatory values.

**Step 3: Make minimal final adjustments**

Tune positions, widths, and text abbreviations only where readability issues remain.

**Step 4: Re-run tests**

Run: `pytest tests/test_lua_telemetry_screen.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add lua/SCRIPTS/TELEMETRY/biba.lua tests/test_lua_telemetry_screen.py
git commit -m "feat: finalize telemetry screen redesign"
```