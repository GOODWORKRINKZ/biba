# Plan 12-01 Summary: biba_config.h Reorganization

**Status:** COMPLETE
**Completed:** 2026-05-27
**Wave:** 1
**Commit:** 9956014

## What Was Done

Reorganized `biba_config.h` from a flat 320-line header into a structured ~500-line configuration with 17 feature toggle sections.

### Files Modified

| File | Change |
|------|--------|
| `firmware/include/biba_config.h` | Complete reorganization: 17 `BIBA_FEATURE_*` toggles in named sections, dependency `#error` checks, backward compat for `BIBA_OPEN_LOOP` |
| `firmware/targets/RPICO_RP2040/target_config.h` | Added `BIBA_FEATURE_REVERSE_PIP=0` (per D-07) |
| `firmware/src/app/zc_detector.h` | All 5 `#define` constants wrapped in `#ifndef` guards |
| `firmware/src/app/rpm_spectral_estimator.h` | All 6 `#define` constants wrapped in `#ifndef` guards |
| `firmware/src/app/rpm_pi.h` | All 9 `#define` constants wrapped in `#ifndef` guards |

### Feature Toggles Introduced

**RPM Chain (master `BIBA_FEATURE_RPM_CLOSED_LOOP`):**
- `BIBA_FEATURE_RPM_ZC` — Zero-crossing detector
- `BIBA_FEATURE_RPM_SPECTRAL` — Goertzel spectral estimator
- `BIBA_FEATURE_RPM_DUAL_WINDOW` — Dual-window hint-guided search
- `BIBA_FEATURE_RPM_LOAD_GATE` — IS-pin DC load gate
- `BIBA_FEATURE_RPM_DR` — Dead reckoning fallback
- `BIBA_FEATURE_RPM_PI` — PI controller
- `BIBA_FEATURE_RPM_ANTI_STALL` — Anti-stall duty ramp

**Safety:**
- `BIBA_FEATURE_LATCH_RECOVERY` — BTS7960 thermal latch auto-reset
- `BIBA_FEATURE_CURRENT_LIMITER` — Per-motor current/power clamp

**Comfort:**
- `BIBA_FEATURE_STEERING_DEADBAND` — Steering deadband
- `BIBA_FEATURE_RPM_RAMP` — RPM setpoint accel/decel ramp
- `BIBA_FEATURE_MELODY` — Motor coil melodies
- `BIBA_FEATURE_REVERSE_PIP` — Reverse backup beep

**Drive:**
- `BIBA_FEATURE_HEADING_HOLD` — Heading-hold PID
- `BIBA_FEATURE_SPEED_MODE` — 3-position switch speed scaling
- `BIBA_FEATURE_MIXER_PROJECTION` — L∞ ball projection

### Dependency Validation

Four `#error` checks at the bottom of `biba_config.h`:
- `PI → DR`: PI uses DR as measurement source
- `DUAL_WINDOW → SPECTRAL`: hint is a second Goertzel search
- `LOAD_GATE → SPECTRAL`: gate applied to spectral result
- `ANTI_STALL → SPECTRAL`: uses HIGH_LOAD from spectral

All checks skipped when `BIBA_FEATURE_RPM_CLOSED_LOOP=0`.

### Backward Compatibility

- `#ifdef BIBA_OPEN_LOOP` → `#define BIBA_FEATURE_RPM_CLOSED_LOOP 0` + `#warning`
- `#ifdef BIBA_REVERSE_PIP_ENABLED` → maps to `BIBA_FEATURE_REVERSE_PIP`

## Verification

- [x] Default build (rpico_rp2040_standalone, all toggles=1): **SUCCESS**
- [x] All 17 toggles present with `#ifndef` guards
- [x] All 4 dependency `#error` checks present
- [x] BIBA_OPEN_LOOP backward compat with `#warning`
- [x] BIBA_REVERSE_PIP_ENABLED backward compat
- [x] Module headers (zc, spectral, pi) have `#ifndef` guards
- [x] target_config.h: REVERSE_PIP=0

## Self-Check: PASSED
