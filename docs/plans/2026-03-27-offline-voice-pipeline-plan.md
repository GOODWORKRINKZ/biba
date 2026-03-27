# Offline Voice Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an offline pipeline that generates and prepares robot-voice WAV candidates for BiBa events, verifies them through robot-side playback, and keeps runtime defaults to one production asset per event.

**Architecture:** The implementation is split into two concerns. First, runtime defaults stay conservative by using one approved WAV per event in `config.py`. Second, a separate offline toolchain reads a phrase manifest, generates or ingests speech assets, applies repeatable DSP profiles, exports candidate WAVs into a working directory, and prepares a robot-audition manifest so those candidates can be deployed and played through the real motor spectral path.

**Tech Stack:** Python, pytest, YAML manifest parsing, subprocess-based TTS invocation, ffmpeg or sox-backed DSP helpers, existing BiBa voice asset layout, robot-side deploy via `bbupdate`.

---

### Task 1: Lock runtime defaults to one asset per event

**Files:**
- Modify: `biba-controller/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

```python
def test_config_defaults_to_single_voice_asset_per_event(...):
    module = importlib.reload(config_module)
    assert module.STARTUP_VOICES == ["/app/voice/startup_returned.wav"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -q`
Expected: FAIL because defaults still contain multiple entries.

**Step 3: Write minimal implementation**

Set the default values in `config.py` so each event list contains one approved WAV path.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add biba-controller/config.py tests/test_config.py
git commit -m "chore: default voice events to single assets"
```

### Task 2: Define the offline phrase manifest format

**Files:**
- Create: `voice-src/phrases.yml`
- Create: `tests/test_voice_prep_manifest.py`
- Create: `scripts/voice_prep.py`

**Step 1: Write the failing test**

```python
def test_load_manifest_reads_event_entries(tmp_path):
    manifest = load_manifest(tmp_path / "phrases.yml")
    assert manifest["startup"].text == "system online"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_voice_prep_manifest.py -q`
Expected: FAIL because loader and manifest file do not exist yet.

**Step 3: Write minimal implementation**

Add:
- a small manifest schema with event key, text, optional seed WAV, optional profile list
- parser code in `scripts/voice_prep.py`
- an initial `voice-src/phrases.yml` with one phrase per current event

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_voice_prep_manifest.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add voice-src/phrases.yml scripts/voice_prep.py tests/test_voice_prep_manifest.py
git commit -m "feat: add offline voice phrase manifest"
```

### Task 3: Add backend command generation for offline TTS

**Files:**
- Modify: `scripts/voice_prep.py`
- Test: `tests/test_voice_prep_manifest.py`

**Step 1: Write the failing test**

```python
def test_build_tts_command_for_text_phrase():
    command = build_tts_command("system online", output_path, profile)
    assert command[0].endswith("espeak-ng")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_voice_prep_manifest.py -q`
Expected: FAIL because command builder is missing.

**Step 3: Write minimal implementation**

Implement a helper that builds a deterministic subprocess command for the chosen TTS backend without executing it in tests.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_voice_prep_manifest.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/voice_prep.py tests/test_voice_prep_manifest.py
git commit -m "feat: add offline voice tts command builder"
```

### Task 4: Add DSP profile recipes

**Files:**
- Modify: `scripts/voice_prep.py`
- Create: `tests/test_voice_prep_profiles.py`

**Step 1: Write the failing test**

```python
def test_command_slow_profile_contains_band_shaping_and_normalization():
    filters = build_filter_chain("command_slow")
    assert "highpass" in filters
    assert "lowpass" in filters
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_voice_prep_profiles.py -q`
Expected: FAIL because profile builder is missing.

**Step 3: Write minimal implementation**

Implement a small set of named profile recipes:
- `command_slow`
- `robot_harsh`
- `seed_clean`

Return structured recipe data instead of raw shell strings where practical.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_voice_prep_profiles.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/voice_prep.py tests/test_voice_prep_profiles.py
git commit -m "feat: add offline voice prep profiles"
```

### Task 5: Export candidate assets into a working directory

**Files:**
- Modify: `scripts/voice_prep.py`
- Test: `tests/test_voice_prep_profiles.py`

**Step 1: Write the failing test**

```python
def test_candidate_output_path_encodes_event_profile_and_variant(tmp_path):
    path = build_candidate_path(tmp_path, "startup", "command_slow", 1)
    assert path.name == "startup__command_slow__v01.wav"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_voice_prep_profiles.py -q`
Expected: FAIL because export naming is missing.

**Step 3: Write minimal implementation**

Implement deterministic working-path generation under `voice-work/<event>/` with traceable filenames.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_voice_prep_profiles.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/voice_prep.py tests/test_voice_prep_profiles.py
git commit -m "feat: add offline voice candidate export paths"
```

### Task 6: Add robot audition manifest generation

**Files:**
- Modify: `scripts/voice_prep.py`
- Create: `tests/test_voice_prep_audition.py`

**Step 1: Write the failing test**

```python
def test_build_audition_manifest_records_candidate_order(tmp_path):
    manifest_path = write_audition_manifest(...)
    assert manifest_path.name == "audition.yml"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_voice_prep_audition.py -q`
Expected: FAIL because audition manifest support is missing.

**Step 3: Write minimal implementation**

Implement manifest export under `voice-work/robot-audition/` that records:
- event key
- ordered candidate paths
- profile metadata
- optional spoken label or index for human note-taking

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_voice_prep_audition.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/voice_prep.py tests/test_voice_prep_audition.py
git commit -m "feat: add robot audition manifest export"
```

### Task 7: Add robot-side audition playback command

**Files:**
- Modify: `biba-controller/main.py`
- Modify: `biba-controller/config.py`
- Create: `tests/test_main_voice_audition.py`

**Step 1: Write the failing test**

```python
def test_main_robot_audition_mode_plays_manifest_candidates(monkeypatch):
    result = main.main()
    assert played == ["/app/voice-work/robot-audition/startup/candidate1.wav"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main_voice_audition.py -q`
Expected: FAIL because audition mode does not exist yet.

**Step 3: Write minimal implementation**

Add a guarded audition mode that:
- reads a robot-audition manifest
- plays listed candidates in order through `play_spectral`
- exits cleanly after playback

Keep the mode explicitly opt-in so normal controller behavior does not change.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main_voice_audition.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add biba-controller/main.py biba-controller/config.py tests/test_main_voice_audition.py
git commit -m "feat: add robot audition playback mode"
```

### Task 8: Document human audition and promotion workflow

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-27-offline-voice-pipeline-design.md`
- Modify: `docs/deployment.md`

**Step 1: Write the failing test**

No automated test is required for prose-only documentation changes.

**Step 2: Verify current docs are missing the workflow**

Run: `rg -n "voice-work|voice-src|promotion|audition|bbupdate" README.md docs/plans/2026-03-27-offline-voice-pipeline-design.md docs/deployment.md`
Expected: missing or incomplete references before update.

**Step 3: Write minimal implementation**

Add operator-facing documentation covering:
- where source phrases live
- where generated candidates appear
- how robot audition assets are deployed and played through the robot
- how one winning WAV is promoted into `biba-controller/voice/`
- why defaults stay single-asset during tuning

**Step 4: Run verification**

Run: `rg -n "voice-work|voice-src|promotion|audition|bbupdate" README.md docs/plans/2026-03-27-offline-voice-pipeline-design.md docs/deployment.md`
Expected: matching lines present.

**Step 5: Commit**

```bash
git add README.md docs/deployment.md docs/plans/2026-03-27-offline-voice-pipeline-design.md
git commit -m "docs: describe robot audition workflow for voice assets"
```

Plan complete and saved to `docs/plans/2026-03-27-offline-voice-pipeline-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
