# Speech Band Range Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand the default spectral speech band to 100..1200 Hz so arming and similar voice prompts are analyzed more completely.

**Architecture:** Keep the change minimal by updating the default speech-band constants in the wav spectral analyzer, adjusting the regression test that encodes those defaults, and regenerating cached peak-frame assets so runtime playback uses the new band immediately.

**Tech Stack:** Python, pytest, build-time voice spectral cache JSON

---

### Task 1: Lock the new defaults in tests

**Files:**
- Modify: `tests/test_wav_player.py`

**Step 1: Write the failing test**

Update the default-constant assertions so they require a minimum of 100 Hz and a maximum of at least 1200 Hz.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py -k default_constants_match_espeak_band -q`

**Step 3: Write minimal implementation**

Change `_SPEECH_MIN_FREQ` and `_SPEECH_MAX_FREQ` defaults in `biba-controller/buzzer/wav_player.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py -k default_constants_match_espeak_band -q`

**Step 5: Commit**

Commit with the wav-player constant update, test update, and docs.

### Task 2: Refresh generated spectral cache data

**Files:**
- Modify: `biba-controller/voice-cache/*.json`

**Step 1: Rebuild the cache**

Run the cache builder against `biba-controller/voice` into `biba-controller/voice-cache`.

**Step 2: Verify regenerated assets exist**

Confirm arm/disarm and other voice cache files were refreshed.

### Task 3: Verify and deploy

**Files:**
- Verify: `tests/test_wav_player.py`
- Verify: full test suite

**Step 1: Run targeted wav-player tests**

Run: `pytest tests/test_wav_player.py -q`

**Step 2: Run full suite**

Run: `pytest -q`

**Step 3: Commit and deploy**

Push the commit, confirm CI is green, then use robot-side `bbupdate` and verify health/image revision.