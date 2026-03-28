# RC Mute Channel and Lua Status Icons — Design Document

## Summary

Add an RC-controlled mute mode on `CH6` that suppresses normal buzzer and voice playback while leaving hardware SOS/beacon playback untouched. Expose the runtime sound state to the Lua telemetry screen by rendering compact header letters: `A` for armed, `M` for mute, `B` for beacon, and a charging icon when battery current indicates charging.

## Problem

The controller currently plays startup, connection, arm, disarm, failsafe, and low-voltage sounds whenever those events occur. That is useful for normal operation, but it also prevents quiet driving or debugging sessions where the operator wants telemetry and control without audio. The radio screen also cannot show at a glance whether the robot is armed, muted, or beaconing.

## Goals

1. Add a dedicated mute RC channel with a default of `CH6`.
2. Mute ordinary sounds consistently across synchronous and asynchronous voice/tone paths.
3. Preserve SOS playback, including the beacon-triggered hardware path.
4. Show `A`, `M`, and `B` together in the Lua header when those states are active.
5. Show a charging indicator in the same header only while the battery is charging.
6. Preserve the existing telemetry mappings for CPU, RAM, and wheel currents.

## Non-Goals

- Muting drive control or telemetry transmission.
- Reassigning the existing beacon channel.
- Introducing a new CRSF frame type or additional radio sensors.
- Changing SOS audio content or beacon timing.

## Design

### 1. RC mute state in controller runtime

Add `CH_MUTE = 6` to config and derive `mute_active` from the corresponding RC channel using the same threshold style already used for arm and manual beacon toggles. The controller loop in `main.py` will compute this state once per received channel frame.

Mute only blocks ordinary audio triggers:

- startup voice or melody
- connected and disconnected sounds
- arm and disarm sounds
- failsafe voice or tone
- low-voltage voice or tone
- RC melody playlist playback

SOS remains exempt. The existing `buzzer.sos_beacon()` call path stays unchanged so the robot can still emit a recovery beacon even while muted.

### 2. Centralized sound gating

Instead of sprinkling `if not mute_active` checks around every call site, add small helper functions in `main.py` that wrap grouped voice playback, async buzzer-method playback, and named melody playback. Those helpers will accept `mute_active` and an explicit `allow_when_muted` flag for the SOS-only exemption path if needed later.

This keeps the control loop readable and makes the mute behavior testable at a narrow API boundary.

### 3. Status-bit encoding in battery telemetry

The Lua screen already consumes all GPS-derived fields:

- `GSpd` for CPU
- `Sats` for RAM
- `Hdg` for left motor current
- `Alt` for right motor current

Because those fields are occupied, encode sound and arm state in the already-overloaded battery `capacity_mah` field. Today it carries only a direction code (`IDLE`, `CHG`, `DIS`). Extend that to a bitmask:

- low 2 bits: battery direction code (`0 = IDLE`, `1 = CHG`, `2 = DIS`)
- bit 2: armed flag
- bit 3: mute flag
- bit 4: beacon flag

This preserves the existing Lua battery-direction behavior while adding three independent status flags without changing the CRSF payload shape.

### 4. Lua header rendering

Update `lua/SCRIPTS/TELEMETRY/biba.lua` to decode the extended `Capa/Mah/mAh` bitmask. Keep `read_battery_direction()` behavior compatible by masking the low 2 bits, but stop rendering `CHG/DIS` text in the body because it is noisy and redundant once the header carries the charging state. Add a helper that decodes `A`, `M`, and `B` from status bits and appends a charging marker only when the low 2 bits indicate `CHG`.

Render the letters in the existing top header row, next to the quality/source text. Multiple letters may appear simultaneously. The charging marker appears only for charging and is absent while idle or discharging.

### 5. Testing strategy

Use TDD across three layers:

1. `tests/test_main.py` for runtime mute gating and status-bit composition.
2. `tests/test_telemetry.py` for battery frame packing with the new status bitmask.
3. `tests/test_lua_telemetry_screen.py` for Lua decoding, charging-icon rendering, and removal of the old `CHG/DIS` body labels.

The tests should prove both muted and unmuted behavior, and should explicitly cover the invariant that SOS is not blocked.

## Error Handling and Compatibility

- If `CH_MUTE` is out of range for a given receiver frame, the controller treats mute as inactive, matching the current `_get_channel()` fallback behavior.
- Existing Lua installs that do not receive the new controller telemetry will continue to show no status letters.
- Existing battery direction bits remain stable because direction decoding continues to use only the low 2 bits.

## Deployment Notes

The feature needs environment/documentation updates so deployed robots can override `CH_MUTE` if needed. No compose-structure change is required because the feature reuses the existing controller and telemetry links.