# Lua Speed Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a three-position `ch6` speed selector to the controller runtime, scale only the robot-side throttle and steering command by `1/3`, `2/3`, or `1.0`, and show the active speed number in the Lua status badge row.

**Architecture:** Add small controller-side config and helper logic so the main loop reads `ch6`, derives a scale, and applies it to throttle and steering before `drive.mix_and_ramp(...)`. Keep the Lua script responsible only for mode display by appending the active speed number to the existing local status badge list.

**Tech Stack:** Python controller runtime, Lua telemetry script, pytest string-structure and controller behavior tests.

---

### Task 1: Add failing controller and config tests for speed mode settings

**Files:**
- Modify: `tests/test_config.py`
- Modify: `tests/test_main.py`
- Test: `biba-controller/config.py`
- Test: `biba-controller/main.py`

**Step 1: Write the failing test**

Add tests that assert controller config declares:

- `CH_SPEED_MODE = 5`
- `SPEED_MODE_SLOW_SCALE`
- `SPEED_MODE_MEDIUM_SCALE`
- `SPEED_MODE_FAST_SCALE`
- `SPEED_MODE_LOW_THRESHOLD`
- `SPEED_MODE_HIGH_THRESHOLD`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py tests/test_main.py -q`

Expected: FAIL because the speed-mode config and controller helper do not exist yet.

**Step 3: Commit**

Do not commit yet.

### Task 2: Add failing Lua badge tests without Lua-side scaling

**Files:**
- Modify: `tests/test_lua_telemetry_screen.py`
- Test: `lua/SCRIPTS/TELEMETRY/biba.lua`

**Step 1: Write the failing test**

Add tests asserting that:

- a helper such as `read_speed_mode()` exists
- it reads `sensor(APP_SPEED_MODE_CHANNEL, 0)`
- it returns speed labels or values covering `1`, `2`, and `3`
- `read_local_status_badges()` appends the speed badge
- `read_drive()` keeps raw stick normalization instead of duplicating controller-side scaling

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q`

Expected: FAIL because the helper and speed badge behavior do not exist yet.

### Task 3: Implement speed-mode config and helper in controller

**Files:**
- Modify: `biba-controller/config.py`
- Modify: `biba-controller/main.py`
- Test: `tests/test_config.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**

Add the new controller config values and a small helper that maps the selector channel to the requested scale.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py tests/test_main.py -q`

Expected: some tests should still fail because the main loop is not using the scale yet.

### Task 4: Apply controller-side scaling in the main loop

**Files:**
- Modify: `biba-controller/main.py`
- Test: `tests/test_main.py`

**Step 1: Write minimal implementation**

Update the controller main loop so the selected scale is applied to filtered throttle and steering before the drive mix.

**Step 2: Run focused test**

Run: `pytest tests/test_main.py -q`

Expected: controller speed-mode tests should pass.

### Task 5: Keep Lua responsible only for badge display

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write minimal implementation**

Keep `read_speed_mode()` and the speed badge, but revert `read_drive()` to raw operator-input normalization so Lua does not duplicate controller-side limiting.

**Step 2: Run focused test**

Run: `pytest tests/test_lua_telemetry_screen.py -q`

Expected: PASS for the focused Lua telemetry test file.

### Task 6: Expose speed-mode env defaults in deployment config

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/test_config.py`

**Step 1: Write minimal implementation**

Add `CH_SPEED_MODE`, thresholds, and scale variables to compose, `.env.example`, and the README environment list.

**Step 2: Run focused test**

Run: `pytest tests/test_config.py -q`

Expected: PASS.

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
- only controller-side stick command is scaled
- trim behavior remains untouched
- the active speed appears in the status badge row

**Step 2: Commit**

Run:

```bash
git add lua/SCRIPTS/TELEMETRY/biba.lua tests/test_lua_telemetry_screen.py docs/plans/2026-04-01-lua-speed-mode-design.md docs/plans/2026-04-01-lua-speed-mode-plan.md
git commit -m "feat: add Lua speed mode selector"
```

Expected: one focused commit containing Lua behavior, tests, and docs.