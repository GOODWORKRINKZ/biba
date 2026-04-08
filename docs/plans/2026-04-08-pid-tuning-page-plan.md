# PID Tuning Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a second controller tools page that exposes live, persistent stabilized-drive tuning updates while the robot is disarmed.

**Architecture:** Extend the existing standard-library HTTP tools server with a `/pid-tuning` page and JSON API, persist tuning values in `/data/pid-tuning.json`, and let the main loop remain the only owner that applies validated pending updates by rebuilding the assisted-drive controller from a new tuning snapshot.

**Tech Stack:** Python standard library `http.server`, existing controller main loop, pytest, Docker Compose, inline HTML/CSS/JS.

---

### Task 1: Add failing config tests for persisted tuning defaults

**Files:**
- Modify: `/home/builder/biba/tests/test_config.py`
- Modify: `/home/builder/biba/biba-controller/config.py`
- Modify: `/home/builder/biba/.env.example`
- Modify: `/home/builder/biba/docker-compose.yml`

**Step 1: Write the failing test**

Add tests asserting:

- a new PID tuning settings path exists and defaults to `/data/pid-tuning.json`
- low-speed stabilization parameters used by the controller are available from config rather than only hardcoded dataclass defaults
- `.env.example` and `docker-compose.yml` expose the same settings surface

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -q`
Expected: FAIL because the new persisted path and missing config defaults do not exist yet.

**Step 3: Write minimal implementation**

Add the missing config values and env/compose exposure.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -q`
Expected: PASS.

### Task 2: Add failing tests for PID tuning state and persistence helpers

**Files:**
- Create: `/home/builder/biba/tests/test_pid_tuning.py`
- Create: `/home/builder/biba/biba-controller/pid_tuning.py`

**Step 1: Write the failing test**

Add tests for:

- default snapshot construction
- JSON load and save
- invalid persisted values falling back safely
- revision tracking for pending updates
- armed-state rejection for apply requests

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_pid_tuning.py -q`
Expected: FAIL because the module and behavior do not exist.

**Step 3: Write minimal implementation**

Implement:

- tuning dataclass or equivalent snapshot object
- validation helpers
- atomic JSON persistence
- a lock-protected store with current, pending, and status metadata

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_pid_tuning.py -q`
Expected: PASS.

### Task 3: Add failing API tests for `/pid-tuning`

**Files:**
- Modify: `/home/builder/biba/tests/test_motor_test_api.py`
- Modify: `/home/builder/biba/biba-controller/motor_test_api.py`

**Step 1: Write the failing test**

Add tests asserting:

- `GET /pid-tuning` serves the new page
- `GET /api/pid-tuning` returns current values and armed status
- `POST /api/pid-tuning` validates payloads and returns `400` on bad input
- `POST /api/pid-tuning` returns `409` while armed
- `POST /api/pid-tuning` accepts valid disarmed updates

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_test_api.py -q`
Expected: FAIL because the new routes and API contract do not exist.

**Step 3: Write minimal implementation**

Extend the existing server with:

- a PID tuning page builder
- `GET /api/pid-tuning`
- `POST /api/pid-tuning`
- shared routing for both tools pages

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motor_test_api.py -q`
Expected: PASS.

### Task 4: Add failing main-loop tests for startup load and disarmed-only live apply

**Files:**
- Modify: `/home/builder/biba/tests/test_main.py`
- Modify: `/home/builder/biba/biba-controller/main.py`

**Step 1: Write the failing test**

Add tests asserting:

- the controller starts from persisted PID tuning overrides when present
- the tools server is created with access to the tuning store
- pending tuning revisions are applied only while disarmed
- applying a new revision rebuilds the assisted-drive controller from the new snapshot

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -q`
Expected: FAIL because main currently has no tuning store or live apply path.

**Step 3: Write minimal implementation**

Wire startup load, tuning store ownership, and disarmed-only controller rebuild into the main loop.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -q`
Expected: PASS.

### Task 5: Add focused docs and operator guidance

**Files:**
- Modify: `/home/builder/biba/README.md`
- Modify: `/home/builder/biba/docs/deployment.md`

**Step 1: Write minimal documentation**

Document:

- `/pid-tuning` URL
- exposed parameter groups
- disarmed-only apply rule
- persistence precedence of `/data/pid-tuning.json`

**Step 2: Sanity-check docs references**

Verify no docs still describe tuning as env-only once the page exists.

### Task 6: Run focused regression coverage

**Files:**
- Test: `/home/builder/biba/tests/test_config.py`
- Test: `/home/builder/biba/tests/test_pid_tuning.py`
- Test: `/home/builder/biba/tests/test_motor_test_api.py`
- Test: `/home/builder/biba/tests/test_main.py`

**Step 1: Run focused tests**

Run: `pytest tests/test_config.py tests/test_pid_tuning.py tests/test_motor_test_api.py tests/test_main.py -q`
Expected: PASS.

**Step 2: Run the full suite**

Run: `pytest -q`
Expected: PASS.

### Task 7: Smoke-test the local tools surface

**Files:**
- No additional source changes expected

**Step 1: Run a local controller or isolated API smoke test**

Verify:

- `/motor-test` still renders
- `/pid-tuning` renders
- `GET /api/pid-tuning` returns defaults or persisted values
- `POST /api/pid-tuning` returns disarmed success and armed rejection in the appropriate test harness

**Step 2: Confirm behavior matches the contract**

Expected: one tools server, both pages reachable, no regression in existing motor test API.

### Task 8: Deploy through the normal robot update workflow

**Files:**
- No additional source changes expected

**Step 1: Push the implementation to GitHub**

Push the branch revision so GitHub Actions builds the updated controller image.

**Step 2: Wait for the relevant Actions runs**

Use `gh run watch ... --exit-status` for both the controller-image workflow and the full build workflow. Confirm the run SHA matches the pushed commit.

**Step 3: Update the robot**

Run the robot-side `bbupdate` alias through interactive SSH.

**Step 4: Verify deployment**

Confirm:

- controller container is healthy
- robot repo HEAD matches the pushed revision
- `/pid-tuning` loads from the robot
- disarmed apply works
- armed apply is rejected
- saved values survive a restart