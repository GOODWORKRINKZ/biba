---
phase: 01-core-drive
plan: 01
subsystem: motor-control
tags: [ramp, speed-ramp, motor, c-port]
requires: []
provides: [biba_ramp_t, biba_ramp_init, biba_ramp_reset, biba_ramp_update]
affects: [firmware/src/modes/mode_standalone.c]
tech-stack:
  added: []
  patterns: [struct-null-guard, failsafe-analog]
key-files:
  created:
    - firmware/src/app/ramp.h
    - firmware/src/app/ramp.c
  modified:
    - firmware/include/biba_config.h
key-decisions:
  - "No math.h dependency — abs computed with ternary expressions"
  - "BIBA_RAMP_ZERO_HOLD_MS stored as uint, converted to float seconds in update"
  - "dt <= 0 guard is first statement of biba_ramp_update (Pitfall 1)"
requirements-completed:
  - MOTOR-03
duration: 8 min
completed: 2026-05-14T00:00:00Z
---

# Phase 1 Plan 01: SpeedRamp C Port Summary

Port of `biba-controller/motors/ramping.py::SpeedRamp` to C as `firmware/src/app/ramp.h` + `ramp.c`, with four `BIBA_RAMP_*` tuning constants in `biba_config.h`.

**Duration:** ~8 min | **Tasks:** 2 | **Files created:** 2 | **Files modified:** 1

**Next:** Ready for Plan 01-03 (TDD test suite for ramp)

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | ramp.h struct + declarations + biba_config.h constants | `964fdf1` | ramp.h, biba_config.h |
| 2 | ramp.c SpeedRamp algorithm implementation | `368c507` | ramp.c |

## What Was Built

`biba_ramp_t` struct with `current` and `hold_remaining_s` fields. Three functions:
- `biba_ramp_init()` — zero-initialize
- `biba_ramp_reset()` — D-04 hard reset (emergency stop)
- `biba_ramp_update(r, target, dt)` — faithful C port of `SpeedRamp.update`:
  - `dt <= 0` guard (Pitfall 1)
  - Target clamp to [-1, 1]
  - Zero-hold timer (150 ms default)
  - Direction-change path uses `BIBA_RAMP_REVERSE_DECEL_RATE` (0.5 u/s)
  - Same-sign path uses `BIBA_RAMP_ACCEL_RATE` / `BIBA_RAMP_DECEL_RATE` (2.0 u/s each)
  - Final output clamp

Constants in `biba_config.h` with `#ifndef` guards (match Python `config.py` defaults):
- `BIBA_RAMP_ACCEL_RATE` = 2.0f
- `BIBA_RAMP_DECEL_RATE` = 2.0f
- `BIBA_RAMP_REVERSE_DECEL_RATE` = 0.5f
- `BIBA_RAMP_ZERO_HOLD_MS` = 150u

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- [x] `firmware/src/app/ramp.h` exists with `biba_ramp_t` struct and 3 declarations
- [x] `firmware/src/app/ramp.c` implements all 3 functions (82 lines)
- [x] `biba_config.h` contains all 4 `BIBA_RAMP_*` constants with `#ifndef` guards
- [x] `dt <= 0` guard is first statement of `biba_ramp_update`
- [x] Direction-change uses `BIBA_RAMP_REVERSE_DECEL_RATE`
- [x] No `math.h` / `fabsf` dependency
- [x] 2 production commits: `964fdf1`, `368c507`
