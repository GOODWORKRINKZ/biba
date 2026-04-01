# Lua Speed Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a three-position `ch6` speed selector to the Lua telemetry script, scale only the displayed operator stick input by `1/3`, `2/3`, or `1.0`, and show the active speed number in the status badge row.

**Architecture:** Keep the change local to `lua/SCRIPTS/TELEMETRY/biba.lua` by introducing small helpers for speed-mode decoding and badge generation. Drive scaling happens in `read_drive()` before wheel mixing, while the active mode number is appended to the existing local status badge list so both compact and wide headers inherit the new indicator without layout rewrites.

**Tech Stack:** Lua for the EdgeTX telemetry script, pytest string-structure tests in Python.

---

### Task 1: Add failing Lua telemetry tests for speed mode constants

**Files:**
- Modify: `tests/test_lua_telemetry_screen.py`
- Test: `lua/SCRIPTS/TELEMETRY/biba.lua`

**Step 1: Write the failing test**

Add tests that assert the Lua source declares:

- `APP_SPEED_MODE_CHANNEL = "ch6"`
- `APP_SPEED_MODE_SLOW_SCALE`
- `APP_SPEED_MODE_MEDIUM_SCALE`
- `APP_SPEED_MODE_FAST_SCALE`
- `APP_SPEED_MODE_LOW_THRESHOLD`
- `APP_SPEED_MODE_HIGH_THRESHOLD`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q`

Expected: FAIL because the speed-mode constants are not declared yet.

**Step 3: Commit**

Do not commit yet.

### Task 2: Add failing tests for speed helper and badge behavior

**Files:**
- Modify: `tests/test_lua_telemetry_screen.py`
- Test: `lua/SCRIPTS/TELEMETRY/biba.lua`

**Step 1: Write the failing test**

Add tests asserting that:

- a helper such as `read_speed_mode()` exists
- it reads `sensor(APP_SPEED_MODE_CHANNEL, 0)`
- it returns speed labels or values covering `1`, `2`, and `3`
- it uses all three scales `1 / 3`, `2 / 3`, and `1.0`
- `read_local_status_badges()` appends the speed badge

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q`

Expected: FAIL because the helper and speed badge behavior do not exist yet.

### Task 3: Add failing tests for drive scaling shape

**Files:**
- Modify: `tests/test_lua_telemetry_screen.py`
- Test: `lua/SCRIPTS/TELEMETRY/biba.lua`

**Step 1: Write the failing test**

Add tests asserting that `read_drive()`:

- calls the new speed-mode helper
- scales `thr` before normalization
- scales `str` before normalization
- still performs the same left/right clamp-based wheel mix

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q`

Expected: FAIL because `read_drive()` still uses the raw full-range channels.

### Task 4: Implement speed-mode constants and helper in Lua

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write minimal implementation**

In `lua/SCRIPTS/TELEMETRY/biba.lua`, add:

- the new `APP_SPEED_MODE_*` constants near the other app-channel constants
- a helper that reads `ch6`, resolves speed `1`, `2`, or `3`, and returns both the speed number and the scale

Keep the implementation small and threshold-driven.

**Step 2: Run focused test**

Run: `pytest tests/test_lua_telemetry_screen.py -q`

Expected: some tests should still fail because `read_drive()` and the badge list are not updated yet.

### Task 5: Implement drive scaling in Lua

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write minimal implementation**

Update `read_drive()` to:

- fetch the active scale from the speed-mode helper
- multiply only `thr` and `str` by that scale
- preserve the existing normalization and clamp logic

Do not change unrelated wheel rendering code.

**Step 2: Run focused test**

Run: `pytest tests/test_lua_telemetry_screen.py -q`

Expected: the drive-scaling tests should now pass, while badge tests may still fail if the status row is not updated yet.

### Task 6: Add speed badge to the status row

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write minimal implementation**

Update `read_local_status_badges()` so it appends the active speed number badge after the existing local state badges.

The badge text should be `"1"`, `"2"`, or `"3"`.

**Step 2: Run focused test**

Run: `pytest tests/test_lua_telemetry_screen.py -q`

Expected: PASS for the focused Lua telemetry test file.

### Task 7: Run regression coverage for Lua-related behavior

**Files:**
- Test: `tests/test_lua_telemetry_screen.py`
- Test: `tests/test_main.py`
- Test: `tests/test_telemetry.py`

**Step 1: Run focused regression tests**

Run: `pytest tests/test_lua_telemetry_screen.py tests/test_main.py tests/test_telemetry.py -q`

Expected: PASS.

**Step 2: Run broader verification if focused tests are clean**

Run: `pytest -q`

Expected: PASS.

### Task 8: Prepare final review summary

**Files:**
- Modify: `docs/plans/2026-04-01-lua-speed-mode-design.md`
- Modify: `docs/plans/2026-04-01-lua-speed-mode-plan.md`

**Step 1: Confirm delivered behavior**

Summarize that:

- `ch6` selects speeds `1`, `2`, and `3`
- only stick input is scaled
- trim behavior remains untouched
- the active speed appears in the status badge row

**Step 2: Commit**

Run:

```bash
git add lua/SCRIPTS/TELEMETRY/biba.lua tests/test_lua_telemetry_screen.py docs/plans/2026-04-01-lua-speed-mode-design.md docs/plans/2026-04-01-lua-speed-mode-plan.md
git commit -m "feat: add Lua speed mode selector"
```

Expected: one focused commit containing Lua behavior, tests, and docs.