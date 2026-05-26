# Plan 11-05 SUMMARY — Firmware Load Gate Implementation

**Date:** 2026-05-26
**Status:** COMPLETE

## Changes

### 1. `firmware/include/biba_config.h`
Added 3 constants (research-recommended values):
- `BIBA_RPM_LOAD_RATIO_THRESH = 1.5f` (ratio gate threshold)
- `BIBA_RPM_LOAD_QUALITY_MAX = 10.0f` (quality below which gate fires)
- `BIBA_RPM_LOAD_ABS_THRESH_ADC = 3800u` (absolute ADC fallback gate)

### 2. `firmware/src/app/rpm_spectral_estimator.h`
- Added `BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD = 7` to enum
- Added `float mean_adc` as first field in `biba_rpm_spectral_result_t`
- Added `biba_rpm_spectral_apply_load_gate()` prototype

### 3. `firmware/src/app/rpm_spectral_estimator.c`
- Added `#include "biba_config.h"` (required for native_test visibility)
- Set `result.mean_adc = mean` after mean computation
- Implemented `biba_rpm_spectral_apply_load_gate()` — symmetric ratio+absolute gate for both channels

### 4. `firmware/src/modes/mode_standalone.c`
- Added `biba_rpm_spectral_apply_load_gate(&spec_left, &spec_right)` call after both spectral estimates, before DR update

### 5. `firmware/test/test_rpm_spectral_estimator/test_main.c`
Added 4 new Unity tests:
- `test_load_gate_rejects_high_ratio_low_quality` — win3 analog, ratio=1.87, quality=3.7 → REJECT
- `test_load_gate_rejects_pre_latch` — win18 analog, ratio=2.39, quality=9.4 → REJECT
- `test_load_gate_keeps_light_load` — win14 analog, ratio=1.33, quality=11.1 → KEEP
- `test_load_gate_noop_when_both_invalid` — neither result modified when already invalid

## Test Results
- **pio test -e native_test:** 88 tests, 0 failures ✅
- **pio run -e rpico_rp2040_is_poc:** SUCCESS ✅

## Acceptance Criteria — ALL PASS
- [x] LOAD_RATIO_THRESH, LOAD_QUALITY_MAX, LOAD_ABS_THRESH_ADC all defined in biba_config.h
- [x] HIGH_LOAD=7 in enum
- [x] mean_adc field in struct + set in estimator
- [x] apply_load_gate prototype + implementation + call site
- [x] 4 new tests pass (0 failures)
- [x] 88 total tests, all pass
- [x] Firmware builds SUCCESS

## Gate Logic Summary
```
ratio = mean_primary / (mean_other + 1e-6)
IF (ratio > 1.5 AND quality < 10.0) OR (mean_primary > 3800):
    → valid = false, reason = HIGH_LOAD
```
Symmetric for both left and right channels.
