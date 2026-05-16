---
phase: 03-field-ready
plan: 01
subsystem: firmware
tags: [thermal-reset, bts7960, hal, native-test]
autonomous: true
---

# Phase 3 Plan 01: BTS7960 Thermal Reset Contract

## Outcome
Implemented THERM-01 thermal reset behavior in firmware with BTS7960 enable-line reset only (no SSR latch-clear path), and added native regression tests for reset ordering and pulse floor.

## Delivered
- Added `BIBA_BTS7960_RESET_PULSE_US` with a locked floor of `100u` in `firmware/include/biba_config.h`.
- Added `biba_hal_delay_us(uint32_t us)` API and implementations:
  - STM32 in `firmware/src/hal/biba_hal.c`
  - RP2040 in `firmware/src/hal/biba_hal_rp2040.c`
- Added `biba_bts7960_thermal_reset(uint32_t pulse_us)` in:
  - `firmware/src/drivers/bts7960.h`
  - `firmware/src/drivers/bts7960.c`
- Integrated thermal reset at:
  - standalone init (`biba_mode_standalone_init`)
  - arm rising edge (`biba_mode_standalone_tick`)
- Added regression suite: `firmware/test/test_bts7960/test_main.c`:
  - verifies sequence `PWM=0 -> EN low -> delay -> EN high`
  - verifies minimum `100 us` pulse floor
  - verifies larger caller pulse is preserved

## Verification
- `cd firmware && pio run -e biba_f103_rev_a_standalone` -> exit 0
- `cd firmware && pio run -e rpico_rp2040_standalone` -> exit 0
- `cd firmware && pio test -e native_test -f test_bts7960 -f test_control_loop` -> all tests passed

## Notes
- Added no-op STM32 `biba_hal_rgb_led_set` implementation in `firmware/src/hal/biba_hal.c` to satisfy standalone STM32 link path.
- Narrowed STM32 `fw_common` source filter in `firmware/platformio.ini` to exclude RP2040-only files.

## Requirement Traceability
- `THERM-01`: satisfied by thermal reset primitive + arm/init integration + deterministic native tests.
