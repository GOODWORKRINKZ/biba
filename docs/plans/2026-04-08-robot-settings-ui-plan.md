# Robot Settings UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a real `/settings` frontend/backend inside the controller container that combines stabilized tuning, persistent motor trim, and the existing motor sound test workflow behind one operator-facing screen.

**Architecture:** Keep one Python backend in the controller runtime, move the UI into dedicated static assets, expose one aggregated `/api/settings` status endpoint plus per-section update endpoints, and keep the main loop as the only owner that applies control-affecting revisions from store objects.

**Tech Stack:** Python standard library `http.server`, existing controller runtime, pytest, static HTML/CSS/JS, SVG animation assets.

---

### Task 1: Add failing tests for persistent motor trim store behavior

**Files:**
- Create: `/home/builder/biba/tests/test_settings_store.py`
- Create: `/home/builder/biba/biba-controller/settings_store.py`
- Modify: `/home/builder/biba/biba-controller/main.py`

**Step 1: Write the failing test**

Add tests for:

- loading the saved trim from `MOTOR_TRIM_SETTINGS_PATH`
- disarmed-only trim update requests
- revision tracking for pending trim updates
- updating store state after an RC gesture save

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings_store.py -q`
Expected: FAIL because the store module does not exist.

**Step 3: Write minimal implementation**

Implement a `MotorTrimStore` with atomic persistence and runtime status metadata.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_settings_store.py -q`
Expected: PASS.

### Task 2: Add failing tests for the new settings frontend/backend surface

**Files:**
- Modify: `/home/builder/biba/tests/test_motor_test_api.py`
- Modify: `/home/builder/biba/biba-controller/motor_test_api.py`
- Create: `/home/builder/biba/biba-controller/web/settings.html`
- Create: `/home/builder/biba/biba-controller/web/settings.css`
- Create: `/home/builder/biba/biba-controller/web/settings.js`
- Create: `/home/builder/biba/biba-controller/web/biba-neon-sign.svg`

**Step 1: Write the failing test**

Add tests asserting:

- `GET /settings` serves the new page
- the page references external CSS, JS, and logo assets
- `GET /settings/assets/...` serves the static files
- `GET /api/settings` returns aggregated status including PID tuning, trim, and motor test status
- `POST /api/settings/motor-trim` updates trim while disarmed and rejects while armed
- `POST /api/settings/motor-test` preserves current executor behavior

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_test_api.py -q`
Expected: FAIL because the new settings routes and assets do not exist.

**Step 3: Write minimal implementation**

Refactor the backend to serve the new static frontend and JSON API while keeping compatibility aliases for the current routes.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motor_test_api.py -q`
Expected: PASS.

### Task 3: Add failing tests for main-loop trim store integration

**Files:**
- Modify: `/home/builder/biba/tests/test_main.py`
- Modify: `/home/builder/biba/biba-controller/main.py`

**Step 1: Write the failing test**

Add tests asserting:

- the controller starts with both PID tuning state and trim store state loaded
- pending trim revisions are applied only while disarmed
- RC gesture trim saves update the trim store current state
- aggregated settings backend gets access to both store objects

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -q -k 'trim_store or settings'`
Expected: FAIL because main does not yet own or update a trim store.

**Step 3: Write minimal implementation**

Wire trim store ownership into the main loop and expose it to the settings server.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -q -k 'trim_store or settings'`
Expected: PASS.

### Task 4: Replace the old inline UI with the new operator page

**Files:**
- Modify: `/home/builder/biba/biba-controller/motor_test_api.py`
- Modify: `/home/builder/biba/biba-controller/web/settings.html`
- Modify: `/home/builder/biba/biba-controller/web/settings.css`
- Modify: `/home/builder/biba/biba-controller/web/settings.js`
- Modify: `/home/builder/biba/biba-controller/web/biba-neon-sign.svg`

**Step 1: Build the page structure**

Implement:

- animated hero logo
- status strip
- stabilized tuning card
- motor trim card
- motor test card

**Step 2: Add operator interactions**

Implement:

- polling from `/api/settings`
- PID tuning submit
- trim submit
- motor test submit
- armed/disarmed button state and feedback

**Step 3: Keep compatibility**

Ensure `/motor-test`, `/pid-tuning`, and `/api/motor-test` still work or redirect safely.

**Step 4: Run focused tests**

Run: `pytest tests/test_motor_test_api.py -q`
Expected: PASS.

### Task 5: Update operator documentation

**Files:**
- Modify: `/home/builder/biba/README.md`
- Modify: `/home/builder/biba/docs/deployment.md`

**Step 1: Document the new entry point**

Describe:

- `/settings`
- stabilized tuning section
- trim section
- motor test section
- legacy route compatibility

**Step 2: Document trim semantics clearly**

Explain the difference between:

- saved persistent trim
- live trim in RC trim mode
- UI trim updates vs RC gesture saves

### Task 6: Run focused and full verification

**Files:**
- Test: `/home/builder/biba/tests/test_settings_store.py`
- Test: `/home/builder/biba/tests/test_motor_test_api.py`
- Test: `/home/builder/biba/tests/test_main.py`
- Test: `/home/builder/biba/tests/test_pid_tuning.py`
- Test: `/home/builder/biba/tests/test_config.py`

**Step 1: Run focused suite**

Run: `pytest tests/test_settings_store.py tests/test_motor_test_api.py tests/test_main.py tests/test_pid_tuning.py tests/test_config.py -q`
Expected: PASS.

**Step 2: Run the full suite**

Run: `pytest -q`
Expected: PASS.

### Task 7: Local smoke test the settings UI surface

**Files:**
- No additional source changes expected

**Step 1: Smoke test routes**

Verify:

- `/settings`
- `/settings/assets/settings.css`
- `/settings/assets/settings.js`
- `/settings/assets/biba-neon-sign.svg`
- `/api/settings`
- `/api/settings/pid-tuning`
- `/api/settings/motor-trim`
- `/api/settings/motor-test`

**Step 2: Confirm status behavior**

Verify that the page reflects:

- armed/disarmed state
- pending/apply revisions for PID tuning
- current/pending trim state
- motor test busy state

### Task 8: Deploy through the normal robot update workflow

**Files:**
- No additional source changes expected

**Step 1: Push the implementation**

Push the branch revision so CI builds the updated controller image.

**Step 2: Wait for Actions**

Use GitHub Actions status checks to confirm the controller-image and full-build workflows succeed for the new commit.

**Step 3: Update the robot**

Run `bbupdate` through the normal robot-side workflow.

**Step 4: Verify on hardware**

Confirm:

- `/settings` loads on the robot
- animated logo asset renders
- PID tuning updates apply while disarmed
- trim updates reflect both UI saves and RC gesture saves
- motor test still works