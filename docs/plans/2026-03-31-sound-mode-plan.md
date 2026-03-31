# Sound Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an explicit `SOUND_MODE` configuration that selects between direct voice playback, spectral voice playback, and synth-only system sounds.

**Architecture:** Centralize event-audio backend selection in `main.py` so startup and runtime event handlers call one routing layer instead of open-coding voice-first fallback behavior. Keep voice audition mode separate and preserve existing voice asset configuration for non-synth modes.

**Tech Stack:** Python, pytest, existing MotorSynth and controller config helpers.

---

### Task 1: Add failing routing tests

**Files:**
- Modify: `tests/test_main.py`
- Modify: `tests/test_main_voice_groups.py`

**Step 1: Write the failing test**

Add targeted tests for:

- `_play_grouped_voice(..., SOUND_MODE="voice")` -> `play_wav`
- `_play_grouped_voice(..., SOUND_MODE="spectral_voice")` -> `play_spectral`
- synth-mode startup or disarm path -> `play_named` / `play_named_async`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py tests/test_main_voice_groups.py -q`

Expected: failures showing the runtime still prefers spectral voice and does not honor `SOUND_MODE`.

**Step 3: Commit**

Do not commit yet.

### Task 2: Add config support for sound mode

**Files:**
- Modify: `biba-controller/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

Add a config test asserting `SOUND_MODE` accepts `voice`, `spectral_voice`, and `synth`, and rejects invalid values through `_get_env_choice`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -q`

Expected: failure because `SOUND_MODE` is not defined yet.

**Step 3: Write minimal implementation**

Add `SOUND_MODE = _get_env_choice("SOUND_MODE", "spectral_voice", {"voice", "spectral_voice", "synth"})` near the existing sound config.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -q`

Expected: PASS.

### Task 3: Centralize backend selection in main

**Files:**
- Modify: `biba-controller/main.py`
- Test: `tests/test_main.py`
- Test: `tests/test_main_voice_groups.py`

**Step 1: Write the failing test**

Ensure the tests from Task 1 still fail against the existing helper logic.

**Step 2: Write minimal implementation**

Add helpers that:

- choose the backend from `config.SOUND_MODE`
- route sync playback to `play_wav`, `play_spectral`, or `play_named`
- route async playback to `play_wav_async`, `play_spectral_async`, or `play_named_async`
- map event names to synth names for `synth` mode

Update startup, connection, arm/disarm, failsafe, low-voltage, and unmute replay paths to use the centralized routing.

**Step 3: Run focused tests**

Run: `pytest tests/test_main.py tests/test_main_voice_groups.py -q`

Expected: PASS.

### Task 4: Verify config and controller behavior together

**Files:**
- Modify: `tests/test_config.py` if needed
- Test: `tests/test_main.py`
- Test: `tests/test_main_voice_groups.py`

**Step 1: Run combined verification**

Run: `pytest tests/test_config.py tests/test_main.py tests/test_main_voice_groups.py -q`

Expected: PASS with explicit coverage of all three sound modes.

**Step 2: Refactor only if needed**

Keep any cleanup limited to naming or duplication removal while preserving green tests.

### Task 5: Run broader regression coverage

**Files:**
- Test: `tests/test_buzzer.py`
- Test: `tests/test_motor_synth.py`
- Test: `tests/test_main.py`
- Test: `tests/test_main_voice_groups.py`
- Test: `tests/test_config.py`

**Step 1: Run broader tests**

Run: `pytest tests/test_buzzer.py tests/test_motor_synth.py tests/test_config.py tests/test_main.py tests/test_main_voice_groups.py -q`

Expected: PASS.

**Step 2: Run full suite if focused tests pass cleanly**

Run: `pytest -q`

Expected: PASS.

### Task 6: Prepare deployment follow-up

**Files:**
- No code changes expected

**Step 1: Summarize runtime effect**

Document that setting `SOUND_MODE=synth` disables system voice playback without removing the voice pipeline.

**Step 2: Commit**

Run:

```bash
git add biba-controller/config.py biba-controller/main.py tests/test_config.py tests/test_main.py tests/test_main_voice_groups.py docs/plans/2026-03-31-sound-mode-design.md docs/plans/2026-03-31-sound-mode-plan.md
git commit -m "feat: add selectable sound mode"
```

Expected: one focused commit containing config, routing, tests, and docs.