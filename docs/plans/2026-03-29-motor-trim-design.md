# Motor Trim Design

## Goal

Add a persistent operator-tuned left/right motor trim mode so the robot can compensate for wheel, motor, and driver mismatch without reflashing or editing config files.

## Problem

With identical PWM commands, the two sides of the drivetrain do not produce identical physical wheel speed. The resulting drift is visible during straight driving, especially at low and medium throttle. Today there is no operator-facing calibration path, so compensation requires code or config changes and cannot be tuned in the field.

## Goals

1. Enter a dedicated trim mode from the transmitter while the robot is disarmed.
2. Use `CH9` live as the trim source during trim mode so the operator can drive and evaluate the balance immediately.
3. Confirm and persist the chosen trim value with the same 5-second stick gesture used to enter trim mode.
4. Reuse the saved trim automatically on later boots.
5. Show a `t` badge on the Lua telemetry screen while trim mode is active.
6. Keep the correction bounded to 20% while preserving full `CH9` analog resolution.

## Non-Goals

- Adding a numeric trim readout to the Lua screen.
- Creating a new CRSF telemetry frame type.
- Changing the steering mix model.
- Calibrating absolute wheel RPM from sensors.

## Design

### 1. Trim mode gesture and state

The controller runtime in [biba-controller/main.py](biba-controller/main.py) will track three related states:

- `trim_mode_active`: whether the controller is currently taking trim from `CH9`
- `saved_trim`: the persisted correction loaded at startup
- `gesture_started_at`: when the trim-entry or trim-confirm gesture began

Trim mode becomes active only when all of these are true:

- the platform is disarmed
- the first four RC channels are high
- that condition remains true for 5 seconds continuously

Once active, the same gesture while still disarmed serves as confirmation. Confirmation saves the current `CH9`-derived trim, exits trim mode, and makes that value the new runtime default.

### 2. Trim source and scaling

`CH9` is treated as a continuous normalized channel in the range `[-1.0, 1.0]`. The full analog value is used for precision; there is no bucketization or rounding.

The effective trim is:

`effective_trim = channel_9_value * 0.20`

This means:

- full negative `CH9` becomes `-0.20`
- centered `CH9` becomes `0.0`
- full positive `CH9` becomes `+0.20`

Outside trim mode the controller ignores live `CH9` and uses the persisted `saved_trim` value directly.

### 3. How trim is applied to motor output

The correction is applied after drive mixing and ramping, using the already-computed left and right duties, but before the duties are sent to the motor driver.

The chosen model is one-sided reduction rather than symmetric boost. This avoids the impossible case where one side tries to exceed 100% duty at full throttle.

Behavior:

- `effective_trim == 0.0`: no correction
- `effective_trim > 0.0`: reduce the right-side command by up to 20%
- `effective_trim < 0.0`: reduce the left-side command by up to 20%

This keeps the drivetrain physically honest at high throttle while still giving the operator enough range to compensate for mismatch.

### 4. Persistence model

Persist trim in a small JSON settings file stored on the controller through the existing container volume mount. The file will contain:

- `trim`
- `updated_at`

Load behavior:

- if the file exists and contains a valid numeric trim, use it
- if the file is missing, default to `0.0`
- if the file is corrupt or unreadable, log a warning and fall back to `0.0`

Writes should be atomic: write a temporary file and rename it into place.

### 5. Telemetry and Lua UI

The existing battery telemetry status-bit overload already carries arm, mute, and beacon state. Extend that bitmask with one additional trim-mode flag.

While trim mode is active:

- the controller sets the new trim bit in the battery telemetry status field
- the Lua script in [lua/SCRIPTS/TELEMETRY/biba.lua](lua/SCRIPTS/TELEMETRY/biba.lua) decodes the bit and appends a `t` badge alongside the existing local badges

The badge indicates mode only. The screen does not need to display the numeric trim value.

## Testing Strategy

Use TDD at three layers:

1. [tests/test_main.py](tests/test_main.py)
   - trim gesture detection
   - trim mode runtime behavior
   - persistence fallback and save behavior
   - trim application math
   - telemetry status-bit composition

2. [tests/test_config.py](tests/test_config.py)
   - config surface for trim path, channel, duration, and max correction defaults if those values are added to runtime config

3. [tests/test_lua_telemetry_screen.py](tests/test_lua_telemetry_screen.py)
   - Lua trim badge decoding from telemetry status bits
   - compact and wide header use of the shared badge helper

## Risks and Mitigations

- False trim-mode entry while driving: prevented by requiring disarm and a 5-second hold.
- Broken settings file causing startup failure: avoided by warning-and-default behavior.
- Full-throttle saturation breaking the correction model: avoided by using one-sided reduction instead of symmetric boost.
- UI lag between mode change and badge display: minimized by reusing the existing periodic telemetry path.

## Deployment Notes

The feature needs a persistent settings path exposed through the controller container volume. No new services or protocol changes are required.