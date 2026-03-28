# Build-Time Spectral Cache Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Precompute production voice spectral frames during Docker image build, load them at runtime with safe fallback, and add precise controller-side BMS telemetry timing traces.

**Architecture:** Add a deterministic cache-generation helper that analyzes production WAV assets into a dedicated cache directory during Docker build. Keep `MotorSynth.play_spectral()` as the public entrypoint, but route it through a cache-aware loader that validates metadata and falls back to live analysis for uncached paths. Add narrow timestamped trace points on the BMS-to-CRSF battery telemetry path so controller-side latency can be measured directly.

**Tech Stack:** Python 3.11, Docker multi-stage build, pytest, existing `buzzer/wav_player.py` spectral analysis code, existing controller logging.

---

### Task 1: Add failing spectral cache tests

**Files:**
- Modify: `tests/test_wav_player.py`
- Modify: `biba-controller/buzzer/wav_player.py`

**Step 1: Write the failing test**

Add focused tests that describe:
- serializing analyzed frames with metadata into a cache file
- rejecting cache files when the source metadata or algorithm version does not match
- returning cached frames instead of recomputing them when metadata matches

Use a temp WAV fixture so the test stays hermetic.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py -q`
Expected: FAIL because no cache helpers or metadata validation exist yet.

**Step 3: Write minimal implementation**

Add cache-oriented helpers in `biba-controller/buzzer/wav_player.py` for:
- computing source metadata
- serializing cache payloads
- validating cache payloads
- loading cached frames with fallback to live analysis

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py -q`
Expected: PASS for the new cache tests.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 2: Add failing runtime integration tests for cached playback

**Files:**
- Modify: `tests/test_wav_player.py`
- Modify: `biba-controller/buzzer/motor_synth.py`

**Step 1: Write the failing test**

Add integration tests proving:
- `MotorSynth.play_spectral()` uses cached frames when a valid cache exists
- `MotorSynth.play_spectral()` still falls back to live analysis for an uncached temp WAV

Mock the low-level playback so the test can assert which analysis path was chosen.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wav_player.py -q`
Expected: FAIL because `MotorSynth.play_spectral()` currently always calls `wav_to_peak_frames()`.

**Step 3: Write minimal implementation**

Update `MotorSynth.play_spectral()` to use a cache-aware spectral loader while preserving its public signature and current error handling.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wav_player.py -q`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 3: Add failing build-helper tests

**Files:**
- Create: `tests/test_voice_spectral_cache.py`
- Create: `biba-controller/voice/build_spectral_cache.py`

**Step 1: Write the failing test**

Add tests describing a helper that:
- scans a voice directory for production WAVs
- writes one cache artifact per source WAV into an output directory
- records expected metadata and frames in the generated cache file names or payloads

Use temp directories and tiny generated WAV fixtures.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_voice_spectral_cache.py -q`
Expected: FAIL because the helper script does not exist yet.

**Step 3: Write minimal implementation**

Create `biba-controller/voice/build_spectral_cache.py` with a small CLI that:
- accepts `--voice-dir` and `--out-dir`
- iterates `.wav` files deterministically
- invokes the cache writer for each production WAV

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_voice_spectral_cache.py -q`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 4: Wire the Docker build step

**Files:**
- Modify: `biba-controller/Dockerfile`
- Modify: `README.md`
- Modify: `docs/deployment.md`

**Step 1: Add a failing expectation in docs review**

Identify the missing documentation points:
- build now precomputes production spectral cache artifacts
- cache artifacts are image-derived, not repo-tracked
- runtime still falls back for uncached WAV paths

**Step 2: Update Dockerfile minimally**

Add a build step after source copy that runs the new helper, for example:

```dockerfile
RUN python voice/build_spectral_cache.py --voice-dir /app/voice --out-dir /app/voice-cache
```

Adjust paths to match the controller image working tree.

**Step 3: Update docs**

Document the new build-time cache behavior in `README.md` and `docs/deployment.md`.

**Step 4: Verify direct helper invocation**

Run: `pytest tests/test_voice_spectral_cache.py -q`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 5: Add failing BMS telemetry trace tests

**Files:**
- Modify: `tests/test_main.py`
- Modify: `biba-controller/main.py`
- Modify: `biba-controller/crsf/telemetry.py` only if required

**Step 1: Write the failing test**

Add a focused test that proves the controller can emit precise diagnostic trace lines around battery telemetry send boundaries without changing business behavior.

The trace should cover:
- the time fresh BMS state is consumed by main loop
- the time battery telemetry payload is emitted toward CRSF

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -q`
Expected: FAIL because no such trace helper or conditional logging exists yet.

**Step 3: Write minimal implementation**

Add a narrow trace path in `biba-controller/main.py` using monotonic timestamps. Keep it cheap and easy to enable for a diagnostic run.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -q`
Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 6: Run focused verification

**Files:**
- Modify only if verification reveals regressions caused by the new changes.

**Step 1: Run spectral tests**

Run: `pytest tests/test_wav_player.py tests/test_voice_spectral_cache.py -q`
Expected: PASS.

**Step 2: Run controller tests**

Run: `pytest tests/test_main.py tests/test_main_voice_groups.py tests/test_main_voice_audition.py -q`
Expected: PASS.

**Step 3: Run related voice pipeline tests**

Run: `pytest tests/test_voice_prep_manifest.py tests/test_voice_prep_profiles.py tests/test_voice_prep_audition.py tests/test_voice_prep_promote.py -q`
Expected: PASS.

**Step 4: Run lint**

Run: `/home/builder/biba/.venv/bin/ruff check biba-controller/ tests/`
Expected: PASS.

### Task 7: Prepare the robot validation follow-up

**Files:**
- No code required unless verification reveals a missing log surface.

**Step 1: Build or pull updated image through the normal workflow**

Use the existing CI and robot-side update path. Do not copy files onto the robot manually.

**Step 2: Validate runtime effect on robot**

Measure:
- arm voice event responsiveness after cache-enabled image deploy
- controller-side BMS publish-to-UART timestamps during throttle runs

**Step 3: Decide the next bottleneck**

Based on the new trace, choose one:
- controller-side telemetry cadence tuning
- Lua/radio-side telemetry visibility investigation
- audition asset cache extension if runtime audition latency matters too

Plan complete and saved to `docs/plans/2026-03-28-build-time-spectral-cache.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?