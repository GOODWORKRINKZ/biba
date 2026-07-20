# Plan 12-02 Summary: mode_standalone.c Feature Gates

**Status:** COMPLETE
**Completed:** 2026-05-27
**Wave:** 2
**Commit:** 387a76b

## What Was Done

Added `#if BIBA_FEATURE_<NAME>` compile-time guards to all 17 feature call sites in `mode_standalone.c`. Replaced the monolithic `#ifndef BIBA_OPEN_LOOP` blocks with cascaded individual feature gates.

### ISR (`on_adc_pair_done`) Changes

| Feature | Guard | Off Behavior |
|---------|-------|-------------|
| RPM_ZC | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_ZC` | zc_left/right remain {0} |
| RPM_SPECTRAL | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_SPECTRAL` | spec_left/right remain {0} |
| RPM_LOAD_GATE | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_LOAD_GATE` | Skip load gate call |
| RPM_ANTI_STALL | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_ANTI_STALL` | s_antistall_duty_* = 0.0f |
| RPM_DUAL_WINDOW | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_DUAL_WINDOW` | Don't update hint_hz |
| RPM_DR | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_DR` | spec_hz = spec.freq_hz (direct) |
| RPM_PI | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_PI` | s_rpm_duty_* remain 0.0f |
| LATCH_RECOVERY | `#if BIBA_FEATURE_LATCH_RECOVERY` | s_latch_reset_pending = false |

### Tick (`biba_mode_standalone_tick`) Changes

| Feature | Guard | Off Behavior |
|---------|-------|-------------|
| MELODY | `#if BIBA_FEATURE_MELODY` at 12 call sites | All melody calls skipped; motors always driven |
| SPEED_MODE | `#if BIBA_FEATURE_SPEED_MODE` | speed_scale = 1.0f |
| STEERING_DEADBAND | `#if BIBA_FEATURE_STEERING_DEADBAND` | steering = raw_steering |
| HEADING_HOLD | `#if BIBA_FEATURE_HEADING_HOLD` | Skip PID correction |
| MIXER_PROJECTION | `#if BIBA_FEATURE_MIXER_PROJECTION` | Use `biba_mix_differential()` fallback |
| CURRENT_LIMITER | `#if BIBA_FEATURE_CURRENT_LIMITER` | left_out/right_out = mix directly |
| RPM_RAMP | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_RAMP` | Reset ramp, pass-through duty |
| RPM_PI (tick) | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_PI` | Open-loop: mixer output → motors directly |
| REVERSE_PIP | `#if BIBA_FEATURE_REVERSE_PIP` | s_reverse_pip_active = false |

### Blackbox Record Changes

- `#ifdef BIBA_OPEN_LOOP` → `#if !BIBA_FEATURE_RPM_CLOSED_LOOP`
- PI integral fields zeroed when `!BIBA_FEATURE_RPM_PI`
- `pi_meas_ema_l` field zeroed when PI is off

### Local Constants

- `LATCH_IS_RAW_MIN`, `LATCH_BLOCKS_CONFIRM`, `LATCH_COOLDOWN_WINDOWS` — wrapped in `#ifndef` guards
- `ANTISTALL_RAMP_STEP`, `ANTISTALL_MAX_DUTY`, `ANTISTALL_CONFIRM` — wrapped in `#ifndef` guards

### Migration Completed

- `BIBA_REVERSE_PIP_ENABLED` → `BIBA_FEATURE_REVERSE_PIP`
- `#ifndef BIBA_OPEN_LOOP` → individual `#if BIBA_FEATURE_*` blocks
- `#ifdef BIBA_OPEN_LOOP` → `#if !BIBA_FEATURE_RPM_CLOSED_LOOP`

## Verification

- [x] Default build (rpico_rp2040_standalone, all toggles=1): **SUCCESS**
- [x] RAM: 14432 bytes (unchanged from Plan 01)
- [x] All 17 `#if BIBA_FEATURE_*` guards present
- [x] All `BIBA_OPEN_LOOP` guards replaced
- [x] `BIBA_REVERSE_PIP_ENABLED` renamed
- [x] `biba_mix_differential()` used in MIXER_PROJECTION else branch
- [x] Blackbox PI fields gated

## Self-Check: PASSED
