# Current Sense Calibration Trace Design

## Goal

Add a controller-side calibration trace mode that records synchronized motor-control, ADS1115, and BMS telemetry samples so left and right wheel current can later be calibrated against the slower total pack current reported by the Daly BMS.

## Problem

The robot already has three relevant signal paths, but they are not currently captured together in a way that supports calibration:

- ADS1115 channels can be read quickly in the control loop.
- Left and right motor duties are known in the controller at loop time.
- Daly BMS current is available only through a slower background poller and can arrive late relative to motor activity.

The existing `Battery telemetry` INFO log is too sparse for calibration because it is rate-limited to 5 seconds and does not include ADS1115 raw values, duty outputs, or BMS sample freshness. If trace logging starts only when BMS current is nonzero, the beginning of many maneuvers will be missed because the BMS sample can lag behind wheel activity by about 1 second or more.

## Goals

1. Capture calibration data only while the platform is armed and motor activity is happening.
2. Preserve enough context to correlate fast ADS1115 samples with slower BMS samples offline.
3. Record BMS freshness explicitly so delayed BMS updates are visible in the dataset.
4. Keep the first iteration focused on logging, not online fitting or automatic current limiting.
5. Store trace samples in a machine-readable format suitable for offline statistics and regression.

## Non-Goals

- Automatic runtime fitting of current coefficients.
- Replacing the BMS current used in normal CRSF battery telemetry.
- Enabling motor current limiting during the first calibration phase.
- Inferring true physical wheel torque or RPM.
- Estimating Raspberry Pi baseline current from datasheet values alone.

## Design

### 1. Trace activation and logging gate

Introduce a dedicated calibration trace mode controlled by env configuration.

The trace should not start only when BMS current becomes nonzero. Instead, a sample is eligible for logging when all of these are true:

- the platform is armed
- calibration trace mode is enabled
- motor activity is present now, or the controller is within a short post-roll window after recent motor activity

Motor activity should be defined by any of the following:

- `abs(throttle)` above the existing deadband
- `abs(steering)` above the existing deadband
- nontrivial left or right duty output
- nonzero valid ADS1115-derived current estimate on either side

This design intentionally uses motor activity as the trigger and treats BMS as a slower reference signal. That avoids dropping the beginning of a maneuver when the BMS sample arrives late.

### 2. Trace sample format

Write one JSON object per line to a JSONL file on the persistent controller volume. Each line represents a controller-side snapshot created from one main-loop iteration.

Each sample should include:

- session identity
  - `session_id`
  - `sample_index`
- time
  - `monotonic_s`
  - `wall_time_iso`
- control state
  - `armed`
  - `raw_throttle`
  - `filtered_throttle`
  - `steering`
  - `control_active`
- motor command state
  - `requested_left`
  - `requested_right`
  - `limited_left`
  - `limited_right`
  - `trimmed_left`
  - `trimmed_right`
  - `left_duty`
  - `right_duty`
- current sense
  - `left_current_valid`
  - `right_current_valid`
  - `left_current_a`
  - `right_current_a`
  - `left_voltage_v`
  - `right_voltage_v`
  - `left_raw_adc`
  - `right_raw_adc`
  - channel metadata for left and right ADS1115 channel selection
- BMS snapshot
  - `bms_current_a`
  - `bms_voltage_v`
  - `bms_soc_pct`
  - `bms_present`
  - `bms_sample_monotonic_s`
  - `bms_age_s`
- diagnostic context
  - `mute_active`
  - `beacon_active`
  - `trim_mode_active`

The log file path should be configurable and default under `/data`, so captures survive container restarts and can be copied off the robot later.

### 3. BMS freshness tracking

The current `BMSPoller` only exposes `latest_state`. Extend it so the control loop can also obtain when that state was last updated in the controller process.

The poller should track:

- latest `BatteryState`
- monotonic timestamp of the last successful read

The main loop then computes:

