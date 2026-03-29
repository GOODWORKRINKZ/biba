# RC Mute Channel and Lua Status Icons Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a mute RC channel that suppresses ordinary sounds while preserving SOS playback, and expose local app-switch badges plus a charging lightning badge in the Lua telemetry header.

**Architecture:** Keep runtime sound suppression in `main.py` behind small helper functions so the control loop remains readable and the mute policy is centralized. Preserve the existing battery direction bitmask for charging, but render UI badges from two sources in Lua: local transmitter channels for `a/m/b`, and battery direction bits for the charging lightning badge. Draw each active badge as its own small rounded rectangle immediately after `BiBa`, leaving right-aligned quality/source text unchanged.

**Tech Stack:** Python 3.10, pytest, CRSF telemetry helpers, EdgeTX Lua telemetry script.

---

### Task 1: Add config and runtime mute tests

**Files:**
- Modify: `tests/test_main.py`
- Modify: `tests/test_config.py`

**Step 1: Write the failing test**

Add focused tests for:
- `config.CH_MUTE` defaulting to `6`
- muted grouped voice playback being skipped
- muted named melody playback being skipped
- `buzzer.sos_beacon()` still running when beacon logic requests SOS

Use small fake buzzer classes and short frame sequences rather than broad integration mocks.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py tests/test_config.py -q -k "mute or CH_MUTE or sos"`

Expected: FAIL because mute config and runtime gating do not exist yet.

**Step 3: Write minimal implementation**

In `biba-controller/config.py`, add `CH_MUTE = _get_env_int("CH_MUTE", 6)`.

In `biba-controller/main.py`:
- add `_is_muted(channels)` or equivalent helper
- add mute-aware wrappers for grouped voice / async buzzer-method / named melody playback
- thread `mute_active` through startup and loop event sound sites
- leave `buzzer.sos_beacon()` untouched

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py tests/test_config.py -q -k "mute or CH_MUTE or sos"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 2: Add failing status-bit telemetry tests

**Files:**
- Modify: `tests/test_main.py`
- Modify: `tests/test_telemetry.py`

**Step 1: Write the failing test**

Add tests proving:
- battery direction remains encoded in the low bits
- armed, mute, and beacon states set their own bits
- `send_battery()` still packs the capacity field verbatim into the CRSF battery payload

Keep the tests narrow by asserting on exact packed bytes or decoded integers.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py tests/test_telemetry.py -q -k "battery telemetry or status bit or mute"`

Expected: FAIL because `_send_battery_telemetry()` still sends only a plain direction code.

**Step 3: Write minimal implementation**

In `biba-controller/main.py`:
- add helpers to build the battery-status bitmask from battery direction, `armed`, `mute_active`, and manual beacon state
- update `_send_battery_telemetry(...)` call sites to pass the composed flags

In `biba-controller/crsf/telemetry.py`:
- keep packing logic unchanged except for any naming or helper cleanup needed by the new tests

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py tests/test_telemetry.py -q -k "battery telemetry or status bit or mute"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 3: Add failing Lua local-badge and charging-lightning tests

**Files:**
- Modify: `tests/test_lua_telemetry_screen.py`
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`

**Step 1: Write the failing test**

Add assertions that:
- Lua masks low bits when decoding battery direction
- Lua exposes a helper that reads the local app switch channels for `a/m/b`
- compact and wide headers draw per-badge rounded rectangles after `BiBa`
- charging is rendered with a lightning helper instead of a text glyph
- compact and wide body layouts stop rendering `CHG/DIS` text next to current values

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -q -k "status or header or battery_direction"`

Expected: FAIL because Lua currently right-aligns a concatenated status string and does not draw channel-based badges or a lightning glyph.

**Step 3: Write minimal implementation**

Update `lua/SCRIPTS/TELEMETRY/biba.lua` to:
- add local app-channel badge helpers for arm, mute, and beacon
- mask the low bits in `read_battery_direction()`
- add a small lightning draw helper for charging
- pass badge data into `draw_header()` and `draw_header_wide()`
- render one rounded-rectangle badge per active icon immediately after `BiBa`
- remove body rendering of `CHG/DIS`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_lua_telemetry_screen.py -q -k "status or header or battery_direction"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 4: Update docs and config surface tests

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `docs/deployment.md`
- Modify: `tests/test_config.py`

**Step 1: Write the failing test**

Add or update config-surface tests so they require `CH_MUTE` to appear in the example env and compose defaults.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -q -k "CH_MUTE or mute"`

Expected: FAIL because the deployment surface does not mention the new variable.

**Step 3: Write minimal implementation**

Add `CH_MUTE` to the env example, compose environment, and the operator-facing documentation sections that describe RC channel mapping.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -q -k "CH_MUTE or mute"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 5: Run regression verification

**Files:**
- Test: `tests/test_main.py`
- Test: `tests/test_telemetry.py`
- Test: `tests/test_lua_telemetry_screen.py`
- Test: `tests/test_config.py`

**Step 1: Run focused regression slice**

Run: `pytest tests/test_main.py tests/test_telemetry.py tests/test_lua_telemetry_screen.py tests/test_config.py -q`

Expected: PASS.

**Step 2: Run full test suite**

Run: `pytest -q`

Expected: PASS.

**Step 3: Review git diff**

Run: `git diff --stat`

Expected: only feature-relevant files changed.

**Step 4: Commit**

Do not commit unless explicitly requested.