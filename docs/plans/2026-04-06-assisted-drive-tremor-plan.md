# Assisted Drive Tremor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate neutral-stick assist twitching by resetting stale controller state and suppressing small gyro-noise-driven corrections.

**Architecture:** Keep the fix local to the assisted-drive controller. Add regression coverage first, then introduce state reset on arm/disarm, measured-yaw filtering, and a near-zero deadband before yaw-rate control.

**Tech Stack:** Python 3.10, pytest, existing IMU-assisted drive controller.

---

### Task 1: Add Regression Coverage

**Files:**
- Modify: `tests/test_assisted_drive.py`

**Step 1: Write the failing test**

Add tests for:
- heading-hold state reset when armed state changes
- zero steering output for small neutral measured yaw noise
- attenuated response to short yaw spikes while sustained yaw still corrects

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba/.worktrees/imu-drive-modes && /home/builder/biba/.venv/bin/python -m pytest -q tests/test_assisted_drive.py`

Expected: FAIL on the new assertions.

### Task 2: Implement Minimal Controller Fix

**Files:**
- Modify: `biba-controller/motors/assisted_drive.py`

**Step 1: Reset state on arm/disarm transitions**

Reset heading and yaw controller state when the armed flag changes.

**Step 2: Add measured-yaw filtering and deadband**

Add a small first-order low-pass filter state and a configurable near-zero measured-yaw deadband before feeding yaw-rate control.

**Step 3: Keep the change minimal**

Do not alter mode routing, speed-mode logic, or motor ramping.

### Task 3: Verify

**Files:**
- Modify: `tests/test_assisted_drive.py`
- Modify: `biba-controller/motors/assisted_drive.py`

**Step 1: Run targeted tests**

Run: `cd /home/builder/biba/.worktrees/imu-drive-modes && /home/builder/biba/.venv/bin/python -m pytest -q tests/test_assisted_drive.py`

Expected: PASS.

**Step 2: Run full suite**

Run: `cd /home/builder/biba/.worktrees/imu-drive-modes && /home/builder/biba/.venv/bin/python -m pytest -q`

Expected: PASS.

**Step 3: Check patch hygiene**

Run: `git -C /home/builder/biba/.worktrees/imu-drive-modes diff --check`

Expected: no output.

Plan complete and saved to `docs/plans/2026-04-06-assisted-drive-tremor-plan.md`.