# Motor Synth Software Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild `MotorSynth` around a direct software PWM dual-motor model with a tested manual PWM path, 20% synth delta, and left/right motor polyphony.

**Architecture:** Keep the public `MotorSynth` interface compatible with `main.py`, but replace the internals with a simple dual-motor software PWM core. Each motor is modeled explicitly as `LPWM` plus `RPWM`, and higher-level note playback is built on top of direct four-channel software PWM writes.

**Tech Stack:** Python 3.10, pigpio software PWM, pytest, existing BLHeli melody parser.

---

### Task 1: Rewrite the test target around the new mental model

**Files:**
- Modify: `tests/test_motor_synth.py`

**Step 1: Write the failing tests**

Add or replace tests so they describe the new behavior only:

- constructor preserves explicit left/right motor pin mapping
- `play_manual_split_pwm` uses the confirmed direct `set_PWM_*` path
- synth note helper uses `20%` delta
- equal duty goes to both `LPWM` and `RPWM` on the same motor
- `play_split_blheli` can drive left and right motor independently
- `play_named` routes through the new note playback path

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_synth.py -q`

Expected: failures because `motor_synth.py` is empty and the new behavior is not implemented.

**Step 3: Commit**

```bash
git add tests/test_motor_synth.py
git commit -m "test: define motor synth software rewrite behavior"
```

### Task 2: Implement the minimal `MotorSynth` skeleton

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Test: `tests/test_motor_synth.py`

**Step 1: Write minimal implementation**

Implement:

- `MotorSynth.__init__`
- software PWM pin initialization
- `off`
- `set_control_active`
- internal pin mapping for left/right motor and each motor's `LPWM/RPWM`

Do not implement wav/spectral or hardware mode behavior in this task.

**Step 2: Run targeted tests**

Run: `pytest tests/test_motor_synth.py -q -k 'initializes or off or control_active'`

Expected: pass for constructor/control/off coverage.

**Step 3: Commit**

```bash
git add biba-controller/buzzer/motor_synth.py tests/test_motor_synth.py
git commit -m "feat: add minimal software motor synth skeleton"
```

### Task 3: Implement direct motor PWM primitives

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Test: `tests/test_motor_synth.py`

**Step 1: Write failing tests**

Add focused tests for:

- `_apply_motor_pwm` writing direct `set_PWM_range`, `set_PWM_frequency`, `set_PWM_dutycycle`
- `_apply_dual_motor_pwm` driving all four motor channels
- `_stop_motor_pwm` restoring silence on both channels of a motor

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_synth.py -q -k 'apply_motor_pwm or dual_motor_pwm or stop_motor_pwm'`

Expected: FAIL.

**Step 3: Write minimal implementation**

Implement the three direct software PWM primitives using the confirmed working pattern.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motor_synth.py -q -k 'apply_motor_pwm or dual_motor_pwm or stop_motor_pwm'`

Expected: PASS.

**Step 5: Commit**

```bash
git add biba-controller/buzzer/motor_synth.py tests/test_motor_synth.py
git commit -m "feat: add direct dual-motor software pwm primitives"
```

### Task 4: Implement synth frequency mapping with 20% delta

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Test: `tests/test_motor_synth.py`

**Step 1: Write failing tests**

Add tests for a helper that converts:

- base frequency
- delta percent `20`
- equal duty

into per-motor `LPWM/RPWM` frequencies and equal duties.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_synth.py -q -k 'delta or synth mapping'`

Expected: FAIL.

**Step 3: Write minimal implementation**

Implement helper for the synth frequency pair and equal-duty mapping.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motor_synth.py -q -k 'delta or synth mapping'`

Expected: PASS.

**Step 5: Commit**

```bash
git add biba-controller/buzzer/motor_synth.py tests/test_motor_synth.py
git commit -m "feat: add 20 percent software synth delta mapping"
```

### Task 5: Implement note playback and split polyphony

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Test: `tests/test_motor_synth.py`

**Step 1: Write failing tests**

Cover:

- `play`
- `play_blheli`
- `play_split_blheli`
- independent left/right note streams for polyphony

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_synth.py -q -k 'play or blheli or split'`

