# Plan 07-05 Summary — Wire PI into mode_standalone.c + latch auto-recovery

**Phase**: 07-is-rpm-integration
**Plan**: 07-05
**Status**: Complete
**Branch**: develop
**Commits**: `6c793cd` (latch auto-recovery), prior commits in session (PI integration)

---

## Objective Delivered

Wired the FF+PI closed-loop RPM controller into `mode_standalone.c`, replacing
`biba_ramp_t` with an IRQ-driven ADC DMA state machine and `biba_rpm_pi_step()`
calls. Additionally implemented IS-signal based BTS7960 thermal latch
auto-recovery detector — empirically validated against captured stall data.

---

## Changes

### PI integration into mode_standalone.c
- `biba_ramp_t` state removed; replaced with `biba_rpm_pi_state_t s_rpm_pi_left/right`
- DMA IRQ callback `on_adc_pair_done()`: ZC analysis → `biba_rpm_pi_step()` → writes
  `volatile float s_rpm_duty_left/right`
- `biba_mode_standalone_tick()`: reads volatile duty, applies failsafe zeroing,
  calls `biba_hal_motor_pwm_*()`
- Telemetry: `wheel_rpm_left_hz` / `wheel_rpm_right_hz` populated from `meas_ema`
- `biba_rpm_pi_reset()` called on disarm/failsafe edges

### BTS7960 thermal latch auto-recovery (commit `6c793cd`)

Added to `mode_standalone.c`:

**Detection constants:**
```c
#define LATCH_IS_RAW_MIN      3500u   // ≈2.82 V; latch saturates to 4095
#define LATCH_BLOCKS_CONFIRM     3u   // 3 × ~51 ms ≈ 150 ms confirmation
#define LATCH_COOLDOWN_WINDOWS  20u   // ~1 s spin-up grace after reset
```

**Detection logic (in DMA IRQ `on_adc_pair_done`):**
- Compute mean IS raw over 512 samples/channel per DMA window
- Latch signature: `duty > 5%` AND `active_blocks == 0` (no commutation AC)
  AND `mean_is > 3500` (high DC fault-current)
- Require 3 consecutive windows (~150 ms) before setting `s_latch_reset_pending`
- Post-trigger: `s_latch_cooldown = 20` blocks IRQ re-arming for ~1 s

**Recovery (in main-context `biba_mode_standalone_tick`):**
- Consumes `s_latch_reset_pending` flag (never calls `sleep_us` in ISR)
- Calls `biba_bts7960_thermal_reset(BIBA_BTS7960_RESET_PULSE_US)`
- Resets both PI states
- Logs `[biba] LATCH RESET` to UART

---

## Threshold Validation

Validated against `scripts/artifacts/is-sweepraw/sweepraw_TRAP_amp30_per30000_n196_20260525-153131_lefthold_*`:

| Signal state | Mean ADC (LSB) | active_blocks | Triggers detector? |
|---|---|---|---|
| LEFT running 30% duty | ~250 | > 0 | No |
| RIGHT running high load | ~3400 | > 0 | No (AC present) |
| LEFT latched (stall) | 4095 (saturated) | 0 | Yes ✓ |

`active_blocks == 0` is primary discriminator. `mean > 3500` is secondary
guard with ~600 LSB margin below latch saturation.

---

## Must-Haves Status

- ✅ `mode_standalone.c` has no `biba_ramp_t` state variables
- ✅ DMA IRQ state machine starts on `biba_mode_standalone_init()`, non-blocking
- ✅ `mode_standalone_tick()` reads volatile `s_rpm_duty_left/right`
- ✅ Failsafe/disarm edge zeroes duties and calls `biba_rpm_pi_reset()`
- ✅ `rpico_rp2040_standalone` builds without errors (SUCCESS, 2.0 s)
- ✅ Telemetry populates `wheel_rpm_left_hz` from `s_rpm_pi_left.meas_ema`
- ✅ Latch auto-recovery: field-tested, cooldown loop fixed

---

## Field Test Notes

- Initial latch detection triggered false positives during normal running under load
- Root cause: motor spin-up from zero has `active_blocks == 0` + high IS — identical
  to latch signature → infinite reset loop
- Fix: `LATCH_COOLDOWN_WINDOWS = 20` (~1 s) blocks re-detection after each reset
- After fix: `[biba] LATCH RESET` appears correctly on stall, motor recovers
  automatically without removing throttle