$$
bms\_age\_s = now\_monotonic - bms\_sample\_monotonic
$$

This is essential because offline analysis must distinguish between:

- a fresh BMS sample that likely corresponds to the current wheel activity
- a stale BMS sample still reflecting the previous operating point

### 4. ADS1115 raw sample visibility

The current current-sense reader returns only calibrated amps and validity. For calibration trace mode, that is insufficient because the offline workflow needs the original observables.

Extend the current-sense model so the controller can log, for each wheel channel:

- raw ADC counts
- interpreted voltage
- calibrated current
- validity

The runtime may still use calibrated current for telemetry fields, but the trace file must preserve raw counts so future fitting can be repeated without recollecting data.

### 5. Post-roll behavior

Add a short configurable post-roll window, for example 2 to 3 seconds, after motor activity drops to zero.

Reason:

- the BMS sample can lag behind actual drive activity
- the user intends to hold each maneuver long enough to observe this delay
- post-roll helps capture the delayed BMS decay after wheel activity has ended

The trace sample should include whether it is inside active drive or post-roll so offline analysis can segment maneuvers cleanly.

### 6. Baseline current model

Do not subtract a hardcoded Raspberry Pi Zero 2W current value in the controller.

Instead, design the trace so offline calibration can fit a baseline term:

$$
I_{bms}(t) \approx I_{left}(t) + I_{right}(t) + I_{base}
$$

where $I_{base}$ absorbs:

- Raspberry Pi consumption
- Wi-Fi load
- ELRS receiver load
- BMS transport overhead
- other always-on electronics and conversion losses

This is more defensible than using only a spec-sheet current because the operating baseline changes with the real robot configuration.

### 7. Offline analysis target

The first phase ends with trace generation, not online fitting. The intended offline workflow is:

1. record long-enough maneuvers for idle, left-only, right-only, and both-wheel drive
2. filter trace samples by `armed`, control activity, and acceptable `bms_age_s`
3. estimate per-side offset and gain against the delayed BMS reference
4. fit a baseline term so:

$$
I_{left} + I_{right} + I_{base} \approx I_{bms}
$$

Once the trace proves stable, a later phase can decide whether to:

- compute coefficients offline and write them into env config
- or add a runtime fitting path

## Testing Strategy

Use TDD in focused slices:

1. [tests/test_bms_poller.py](tests/test_bms_poller.py)
   - latest-state timestamp is updated on successful poll
   - timestamp clears or remains unchanged on failures according to the chosen semantics

2. [tests/test_current_sense.py](tests/test_current_sense.py)
   - ADS1115 sample structure exposes raw ADC, voltage, current, and validity
   - invalid reads propagate correctly into the trace layer

3. [tests/test_main.py](tests/test_main.py)
   - trace gate requires armed state plus activity or post-roll
   - delayed BMS sample age is logged correctly
   - JSONL samples include expected fields
   - no trace is written when the feature is disabled

4. Optional focused offline test fixture
   - verify that a synthetic trace can be parsed into a DataFrame-like structure or equivalent record list if an offline helper script is introduced

## Risks and Mitigations

- Excessive log volume: mitigate with trace mode off by default and a configurable sample rate or write gate.
- Misinterpreting stale BMS as synchronous truth: mitigate by always logging `bms_age_s` and the BMS sample timestamp.
- Losing the start of a maneuver: mitigate by gating on armed motor activity, not BMS nonzero current.
- Re-fitting becoming impossible later: mitigate by logging raw ADS1115 counts, not just calibrated currents.
- Overfitting baseline from spec-sheet assumptions: mitigate by fitting `I_base` from the trace dataset instead of hardcoding Pi current.

## Deployment Notes

The feature should be off by default. Runtime config should expose:

- trace enable flag
- JSONL output path
- post-roll duration
- optional trace rate limit if needed

No robot-side manual repo edits should be required. Once implemented, deployment should go through the usual repository update flow.