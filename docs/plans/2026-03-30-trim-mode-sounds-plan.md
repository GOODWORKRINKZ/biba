# Trim Mode Sounds Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add short distinct two-channel motor-synth sounds when motor trim mode is entered and when trim is saved and exited.

**Architecture:** Reuse the existing named BLHeli motor-synth melody path by adding `trim_enter` and `trim_exit` entries to the melody catalog, then trigger them from the trim mode state transitions in the main controller loop with `allow_when_muted=True`. Verify behavior with focused controller tests and melody-catalog tests.

**Tech Stack:** Python, pytest, existing motor-synth melody catalog, CRSF controller runtime

---

### Task 1: Add failing transition-sound tests

**Files:**
- Modify: `tests/test_main.py`

**Step 1: Write the failing test**

Add tests that enter trim mode and save/exit trim mode, then assert the buzzer receives `trim_enter` and `trim_exit` respectively.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -k trim_mode_sound -v`
Expected: FAIL because the sound names are not played yet.

**Step 3: Write minimal implementation**

Implement the smallest runtime changes to request the expected named sounds.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -k trim_mode_sound -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_main.py biba-controller/main.py
git commit -m "feat: add trim mode transition sounds"
```

### Task 2: Add failing melody-catalog tests

**Files:**
- Modify: `tests/test_motor_synth.py`
- Modify: `biba-controller/buzzer/melodies.py`

**Step 1: Write the failing test**

Add tests that assert `trim_enter` and `trim_exit` are available in the named melody catalog and contain non-empty BLHeli entries.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_synth.py -k trim -v`
Expected: FAIL because the entries do not exist yet.

**Step 3: Write minimal implementation**

Add `trim_enter` and `trim_exit` entries to `BLHELI_CATALOG` with short distinct motifs.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_motor_synth.py -k trim -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_motor_synth.py biba-controller/buzzer/melodies.py
git commit -m "feat: add trim mode melodies"
```

### Task 3: Run focused regression

**Files:**
- Test: `tests/test_main.py`
- Test: `tests/test_motor_synth.py`

**Step 1: Run focused regression**

Run: `pytest tests/test_main.py tests/test_motor_synth.py -v`
Expected: PASS.

**Step 2: Commit**

```bash
git add docs/plans/2026-03-30-trim-mode-sounds-design.md docs/plans/2026-03-30-trim-mode-sounds-plan.md
git commit -m "docs: add trim mode sounds design and plan"
```