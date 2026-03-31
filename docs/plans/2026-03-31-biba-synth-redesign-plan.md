# BiBa Synth Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign BiBa's synth-only event sounds around a new robot-pet identity while removing obsolete synth control flow that is not needed for the current software-PWM BTS7960 deployment.

**Architecture:** Keep voice, spectral voice, PCM, and FFT paths unchanged. Simplify `MotorSynth` around the current software detune model for mono and split BLHeli playback, then replace the synth system catalog with a new BiBa-specific vocabulary designed for coarse software-PWM frequency buckets.

**Tech Stack:** Python, pigpio, pytest, unittest.mock.

---

### Task 1: Lock down current synth routing with tests

**Files:**
- Modify: `tests/test_motor_synth.py`
- Modify: `tests/test_main.py`

**Step 1:** Add a failing test that proves the synth path for the current software-PWM configuration does not rely on the legacy hardware shared-channel slice behavior.

**Step 2:** Run the focused synth test to verify it fails for the expected reason.

**Step 3:** Add or update a runtime routing test showing `SOUND_MODE=synth` still resolves named synth events through `play_named` or `play_named_async`.

**Step 4:** Run the focused runtime test to verify it passes or fails only for the intended behavior change.

**Step 5:** Commit the test-only red-phase work.

### Task 2: Remove obsolete synth control flow

**Files:**
- Modify: `biba-controller/buzzer/motor_synth.py`
- Test: `tests/test_motor_synth.py`

**Step 1:** Remove the legacy hardware shared-channel bipolar slice helpers and any branching that is no longer required for the supported synth path.

**Step 2:** Keep `_tone()` and `_split_tone()` centered on the software detune model and the regular mono/split apply paths.

**Step 3:** Run the focused motor synth tests and make them pass with the minimal implementation.

**Step 4:** Commit the cleanup once the focused tests pass.

### Task 3: Rewrite the BiBa synth catalog

**Files:**
- Modify: `biba-controller/buzzer/melodies.py`
- Test: `tests/test_buzzer.py`
- Test: `tests/test_motor_synth.py`

**Step 1:** Replace the system synth entries in `BLHELI_CATALOG` with a new BiBa event vocabulary.

**Step 2:** Replace the system synth entries in `SPLIT_BLHELI_CATALOG` with matching two-motor variants.

**Step 3:** Keep all required system event names present: `startup`, `arm`, `disarm`, `low_voltage`, `failsafe`, `sos`, `connected`, `disconnected`, `shutdown`, `trim_enter`, `trim_exit`, and `biba_signature`.

**Step 4:** Adjust or add tests so they validate event coverage and split-catalog preference without depending on the exact old melodies.

**Step 5:** Run focused melody and synth tests to confirm the new catalog is wired correctly.

**Step 6:** Commit the catalog rewrite.

### Task 4: Run regression verification

**Files:**
- Test: `tests/test_motor_synth.py`
- Test: `tests/test_buzzer.py`
- Test: `tests/test_main.py`
- Test: `tests/test_config.py`

**Step 1:** Run the full focused regression set for synth, buzzer, runtime routing, and config.

**Step 2:** Confirm all tests pass and inspect any failures for accidental regressions in non-synth sound modes.

**Step 3:** Commit the verified result if additional fixes were needed after the prior task commits.

### Task 5: Push and deploy

**Files:**
- No source changes expected

**Step 1:** Push the verified branch tip to GitHub.

**Step 2:** Wait for the relevant GitHub Actions image build to finish successfully for the pushed revision.

**Step 3:** Deploy to the robot using the standard `bbupdate` workflow.

**Step 4:** Verify robot health, deployed revision, and relevant sound-mode environment variables after restart.