# Current Sense Calibration Trace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a delayed-BMS-aware calibration trace mode that records synchronized controller, ADS1115, and BMS samples while the robot is armed and motor activity is present.

**Architecture:** Keep trace orchestration in [biba-controller/main.py](biba-controller/main.py): it already sees RC input, computed motor outputs, current-sense samples, and the latest BMS snapshot in one loop. Extend [biba-controller/bms/poller.py](biba-controller/bms/poller.py) to expose the timestamp of the last successful BMS update, extend the ADS1115 current-sense path to preserve raw sample details, and add a JSONL trace writer that logs only during armed activity and a short post-roll window.

**Tech Stack:** Python 3.10, pytest, JSONL logging, monotonic timestamps, ADS1115 via `smbus2`, Daly BMS poller thread.

---

### Task 1: Lock BMS freshness semantics in tests

**Files:**
- Modify: `tests/test_bms_poller.py`
- Modify: `biba-controller/bms/poller.py`

**Step 1: Write the failing test**

Add tests that prove:
- `BMSPoller` exposes the latest successful sample timestamp
- the timestamp changes when a new sample arrives
- the main thread can read the state and timestamp atomically enough for trace use

Example test:

```python
def test_bms_poller_exposes_latest_state_timestamp() -> None:
    poller = BMSPoller(FakeBMS([BatteryState(voltage=24.0, current=1.5, soc=80.0)]), interval_s=10.0)
    poller._run_one_iteration_for_test()

    assert poller.latest_state is not None
    assert poller.latest_state_timestamp_s is not None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_bms_poller.py -q`

Expected: FAIL because `BMSPoller` does not expose a timestamp today.

**Step 3: Write minimal implementation**

In `biba-controller/bms/poller.py`:
- store the monotonic timestamp of the last successful `read_state()`
- expose it through a property or snapshot helper
- keep locking semantics simple and explicit

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_bms_poller.py -q`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 2: Preserve raw ADS1115 observables in tests and code

**Files:**
- Modify: `tests/test_current_sense.py`
- Modify: `biba-controller/motors/current_sense.py`

**Step 1: Write the failing test**

Add tests that require the current-sense reader to expose per-side sample detail including:
- raw ADC count
- measured voltage
- calibrated current
- validity

Example test:

```python
def test_ads1115_reader_returns_raw_voltage_and_current() -> None:
    bus = FakeBus(read_values=[0x4000, 0x2000])
    reader = ADS1115MotorCurrentReader(...)

    left, right = reader.read_currents()

    assert left.raw_adc == 0x4000
    assert left.voltage_v == pytest.approx(2.048)
    assert left.valid is True
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_current_sense.py -q`

Expected: FAIL because the current sample model does not currently preserve raw ADC or voltage.

**Step 3: Write minimal implementation**

In `biba-controller/motors/current_sense.py`:
- extend the current sample data model or add a richer trace sample wrapper
- keep the existing limiter/telemetry-facing current path working
- ensure invalid reads still produce a safe invalid sample

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_current_sense.py -q`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 3: Add failing config-surface tests for calibration trace mode

**Files:**
- Modify: `tests/test_config.py`
- Modify: `biba-controller/config.py`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `docs/wiring.md`

**Step 1: Write the failing test**

Add tests requiring new config values for:
- trace enable flag
- trace output path
- post-roll seconds
- optional trace sample interval or max rate if introduced

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_config.py -q -k "trace or current_sense"`

Expected: FAIL because the trace-specific configuration does not exist yet.

**Step 3: Write minimal implementation**

In `biba-controller/config.py`:
- add defaults for the calibration trace env surface

In `docker-compose.yml`, `README.md`, and `docs/wiring.md`:
- document the feature as off-by-default and meant for calibration sessions

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_config.py -q -k "trace or current_sense"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 4: Add failing tests for trace gating and JSONL shape

**Files:**
- Modify: `tests/test_main.py`
- Modify: `biba-controller/main.py`

**Step 1: Write the failing test**

Add focused tests that prove:
- no trace file is written when the feature is disabled
- trace writes while armed and motor activity is present
- trace continues during configured post-roll after activity stops
- trace does not require `bms_current_a != 0`
- each JSONL line includes the required keys, including `bms_age_s`

Example test:

```python
def test_calibration_trace_logs_armed_motor_activity_even_with_zero_bms_current(tmp_path: Path) -> None:
    ...
    assert record["armed"] is True
    assert record["bms_current_a"] == 0.0
    assert record["left_duty"] > 0.0
```

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_main.py -q -k "trace or calibration or bms_age"`

Expected: FAIL because no calibration trace writer exists yet.

**Step 3: Write minimal implementation**

In `biba-controller/main.py`:
- add helper(s) to decide when trace logging is active
- generate JSON-serializable sample dictionaries
- append JSONL records to the configured file path
- compute `bms_age_s` from the poller timestamp
- include current motor command state and ADS1115 sample detail

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_main.py -q -k "trace or calibration or bms_age"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 5: Verify existing telemetry behavior stays intact

**Files:**
- Modify: `tests/test_telemetry.py`
- Modify: `tests/test_main.py`

**Step 1: Write the failing regression test**

Add or update tests proving:
- normal CRSF battery telemetry still uses BMS current as before
- system telemetry still sends left/right motor current fields
- enabling trace mode does not alter telemetry payload semantics

**Step 2: Run test to verify it fails if behavior drifted**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_telemetry.py tests/test_main.py -q -k "telemetry or current"`

Expected: PASS initially if no regression was introduced by the tests alone, otherwise FAIL and expose the drift.

**Step 3: Write minimal implementation**

Only if needed, adjust the implementation so trace mode is observational and does not change existing telemetry outputs.

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests/test_telemetry.py tests/test_main.py -q -k "telemetry or current"`

Expected: PASS.

**Step 5: Commit**

Do not commit unless explicitly requested.

### Task 6: Add a small offline trace-inspection helper

**Files:**
- Create: `scripts/current_trace_summary.py`
- Modify: `tests/test_vcp_capture.py` or create a focused new test file if a cleaner location exists
- Modify: `README.md`

**Step 1: Write the failing test**

Add a focused test for a helper that:
- reads the JSONL trace file
- prints record count, time span, and basic stats for BMS age and left/right current fields

**Step 2: Run test to verify it fails**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests -q -k "current_trace_summary"`

Expected: FAIL because the helper does not exist yet.

**Step 3: Write minimal implementation**

Create `scripts/current_trace_summary.py` as a lightweight inspection tool, not a full fitter. Keep it dependency-light so it can run on the repo venv.

**Step 4: Run test to verify it passes**

Run: `cd /home/builder/biba && /home/builder/biba/.venv/bin/python -m pytest tests -q -k "current_trace_summary"`

Expected: PASS.