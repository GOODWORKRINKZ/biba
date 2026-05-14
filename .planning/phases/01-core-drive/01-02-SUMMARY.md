---
phase: 01-core-drive
plan: 02
subsystem: hal
tags: [ssr, gpio, power-rail, bts7960]
requires: []
provides: [biba_hal_ssr_init, biba_hal_ssr_set, BIBA_PIN_SSR_GPIO]
affects: [firmware/src/modes/mode_standalone.c]
tech-stack:
  added: []
  patterns: [gpio-out-init-low, hal-stub-pattern]
key-files:
  modified:
    - firmware/targets/RPICO_RP2040/target.h
    - firmware/src/hal/biba_hal.h
    - firmware/src/hal/biba_hal.c
    - firmware/src/hal/biba_hal_rp2040.c
key-decisions:
  - "biba_hal_ssr_init() called from biba_hal_init() — guarantees LOW before any mode code"
  - "STM32 stubs use (void)enabled to suppress unused-parameter warning"
  - "gpio_put(BIBA_PIN_SSR_GPIO, 0) in init — no gpio_set_function (plain GPIO OUT)"
requirements-completed:
  - D-09
  - D-13
duration: 5 min
completed: 2026-05-14T00:00:00Z
---

# Phase 1 Plan 02: SSR HAL Extension Summary

Added GP16 SSR GPIO support to the BiBa RP2040 HAL. SSR is driven LOW at boot unconditionally before any mode code runs, preventing BTS7960 power-on before arming.

**Duration:** ~5 min | **Tasks:** 2 | **Files modified:** 4

**Next:** Ready for Wave 2 Plan 01-03 (TDD test suite for biba_ramp)

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Add BIBA_PIN_SSR_GPIO=16 + ASCII pin map update to target.h | `391e55d` | target.h |
| 2 | HAL declarations, stubs, RP2040 impl + biba_hal_init() call | `391e55d` | biba_hal.h, biba_hal.c, biba_hal_rp2040.c |

## What Was Built

- `target.h`: `BIBA_PIN_SSR_GPIO 16` in dedicated `/* --- SSR ---*/` section; ASCII pin map updated with `GP16 GPIO OUT  SSR (BTS7960 power relay)`
- `biba_hal.h`: `biba_hal_ssr_init(void)` and `biba_hal_ssr_set(bool enabled)` declared with doc comment referencing D-13
- `biba_hal.c`: No-op stubs `void biba_hal_ssr_init(void) {}` and `void biba_hal_ssr_set(bool enabled) { (void)enabled; }`
- `biba_hal_rp2040.c`:
  - `biba_hal_ssr_init()` uses `gpio_init` + `gpio_set_dir(GPIO_OUT)` + `gpio_put(0)` — mirrors EN-pin pattern
  - `biba_hal_ssr_set(bool)` uses `gpio_put(BIBA_PIN_SSR_GPIO, enabled ? 1u : 0u)`
  - `biba_hal_init()` calls `biba_hal_ssr_init()` immediately after `biba_hal_motor_pwm_init()`

## Deviations from Plan

None — executed exactly as written.

## Self-Check: PASSED

- [x] `BIBA_PIN_SSR_GPIO 16` in target.h (value 16 not used by any other define)
- [x] GP16 row added to ASCII pin map comment
- [x] Both functions declared in biba_hal.h
- [x] STM32 stubs with `(void)enabled` in biba_hal.c
- [x] RP2040 impl: gpio_init + gpio_set_dir(GPIO_OUT) + gpio_put(0) in init
- [x] `biba_hal_ssr_init()` called from `biba_hal_init()` after `biba_hal_motor_pwm_init()`
