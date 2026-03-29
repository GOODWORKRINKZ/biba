# Right Motor Inversion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore the existing right-motor inversion capability by wiring inversion flags through deployment config and then deploy the updated configuration to the robot.

**Architecture:** Keep motor inversion in the existing runtime path via `MOTOR1_INVERTED` and `MOTOR2_INVERTED`. Fix the deployment layer so `docker-compose.yml` forwards those env values instead of hardcoding `0`, and document the robot-facing setting in `.env.example`.

**Tech Stack:** Python 3.11, pytest, Docker Compose, GitHub Actions, GHCR deployment

---

### Task 1: Lock inversion wiring with tests

**Files:**
- Modify: `tests/test_config.py`

**Step 1:** Add a failing test asserting `docker-compose.yml` exposes `MOTOR1_INVERTED` and `MOTOR2_INVERTED` via env interpolation.

**Step 2:** Add a failing test asserting `.env.example` documents `MOTOR1_INVERTED` and `MOTOR2_INVERTED`.

**Step 3:** Run only the new tests and confirm they fail for the expected reason.

### Task 2: Fix deployment config wiring

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Step 1:** Replace hardcoded inversion values in `docker-compose.yml` with `${MOTOR1_INVERTED:-0}` and `${MOTOR2_INVERTED:-0}`.

**Step 2:** Add `MOTOR1_INVERTED=0` and `MOTOR2_INVERTED=0` to `.env.example` near the motor config block.

**Step 3:** Re-run the focused tests and confirm they pass.

### Task 3: Verify and deploy

**Files:**
- No code changes expected

**Step 1:** Run the relevant pytest subset for config/deployment wiring.

**Step 2:** Push the branch tip to GitHub if needed and wait for the image workflow for that exact revision to finish successfully.

**Step 3:** Run `bbupdate` on the robot through interactive SSH and verify robot `HEAD`, container health, and effective `MOTOR2_INVERTED=1` in the container environment.