Expected: FAIL.

**Step 3: Write minimal implementation**

Implement note playback on top of the new direct dual-motor software PWM core.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motor_synth.py -q -k 'play or blheli or split'`

Expected: PASS.

**Step 5: Commit**

```bash
git add biba-controller/buzzer/motor_synth.py tests/test_motor_synth.py
git commit -m "feat: rebuild software motor synth note playback"
```

### Task 6: Reconnect named playback and compatibility wiring

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Modify: `tests/test_motor_synth.py`
- Verify: `tests/test_main.py`
- Verify: `tests/test_motor_test_api.py`

**Step 1: Write failing tests**

Ensure:

- `play_named` works through the rebuilt playback path
- constructor compatibility with `main.py` stays intact
- motor test executor still works with `play_manual_split_pwm`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_synth.py tests/test_main.py tests/test_motor_test_api.py -q`

Expected: FAIL if compatibility is incomplete.

**Step 3: Write minimal implementation**

Wire `play_named` and compatibility fields expected by `main.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motor_synth.py tests/test_main.py tests/test_motor_test_api.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add biba-controller/buzzer/motor_synth.py tests/test_motor_synth.py tests/test_main.py tests/test_motor_test_api.py
git commit -m "feat: reconnect motor synth compatibility paths"
```

### Task 7: Remove or defer unsupported features cleanly

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Modify: `tests/test_motor_synth.py`

**Step 1: Write failing tests**

Add explicit behavior for unsupported paths in phase one:

- `HARDWARE` either rejected clearly or treated as unsupported
- `play_wav` and `play_spectral` no-op or explicit temporary stub

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_synth.py -q -k 'hardware or wav or spectral'`

Expected: FAIL.

**Step 3: Write minimal implementation**

Implement explicit temporary behavior rather than leaving dead broken code paths.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motor_synth.py -q -k 'hardware or wav or spectral'`

Expected: PASS.

**Step 5: Commit**

```bash
git add biba-controller/buzzer/motor_synth.py tests/test_motor_synth.py
git commit -m "refactor: defer unsupported motor synth modes"
```

### Task 8: Full verification and deployment

**Files:**
- Verify: `biba-controller/buzzer/motor_synth.py`
- Verify: `tests/test_motor_synth.py`
- Verify: `tests/test_main.py`
- Verify: `tests/test_motor_test_api.py`
- Update: `docs/plans/2026-04-01-motor-synth-software-rewrite-design.md`

**Step 1: Run lint and full tests**

Run: `python -m ruff check biba-controller tests`

Expected: PASS.

Run: `pytest`

Expected: PASS.

**Step 2: Commit final implementation**

```bash
git add biba-controller/buzzer/motor_synth.py tests docs/plans/2026-04-01-motor-synth-software-rewrite-design.md docs/plans/2026-04-01-motor-synth-software-rewrite-plan.md
git commit -m "refactor: rebuild software motor synth around dual pwm motors"
```

**Step 3: Push and wait for CI**

Run: `git push origin main`

Run: `gh run list --repo GOODWORKRINKZ/biba --limit 20 --json databaseId,workflowName,status,conclusion,headSha`

Expected: `G: Build Controller Image` and `G: Build All` complete successfully for the pushed SHA.

**Step 4: Deploy to robot**

Run the standard robot update flow only after CI is green:

```bash
sshpass -p 'open' ssh -tt -o StrictHostKeyChecking=no biba@192.168.2.185 \
  'bash -ic "source ~/biba/scripts/biba_aliases.sh; bbupdate"'
```

**Step 5: Verify live deployment**

Run post-deploy checks:

- robot repo `HEAD`
- container healthy
- running container contains the rebuilt `MotorSynth`
- manual motor test still works