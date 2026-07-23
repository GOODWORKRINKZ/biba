# Phase 13 Discussion Log

**Date:** 2026-05-27
**Duration:** ~2 hours

## Areas Discussed

### 1. Timing / DMA ISR execution time
**Finding:** Goertzel spectral estimation (unchanged from Phase 10) dominates
ISR time at ~275 ms per invocation (RP2040, no FPU). However, this is
unchanged from Phase 10 — the ISR double-buffering pattern (copy ADC → restart
DMA → compute) prevents data loss. Not the regression cause.

### 2. ADC buffer / data race
**Finding:** `adc_capture_start_async_pair()` unchanged from Phase 10.
Copy-then-restart pattern guarantees no race. 4-channel DMA functions added
only to PoC firmware, not standalone mode.

### 3. Latch recovery false triggers
**Finding:** With CLOSED_LOOP=0, `s_rpm_duty_left = 0.0f` → latch check
`duty > 0.05f` is always FALSE. No false triggers. 0 latch resets in
session_0012 confirm.

### 4. Include order / macro shadowing
**Finding:** `#include "biba_config.h"` added to `rpm_spectral_estimator.c`.
In `rpm_spectral_estimator.c`, the header is included before `biba_config.h`,
so header defaults win. In `mode_standalone.c`, `biba_config.h` is included
first, so its overrides apply. But values are **identical** in both — no
actual discrepancy. Fragile pattern but not the current bug.

### 5. Melody / PWM conflict
**Finding:** PWM drivers (`bts7960.c`, HAL) unchanged from Phase 10.
Melody system unchanged.

### 6. ABI struct mismatch
**Finding:** `mean_adc` added to `biba_rpm_spectral_result_t` as first field.
All code compiled together in one build → no ABI mismatch possible.

### 7. ROOT CAUSE — Load gate sustained invalid periods
**Confirmed.** Blackbox session_0012 shows 72 duty oscillation events, PI
integral at saturation limits, negative duty at zero throttle. Simulation
model shows 18× increase in consecutive invalid windows (1→18) caused by
DC-current-based load gate during deceleration.

### 8. Fix strategy
Three-tier defence agreed:
1. Deceleration bypass in load gate (if |duty| < threshold & prev_rpm > min)
2. Raise LOAD_QUALITY_MAX from 10.0 → 15.0
3. PI integral reset on gate fire edge

## Key Artifacts

- `scripts/artifacts/phase13_before_after.png` — 18× degradation visualisation
- `scripts/artifacts/phase13_root_cause_model.png` — full oscillation cycle
- `scripts/artifacts/phase13_regression_analysis.png` — blackbox + PI model
- `artifacts/blackbox/session_0012.csv` — regression evidence (72 duty swings)

## User Decisions

- CLOSED_LOOP=0 was intentional — for testing other subsystems without RPM loop
- Regression exists with CLOSED_LOOP=1 (normal operation)
- Want to fix the load gate / PI interaction, not remove the gate
- Prefer modelling/simulation approach before hardware measurements
