# Left Right Spectral Cache Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build left/right precomputed spectral cache artifacts for production voice WAVs and update runtime spectral playback to use separate motor-side frame streams without reintroducing startup latency.

**Architecture:** Reuse the existing WAV-to-peak-frame analysis once per source WAV, split analyzed peaks into left and right frame streams by even/odd peak index, and serialize one cache file per side during Docker image build. At runtime, preserve motor grouping so spectral playback can load the side-specific cache files for production voices and schedule left and right motor pins independently, while retaining fallback live analysis for uncached ad hoc WAV paths.

**Tech Stack:** Python 3.10, pytest, Docker build helper script, pigpio motor PWM playback

---

### Task 1: Add failing routing and cache-path tests

**Files:**
- Modify: `tests/test_wav_player.py`

**Step 1: Write the failing test**

Add focused tests that describe the new behavior:
- a pure helper that splits frame peaks into left and right lists by even/odd index
- default production cache path resolution for left and right artifacts

Expected test shape:

```python
def test_split_peak_frames_by_side_routes_even_left_and_odd_right():
    frames = [([(200, 1000), (300, 900), (400, 800), (500, 700)], 6)]

    left_frames, right_frames = split_peak_frames_by_side(frames)

    assert left_frames == [([(200, 1000), (400, 800)], 6)]
    assert right_frames == [([(300, 900), (500, 700)], 6)]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py -q -k "split_peak_frames_by_side or cache_path_for_side"`
Expected: FAIL because the routing helper and side-specific cache-path helper do not exist yet.

**Step 3: Write minimal implementation**

In `biba-controller/buzzer/wav_player.py` add:
- a side-routing helper for peak frames
- a helper resolving `voice-cache/<stem>.left.peaks.json` and `voice-cache/<stem>.right.peaks.json`

Keep the implementation minimal and pure.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py -q -k "split_peak_frames_by_side or cache_path_for_side"`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 2: Add failing build-helper tests for dual artifacts

**Files:**
- Modify: `tests/test_voice_spectral_cache.py`

**Step 1: Write the failing test**

Replace the single-artifact expectation with tests that require:
- one WAV produces exactly `*.left.peaks.json` and `*.right.peaks.json`
- both artifacts validate against the original source WAV
- no legacy shared `*.peaks.json` file is expected

Use generated temp WAV fixtures and inspect the returned artifact paths.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_voice_spectral_cache.py -q`
Expected: FAIL because the helper still writes one shared artifact per WAV.

**Step 3: Write minimal implementation**

Update `biba-controller/voice/build_spectral_cache.py` so each WAV is analyzed once, split into left and right frames, and both cache files are written with deterministic names.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_voice_spectral_cache.py -q`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 3: Add failing side-specific cache load tests

**Files:**
- Modify: `tests/test_wav_player.py`

**Step 1: Write the failing test**

Add tests covering:
- writing and loading side-specific cache payloads
- default production voice lookup loading both side artifacts without recomputing
- fallback to live analysis for uncached non-production WAVs

Use `patch("buzzer.wav_player.wav_to_peak_frames")` to prove production cache loads do not recompute when both artifacts exist.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py -q -k "side cache or split spectral"`
Expected: FAIL because side-specific cache readers/loaders are not implemented.

**Step 3: Write minimal implementation**

In `biba-controller/buzzer/wav_player.py`:
- generalize cache writing/loading so left and right artifacts can be read independently
- add a loader returning `(left_frames, right_frames)` when production side caches are present
- preserve fallback live analysis for non-production WAVs by deriving left/right frames in memory

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py -q -k "side cache or split spectral"`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 4: Add failing motor-synth split playback tests

**Files:**
- Modify: `tests/test_wav_player.py`
- Modify: `tests/test_main.py`
- Modify: `biba-controller/buzzer/motor_synth.py`

**Step 1: Write the failing test**

Add tests proving:
- spectral playback loads separate left and right frame streams
- left motor pins receive only left-frame tones and right motor pins receive only right-frame tones
- mono fallback for temporary uncached WAVs still works

Prefer focused fake-pigpio assertions over broad integration mocks.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py tests/test_main.py -q -k "split spectral or motor group"`
Expected: FAIL because `MotorSynth` still flattens pins and uses mono spectral playback.

**Step 3: Write minimal implementation**

Refactor runtime playback:
- in `biba-controller/buzzer/motor_synth.py`, preserve left and right motor groups
- in `biba-controller/buzzer/wav_player.py`, add a split scheduler that can drive left and right pin groups independently per frame duration
- in `biba-controller/main.py`, construct the synth with motor-side grouping intact

Keep public grouped-voice behavior unchanged except for the new split playback internals.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py tests/test_main.py -q -k "split spectral or motor group"`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 5: Verify build integration and regressions

**Files:**
- Modify: `biba-controller/Dockerfile` only if runtime path changes require a build-step argument or path adjustment
- Review: `docs/plans/2026-03-28-build-time-spectral-cache-design.md`

**Step 1: Run targeted regression tests**

Run: `pytest tests/test_voice_spectral_cache.py tests/test_wav_player.py tests/test_main.py -q`
Expected: PASS.

**Step 2: Run full test suite**

Run: `pytest -q`
Expected: PASS.

**Step 3: Sanity-check the build helper path**

Run: `pytest tests/test_voice_spectral_cache.py -q`
Expected: PASS and confirms the Docker build helper still emits artifacts correctly.

**Step 4: Commit**

Do not commit unless explicitly requested.