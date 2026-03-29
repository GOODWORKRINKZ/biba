# Motor Trim Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a persistent RC-driven trim mode that lets the operator tune left/right drivetrain balance from `CH9`, save it with a 5-second disarmed gesture, and display trim mode with a `t` badge on the Lua telemetry screen.

**Architecture:** Keep trim orchestration in [biba-controller/main.py](biba-controller/main.py): it owns gesture detection, persistence, live-vs-saved trim source selection, status-bit encoding, and final duty correction before motor output. Reuse the existing battery telemetry status-bit path for the UI by adding one trim-mode bit and teaching [lua/SCRIPTS/TELEMETRY/biba.lua](lua/SCRIPTS/TELEMETRY/biba.lua) to render a `t` badge when that bit is present.

**Tech Stack:** Python 3.10, pytest, JSON file persistence, CRSF battery telemetry status bits, EdgeTX Lua telemetry UI.

---

### Task 1: Lock trim math and status-bit behavior in tests

**Files:**
- Modify: `tests/test_main.py`

**Step 1: Write the failing test**

Add focused tests for:
- applying `0.0` trim leaves both duties unchanged
- positive trim reduces only the right duty
- negative trim reduces only the left duty
- trim values are bounded to a 20% maximum effect
- battery status bits preserve direction bits and add the trim-mode bit independently

Example test:

```python
def test_apply_trim_positive_reduces_only_right_side() -> None:
    main = importlib.import_module("main")

    left, right = main._apply_motor_trim(0.75, 0.75, 0.20)

    assert left == pytest.approx(0.75)
    assert right == pytest.approx(0.60)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest tests/test_main.py -q -k "trim or status_bits"`

Expected: FAIL because trim helpers and the trim-mode status bit do not exist yet.

**Step 3: Write minimal implementation**

In `biba-controller/main.py`:
- add trim constants or helper functions
- add `_apply_motor_trim(left_duty, right_duty, trim)`
- extend `_encode_battery_status_bits(...)` with `trim_mode_active`

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest tests/test_main.py -q -k "trim or status_bits"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 2: Add failing persistence tests for saved trim

**Files:**
- Modify: `tests/test_main.py`
- Modify: `tests/test_config.py`

**Step 1: Write the failing test**

Add tests proving:
- missing trim settings file returns `0.0`
- corrupt trim settings file logs a warning and returns `0.0`
- saving trim writes the effective trimmed value, not raw `CH9`
- config exposes defaults for trim path and max trim if those settings are added to config

Example test:

```python
def test_load_trim_defaults_to_zero_when_file_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "MOTOR_TRIM_SETTINGS_PATH", str(tmp_path / "trim.json"))

    assert main._load_saved_motor_trim() == 0.0
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest tests/test_main.py tests/test_config.py -q -k "trim and (load or save or settings or path)"`

Expected: FAIL because trim persistence helpers and config surface do not exist yet.

**Step 3: Write minimal implementation**

In `biba-controller/config.py`:
- add defaults for the trim settings path, channel index, confirmation hold duration, and max trim effect if needed

In `biba-controller/main.py`:
- add JSON load/save helpers for trim settings
- use atomic write via temp file plus rename

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest tests/test_main.py tests/test_config.py -q -k "trim and (load or save or settings or path)"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 3: Add failing trim-mode gesture tests

**Files:**
- Modify: `tests/test_main.py`

**Step 1: Write the failing test**

Add loop-level tests for:
- trim mode enters after 5 seconds with channels 1-4 high while disarmed
- trim mode uses live `CH9` during subsequent driving
- the same gesture in trim mode saves the current effective trim and exits trim mode

Build the tests using short fake receiver frame sequences and controlled monotonic timestamps.

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest tests/test_main.py -q -k "trim mode or ch9 or gesture"`

Expected: FAIL because the control loop has no trim mode state machine.

**Step 3: Write minimal implementation**

In `biba-controller/main.py`:
- detect the disarmed all-high gesture on channels 1-4
- start and clear the hold timer correctly
- switch between saved trim and live `CH9 * 0.20`
- persist and exit on confirmation
- log entry and save events for observability

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest tests/test_main.py -q -k "trim mode or ch9 or gesture"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 4: Add failing Lua trim badge tests

**Files:**
- Modify: `tests/test_lua_telemetry_screen.py`
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`

**Step 1: Write the failing test**

Add assertions that:
- Lua masks and reads the new trim-mode status bit
- the status-badge helper can append `t`
- compact and wide headers continue to use the shared badge helper after the new badge is added

Example assertion:

```python
def test_read_status_badges_adds_trim_mode_badge() -> None:
    body = _extract_function(_lua_source(), "read_robot_status_badges")

    assert 'badges[#badges + 1] = "t"' in body
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest tests/test_lua_telemetry_screen.py -q -k "trim or badge or status"`

Expected: FAIL because Lua does not know about the trim-mode status bit.

**Step 3: Write minimal implementation**

In `lua/SCRIPTS/TELEMETRY/biba.lua`:
- add a trim-mode status-bit constant
- read the robot-side status bits from the battery capacity field
- merge the robot-side `t` badge with the existing locally-derived `a/m/b` badges
- keep compact and wide header rendering routed through the same badge helper

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest tests/test_lua_telemetry_screen.py -q -k "trim or badge or status"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 5: Update operator-facing docs and deployment surface

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `docs/deployment.md`
- Modify: `tests/test_config.py`

**Step 1: Write the failing test**

Add or update config-surface tests so they require the trim-related environment variables to appear in the example env and compose defaults.

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest tests/test_config.py -q -k "trim and (env or compose or config)"`

Expected: FAIL because the deployment surface does not mention trim settings.

**Step 3: Write minimal implementation**

Document the trim channel, hold gesture, persistent settings path, and max trim effect in the env example, compose file, README, and deployment guide.

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest tests/test_config.py -q -k "trim and (env or compose or config)"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 6: Run regression verification

**Files:**
- Test: `tests/test_main.py`
- Test: `tests/test_lua_telemetry_screen.py`
- Test: `tests/test_config.py`
- Test: `tests/test_telemetry.py`

**Step 1: Run the focused regression slice**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest tests/test_main.py tests/test_lua_telemetry_screen.py tests/test_config.py tests/test_telemetry.py -q`

Expected: PASS.

**Step 2: Run the full suite**

Run: `cd /home/builder/biba/.worktrees/motor-trim && /home/builder/biba/.venv/bin/python -m pytest -q`

Expected: PASS.

**Step 3: Review the diff**

Run: `cd /home/builder/biba/.worktrees/motor-trim && git diff --stat`

Expected: only trim-feature files changed.

**Step 4: Commit**

Do not commit unless explicitly requested.