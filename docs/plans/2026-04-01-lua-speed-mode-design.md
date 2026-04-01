# Lua Speed Mode Design

## Goal

Add a three-speed operator mode to the EdgeTX telemetry Lua script so `ch6` selects one of three drive range limits:

- speed `1`: `1/3` stick range
- speed `2`: `2/3` stick range
- speed `3`: full stick range

The active speed number must also be shown in the existing status badge row next to the arm, beacon, and mute badges.

## Current Problem

The Lua script currently renders wheel activity from raw `ch2` and `ch4` values with a fixed full-range mapping in `read_drive()`. That means the operator has no transmitter-side low-speed mode for precise indoor driving or safe testing. The status row also has no indication of which operator speed profile is currently active.

## Decision

Use `ch6` as a three-position speed selector inside `lua/SCRIPTS/TELEMETRY/biba.lua`.

The selected mode will map to configurable scale constants:

- slow -> `1/3`
- medium -> `2/3`
- fast -> `1.0`

The mode number `1`, `2`, or `3` will be appended to the local status badge list so it appears in the same rounded badge style already used for `a`, `b`, and `m`.

## Input Scaling Rule

Only the operator stick inputs are scaled.

Specifically:

1. Read raw throttle from `ch2`
2. Read raw steering from `ch4`
3. Read speed mode from `ch6`
4. Multiply only `thr` and `str` by the mode scale
5. Convert the scaled values to normalized `-1..1`
6. Apply the existing wheel mix

This means the visualized drive intent becomes:

$$
thr_{scaled} = thr \cdot k
$$

$$
str_{scaled} = str \cdot k
$$

$$
left = clamp\left(\frac{thr_{scaled}}{1024} + \frac{str_{scaled}}{1024}, -1, 1\right)
$$

$$
right = clamp\left(\frac{thr_{scaled}}{1024} - \frac{str_{scaled}}{1024}, -1, 1\right)
$$

## Trim Handling

Trim must not be scaled down by the selected speed mode.

That rule is important because the robot-side motor trim is an alignment correction, not an operator speed preference. Scaling only the stick travel preserves precise low-speed control while keeping trim authority stable across all three speed modes.

In practice, the Lua screen should only scale the operator input that it visualizes. It should not try to re-implement or attenuate the controller-side trim behavior.

## Mode Detection

Introduce explicit constants for the selector channel, mode scales, and position thresholds.

Recommended constants:

- `APP_SPEED_MODE_CHANNEL = "ch6"`
- `APP_SPEED_MODE_SLOW_SCALE = 1 / 3`
- `APP_SPEED_MODE_MEDIUM_SCALE = 2 / 3`
- `APP_SPEED_MODE_FAST_SCALE = 1.0`
- `APP_SPEED_MODE_LOW_THRESHOLD`
- `APP_SPEED_MODE_HIGH_THRESHOLD`

The thresholds should divide the three-position switch into:

- below low threshold -> speed `1`
- between thresholds -> speed `2`
- above high threshold -> speed `3`

This keeps the behavior configurable for real transmitter output values instead of hard-coding exact switch numbers.

## UI Rendering

The active speed must appear in the existing status badge row.

The intended rendering shape is:

- arm active, beacon active, medium speed -> `a b 2`
- arm active, mute active, slow speed -> `a m 1`

The speed indicator should be implemented as a normal badge label, not as a separate header text element. That keeps the compact and wide layouts visually consistent because both already call the shared status-badge drawing helpers.

## Runtime Shape

Add two small helpers:

1. one helper that reads `ch6` and returns the active speed number and its scale
2. one helper that returns the speed badge label for the local status row

Then update:

- `read_drive()` to use the selected scale
- `read_local_status_badges()` to append the speed number badge

No other drawing code should need structural changes because both compact and wide headers already render an arbitrary status badge list.

## Testing Strategy

Add focused tests in `tests/test_lua_telemetry_screen.py` that verify:

1. the Lua file declares the new speed-mode constants
2. a speed-mode helper exists and reads `ch6`
3. the helper returns all three scales `1/3`, `2/3`, and `1.0`
4. `read_drive()` uses the helper and scales `thr` and `str`
5. `read_local_status_badges()` adds the speed number badge

These tests should stay at the current string-structure level used by the existing Lua telemetry tests.

## Non-Goals

- changing controller-side motor trim behavior
- changing arm, beacon, or mute channel semantics
- redesigning the header layout beyond adding one extra badge
- changing deployment, Docker, or controller runtime code