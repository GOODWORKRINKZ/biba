# Motor Synth Two-Channel Polyphony Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make all named BLHeli melodies optionally playable as true left/right two-channel motor polyphony while preserving mono fallback for melodies without split definitions.

**Architecture:** Keep the current mono catalog and playback path intact. Expand `SPLIT_BLHELI_CATALOG` so it can hold explicit left/right parts for the full melody catalog, then rely on existing `MotorSynth.play_named()` routing to prefer split playback whenever split motor groups and split definitions are available.

**Tech Stack:** Python, pigpio, pytest, existing `MotorSynth`, `parse_blheli`, and melody catalogs in `biba-controller/buzzer/melodies.py`.

---

### Task 1: Add routing regression tests for split-vs-mono selection

**Files:**
- Modify: `tests/test_motor_synth.py`
- Review: `biba-controller/buzzer/motor_synth.py`
- Review: `biba-controller/buzzer/melodies.py`

**Step 1: Write the failing test**

Add a test that defines a temporary split melody entry and asserts `play_named()` energizes left and right motor groups with distinct frequencies instead of falling back to mono.

```python
def test_play_named_prefers_split_catalog_entry(monkeypatch):
    pi = MagicMock()
    from buzzer.motor_synth import MotorSynth
    from buzzer import melodies

    synth = MotorSynth(
        pi,
        [12, 19],
        comp_pins=[18, 13],
        left_pwm_pins=[12],
        left_comp_pins=[18],
        right_pwm_pins=[19],
        right_comp_pins=[13],
    )
    synth._wait_or_interrupted = lambda _delay: False
    monkeypatch.setitem(melodies.SPLIT_BLHELI_CATALOG, "poly_test", ("C5 1/8", "E5 1/8", 120))

    synth.play_named("poly_test")

    non_zero = [args for args, _kwargs in [(call.args, call.kwargs) for call in pi.hardware_PWM.call_args_list] if args[1] > 0]
    assert any(args[0] == 12 and args[1] != 0 for args in non_zero)
    assert any(args[0] == 19 and args[1] != 0 for args in non_zero)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_synth.py::test_play_named_prefers_split_catalog_entry -q`

Expected: failure if the test assumptions or temporary catalog setup are wrong.

**Step 3: Write the fallback test**

Add a test asserting that a mono-only melody still routes through the mono path when no split entry exists.

```python
def test_play_named_falls_back_to_mono_when_split_missing(monkeypatch):
    ...
```

**Step 4: Run both tests**

Run: `pytest tests/test_motor_synth.py -q`

Expected: new tests pass and existing tests remain green.

### Task 2: Add explicit split entries for system melodies

**Files:**
- Modify: `biba-controller/buzzer/melodies.py`
- Test: `tests/test_motor_synth.py`

**Step 1: Write the failing test**

Add a test that verifies representative system melodies now exist in `SPLIT_BLHELI_CATALOG`.

```python
def test_system_polyphonic_melodies_exist():
    from buzzer import melodies

    expected = {
        "biba_signature",
        "startup",
        "arm",
        "disarm",
        "low_voltage",
        "failsafe",
        "sos",
        "connected",
        "disconnected",
        "shutdown",
        "trim_enter",
        "trim_exit",
    }
    assert expected.issubset(melodies.SPLIT_BLHELI_CATALOG)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_synth.py::test_system_polyphonic_melodies_exist -q`

Expected: FAIL because most system names are not yet in the split catalog.

**Step 3: Write minimal implementation**

Add hand-authored left/right BLHeli strings for all system melodies in `SPLIT_BLHELI_CATALOG`.

Implementation notes:

- Keep the existing mono `BLHELI_CATALOG` entries untouched.
- Match durations across left/right phrases so `zip(left_notes, right_notes)` preserves the intended arrangement.
- Use `P` tokens to insert silence on one side when needed.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_motor_synth.py -q`

Expected: system-catalog assertions pass without breaking existing behavior.

### Task 3: Add explicit split entries for fun melodies

**Files:**
- Modify: `biba-controller/buzzer/melodies.py`
- Test: `tests/test_motor_synth.py`

**Step 1: Write the failing test**

Add a test that verifies every melody in `FUN_PLAYLIST` also has a split entry.

```python
def test_fun_playlist_melodies_have_split_versions():
    from buzzer import melodies

    assert set(melodies.FUN_PLAYLIST).issubset(melodies.SPLIT_BLHELI_CATALOG)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_motor_synth.py::test_fun_playlist_melodies_have_split_versions -q`

Expected: FAIL because fun melodies are currently mono-only.

**Step 3: Write minimal implementation**

Add hand-authored left/right parts for each fun melody in `SPLIT_BLHELI_CATALOG`.

Implementation notes:

- Keep phrases musically simple and robust for motor playback.
- Prefer octave support lines, alternating harmony, or rhythmic counter-lines over dense chords.
- Preserve original melody recognition in at least one channel.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_motor_synth.py -q`

Expected: all fun-catalog coverage assertions pass.

### Task 4: Add representative playback assertions for system and fun polyphony

**Files:**
- Modify: `tests/test_motor_synth.py`
- Review: `biba-controller/buzzer/motor_synth.py`

**Step 1: Write the failing test**

Add a representative system playback test, for example `startup`, that asserts left and right non-zero frequencies differ during playback.

```python
def test_play_named_startup_uses_distinct_left_and_right_frequencies():
    ...
```

**Step 2: Write another failing test**

Add a representative fun playback test, for example `mario`, with the same assertion.

```python
def test_play_named_fun_melody_uses_distinct_left_and_right_frequencies():
    ...
```

**Step 3: Run tests to verify failures**

Run: `pytest tests/test_motor_synth.py -q`

Expected: failures if split entries are missing or collapse to identical routing.

**Step 4: Adjust implementation only if necessary**

If catalog data is correct and routing already works, no runtime code changes should be needed. If a test shows split routing does not trigger for valid catalog entries, update `MotorSynth.play_named()` minimally.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_motor_synth.py -q`

Expected: representative playback tests pass.

### Task 5: Run focused regression suite

**Files:**
- Test: `tests/test_motor_synth.py`
- Test: `tests/test_wav_player.py`
- Test: `tests/test_main.py`

**Step 1: Run motor synth tests**

Run: `pytest tests/test_motor_synth.py -q`

Expected: PASS.

**Step 2: Run adjacent audio regression tests**

Run: `pytest tests/test_wav_player.py tests/test_main.py -q`

Expected: PASS.

**Step 3: Run combined focused suite**

Run: `pytest tests/test_motor_synth.py tests/test_wav_player.py tests/test_main.py -q`

Expected: PASS with no regressions in mono or WAV/spectral paths.

**Step 4: Run lint**

Run: `ruff check biba-controller/buzzer/melodies.py biba-controller/buzzer/motor_synth.py tests/test_motor_synth.py tests/test_wav_player.py tests/test_main.py`

Expected: PASS.

### Task 6: Update documentation

**Files:**
- Modify: `docs/plans/2026-03-26-motor-synth-melodies-design.md` (if still used as reference)
- Or modify: `README.md` if user-facing melody capability is documented there

**Step 1: Write the failing doc expectation**

List the user-visible behavior to document:

- named BLHeli melodies may have explicit left/right parts
- mono fallback remains supported
- two-motor setups can play two-channel melodies

**Step 2: Write minimal implementation**

Update the relevant doc location with a short explanation of split melody support.

**Step 3: Verify docs changed only where needed**

Run: `git --no-pager diff -- docs/plans/2026-03-26-motor-synth-melodies-design.md README.md`

Expected: concise documentation-only diff.