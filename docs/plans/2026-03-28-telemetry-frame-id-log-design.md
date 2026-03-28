# Telemetry Frame ID Log Correlation Design

## Goal

Add a shared `frame_id` marker that appears in both robot logs and app-side Lua logs so telemetry observations can be matched exactly across the CRSF link without changing the visible telemetry UI.

## Current State

The controller can log precise battery telemetry timing around `_send_battery_telemetry()`, but those logs stop at the robot side. The Lua telemetry screen reads CRSF-exposed sensor values such as `Curr`, `VFAS`, and `Capa`, but it has no shared identifier that lets us prove which robot-side send corresponds to which app-side observation.

Current diagnosis shows controller-side battery telemetry delay is about one second and aligns with `BMS_POLL_INTERVAL_S=1.0`. Any additional delay visible on the transmitter must therefore be downstream of the robot-side send path. We need a correlation marker to prove that precisely.

## Constraints

- Do not change the telemetry UI.
- Do not break current battery telemetry semantics for voltage, current, SOC, or direction.
- The marker only needs to exist in logs, not on-screen.
- The implementation should stay lightweight enough for routine short diagnostics.

## Options Considered

### Option A: Reuse an existing battery telemetry field

Pack `frame_id` into an already used battery field such as current or capacity.

Pros:
- no extra telemetry transport path

Cons:
- breaks or complicates current field semantics
- makes existing diagnostics harder to trust
- creates unnecessary coupling between logging needs and displayed battery data

### Option B: Add `frame_id` to a separate service telemetry field

Transmit a rolling `frame_id` through a separate CRSF-exposed sensor path that Lua can read for logging, while leaving visible battery telemetry unchanged.

Pros:
- clean separation from battery semantics
- exact correlation between robot and app logs
- no UI changes required

Cons:
- requires a small telemetry-path extension
- needs a safe sensor slot or helper frame encoding

### Option C: Match only by timestamps and events

Keep using local timestamps on both ends and correlate by approximate timing.

Pros:
- no protocol changes

Cons:
- this is already the current weak point
- not reliable under radio refresh jitter or display lag

## Recommendation

Use Option B.

Introduce a monotonically increasing `frame_id` on the controller side, incremented for each transmitted battery telemetry sample. Send it through a separate telemetry path that Lua can read, and log it on both ends. This preserves current telemetry behavior while giving us an exact join key across the radio link.

## Architecture

### Controller Side

Add a battery telemetry frame counter in the controller process. Each call to `_send_battery_telemetry()` assigns the next `frame_id` to that battery sample and includes it in robot-side diagnostic logging.

Robot log lines should include at least:
- `frame_id`
- trace stage (`consume` / `send`)
- monotonic timestamp
- battery current and voltage values already being logged

### Transport

Carry `frame_id` through a service telemetry field that does not alter the existing battery payload semantics. The first implementation should prefer reusing a safe auxiliary CRSF sensor slot already exposed through the current telemetry path if one exists cleanly; otherwise add a dedicated helper path with minimal surface area.

The marker can be a rolling integer counter. It does not need wall-clock meaning; it only needs to match the same sample across logs.

### Lua Side

Lua reads the `frame_id` sensor alongside existing telemetry sensors. It does not render it on-screen. Instead, when app-side diagnostic logging is enabled, Lua emits log lines containing:
- `frame_id`
- local `getTime()` value
- current battery sensor readings observed at that moment

### Logging Scope

This should be diagnostic-oriented rather than permanently noisy. The logging can be guarded behind the existing trace mode or a closely related diagnostic flag so normal operation remains quiet.

## Risks

- Choosing the wrong telemetry carrier could collide with an existing or future sensor meaning.
- Lua-side logging capabilities may be limited by the transmitter environment, so the exact sink may need to align with what EdgeTX/OpenTX actually exposes for script diagnostics.
- A small rolling counter can wrap; logs must tolerate that and match within a bounded window.

## Success Criteria

- the robot logs include a `frame_id` for each traced battery telemetry sample
- the transmitter-side Lua diagnostics include the same `frame_id`
- the same sample can be matched exactly across both logs without using approximate timestamps
- visible telemetry UI remains unchanged