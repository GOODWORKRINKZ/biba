# Telemetry Frame ID Log Correlation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a shared `frame_id` marker to robot-side and app-side diagnostics so battery telemetry samples can be correlated exactly across the CRSF link without changing the telemetry UI.

**Architecture:** The controller assigns a rolling `frame_id` to each battery telemetry sample and logs it when the sample is consumed and sent. The same `frame_id` is transmitted via a non-UI service telemetry path that Lua reads only for diagnostic logging, leaving existing battery telemetry semantics intact.

**Tech Stack:** Python controller, CRSF telemetry helpers, Lua telemetry script, pytest.

---

### Task 1: Confirm the transport slot for `frame_id`

**Files:**
- Modify: `biba-controller/crsf/telemetry.py`
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Reference: `biba-controller/main.py`

**Step 1: Identify the safest existing telemetry carrier**

Review the currently used CRSF battery and system-stat fields and pick a carrier for `frame_id` that will not change visible UI semantics.

**Step 2: Document the chosen mapping inline in the plan implementation notes**

State exactly which transmitted value will carry `frame_id` and which Lua sensor name will read it.

**Step 3: Re-check Lua references**

Run: `grep -nE "sensor\(|Hdg|Alt|GSpd|Sats|Curr|VFAS|Capa" lua/SCRIPTS/TELEMETRY/biba.lua`

Expected: confirm current field usage before assigning the new one.

**Step 4: Commit**

```bash
git add docs/plans/2026-03-28-telemetry-frame-id-log*.md
git commit -m "docs: plan telemetry frame id correlation"
```

### Task 2: Add controller-side `frame_id` generation and logging

**Files:**
- Modify: `biba-controller/main.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**

Add a focused test proving traced battery telemetry logs include a stable `frame_id` for both `consume` and `send` within the same sample.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -k frame_id -v`

Expected: FAIL because `frame_id` is not present yet.

**Step 3: Write minimal implementation**

Add a rolling counter for battery telemetry sends and include `frame_id` in the trace logs without changing current battery payload behavior.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -k frame_id -v`

Expected: PASS

**Step 5: Commit**

```bash
git add biba-controller/main.py tests/test_main.py
git commit -m "feat: add battery telemetry frame ids to controller logs"
```

### Task 3: Transmit `frame_id` over the chosen telemetry path

**Files:**
- Modify: `biba-controller/crsf/telemetry.py`
- Modify: `biba-controller/main.py`
- Test: `tests/test_telemetry.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing transport test**

Add or extend a test to prove the chosen CRSF helper writes the encoded `frame_id` as intended.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_telemetry.py tests/test_main.py -k frame_id -v`

Expected: FAIL because transport does not yet carry the marker.

**Step 3: Write minimal implementation**

Extend the telemetry helper and call path to encode the chosen `frame_id` transport without changing visible battery metrics.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_telemetry.py tests/test_main.py -k frame_id -v`

Expected: PASS

**Step 5: Commit**

```bash
git add biba-controller/crsf/telemetry.py biba-controller/main.py tests/test_telemetry.py tests/test_main.py
git commit -m "feat: transport battery telemetry frame ids"
```

### Task 4: Add Lua-side diagnostic logging for `frame_id`

**Files:**
- Modify: `lua/SCRIPTS/TELEMETRY/biba.lua`
- Test: `tests/test_lua_telemetry_screen.py`

**Step 1: Write the failing test**

Add a focused test for the Lua script behavior that reads the chosen sensor and exposes a diagnostic log message containing `frame_id` without altering displayed UI content.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_lua_telemetry_screen.py -k frame_id -v`

Expected: FAIL because Lua does not yet read or log the marker.

**Step 3: Write minimal implementation**

Add a helper to read the `frame_id` sensor and emit diagnostic logging only; do not draw it on screen.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_lua_telemetry_screen.py -k frame_id -v`

Expected: PASS

**Step 5: Commit**

```bash
git add lua/SCRIPTS/TELEMETRY/biba.lua tests/test_lua_telemetry_screen.py
git commit -m "feat: log telemetry frame ids in lua diagnostics"
```

### Task 5: Verify end-to-end behavior and update docs

**Files:**
- Modify: `README.md`
- Modify: `docs/deployment.md`
- Test: relevant existing tests

**Step 1: Update docs**

Document the purpose of `frame_id`, how to enable the diagnostics, and how to match robot logs against app-side logs.

**Step 2: Run focused verification**

Run: `pytest tests/test_main.py tests/test_telemetry.py tests/test_lua_telemetry_screen.py -v`

Expected: PASS

**Step 3: Run broader regression coverage**

Run: `pytest -q`

Expected: PASS

**Step 4: Commit**

```bash
git add README.md docs/deployment.md
git commit -m "docs: describe telemetry frame id diagnostics"
```

Plan complete and saved to `docs/plans/2026-03-28-telemetry-frame-id-log.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?