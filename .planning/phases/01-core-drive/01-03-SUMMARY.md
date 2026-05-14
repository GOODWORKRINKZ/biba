---
phase: 01-core-drive
plan: 03
type: tdd
subsystem: testing
tags: [tdd, unity, ramp, native-test]
requires: ["01-01"]
provides: ["firmware/test/test_ramp/test_main.c"]
tech-stack:
  added: []
  patterns: [unity-test-standalone, biba_test_support]
key-files:
  created:
    - firmware/test/test_ramp/test_main.c
  modified:
    - firmware/src/app/ramp.c
    - firmware/include/biba_config.h
    - firmware/platformio.ini
key-decisions:
  - "Pre-existing native_test build broken (main_rp2040.cpp pulled in Arduino.h, melody.c had undefined HAL refs) — fixed by adding exclusions to common build_src_filter"
  - "biba_config.h guarded target_config.h include behind #ifndef BIBA_NATIVE_TEST to allow ramp.c in native build"
  - "ramp.c needed #include <stddef.h> for NULL — added"
requirements-completed:
  - MOTOR-03
test-results:
  command: "pio test -e native_test"
  result: "39/39 PASS (all 4 suites)"
  ramp-tests: "8/8 PASS"
duration: 12 min
completed: 2026-05-14T00:00:00Z
---

# Phase 1 Plan 03: TDD Test Suite Summary

Created Unity test suite for `biba_ramp_update`. Fixed pre-existing native_test build issues that prevented any native tests from running. 39/39 tests pass.

**Duration:** ~12 min | **Files created:** 1 | **Files modified:** 3

**Next:** Wave 3 Plan 01-04 (wire ramp + SSR into mode_standalone.c)

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Create test_ramp/test_main.c with 8 Unity test cases | `93a5b99` | test_main.c |
| Bug fixes | Fix native_test build (main_rp2040.cpp, melody.c, biba_config.h guard, NULL) | `93a5b99` | platformio.ini, biba_config.h, ramp.c |

## Test Cases

| # | Test | Coverage |
|---|------|----------|
| 1 | `test_init_starts_at_zero` | biba_ramp_init zero state |
| 2 | `test_reset_zeroes_running_state` | biba_ramp_reset clears current + hold |
| 3 | `test_dt_zero_returns_current_unchanged` | dt<=0 guard (Pitfall 1) |
| 4 | `test_acceleration_toward_positive_target` | BIBA_RAMP_ACCEL_RATE step |
| 5 | `test_deceleration_from_positive` | BIBA_RAMP_DECEL_RATE step |
| 6 | `test_direction_change_uses_reverse_decel_rate` | direction change path (0.05 not 0.2 or 0.1) |
| 7 | `test_direction_change_triggers_zero_hold` | zero-hold arm + hold freeze |
| 8 | `test_clamp_output_to_unit` | output clamp ±1.0 |

## Bug Fixes Applied

Pre-existing native_test build was completely broken:

1. **`main_rp2040.cpp` included `Arduino.h`** → added `-<main_rp2040.cpp>` to common `build_src_filter`
2. **`melody.c` referenced HAL audio symbols** → added `-<app/melody.c>` to filter
3. **`biba_config.h` included `target_config.h` unconditionally** → wrapped in `#ifndef BIBA_NATIVE_TEST / #else / #endif` with minimal fallback defaults
4. **`ramp.c` used `NULL` without `<stddef.h>`** → added `#include <stddef.h>`

## Deviations from Plan

- Additional scope: fixed 4 pre-existing native_test build issues not mentioned in plan. All fixes necessary to achieve `pio test -e native_test` exit 0.

## Self-Check: PASSED

- [x] `firmware/test/test_ramp/test_main.c` exists with ≥80 lines (140 lines)
- [x] 8 RUN_TEST calls in run_all()
- [x] `pio test -e native_test -f test_ramp` exits 0 — 8/8 PASSED
- [x] `pio test -e native_test` exits 0 — 39/39 PASSED (all suites)
- [x] Commit: `93a5b99`
