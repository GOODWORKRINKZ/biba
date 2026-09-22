# SPEC — Phase 9: RPM Estimator Hardening

**Phase:** 09  
**Status:** spec-complete  
**Ambiguity score:** 0.16 (gate ≤ 0.20 ✓)  
**Created:** 2026-05-26

---

## Problem Statement

Session 0012 analysis (860 records, 34.4s driving) shows **19.2% of blackbox ticks have rpm=0
while |duty| > 0.15**. Root causes:

| Cause | rpm=0 count | Condition |
|-------|-------------|-----------|
| ADC saturation (mean_is ≥ 3800) | 61 / 117 sat. ticks (52%) | high duty → IS clips → Goertzel peak_amp < MIN_PEAK_AMP_LSB |
| active_blocks = 1 (weak signal) | 55 / 105 ticks (52%) | low torque / transition |
| Normal signal (blocks=8) noise | 79 / 619 ticks (13%) | spectral peak occasionally below threshold |

When `spec.valid = false`, firmware currently writes `spec_hz = 0.0f` → PI sees full
tracking error → integral winds → wheel jerks or oscillates.

**Fix:** Dead-reckoning (DR) fallback: when Goertzel is invalid, extrapolate from the last
valid measurement scaled by the ratio `meas_hz / target_hz`, maintained as an EMA. After
`N` consecutive invalid cycles, give up and write 0 (enabling stall detection).

---

## Decisions (locked)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | DR logic lives in **new files `rpm_dr.h` / `rpm_dr.c`** | estimator stays stateless + testable; mode_standalone.c calls DR |
| D2 | Max streak `N` is **`BIBA_RPM_DR_MAX_STREAK`** in `biba_config.h` | field-tunable without recompile |
| D3 | Invalid flag = **`BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED = 5`** added to existing enum | reuses spec_reason_L/R channel in serial telemetry and blackbox unchanged |
| D4 | Extrapolation = **`ratio_ema × curr_target_hz`**, `ratio = meas_hz / target_hz`, EMA α = 0.2 | adapts to per-wheel mechanical variation (LEFT/RIGHT ratio differ ~10%) |
| D5 | Initial `ratio_ema = 0.0f` → DR silent until first valid measurement | safe: no phantom RPM at cold start |
| D6 | `ratio_ema` clamped to corridor **[0.50, 1.30]** from sweep calibration | prevents wild extrapolation; derived from fullsine amp100 sweep p10–p95 |
| D7 | **Python simulation on sweep raw data FIRST** — must show < 10% rpm=0 at |duty|>15% before firmware is written | evidence gate before touching C code |
| D8 | Blackbox record unchanged (31 bytes) — DR flag carried via existing `spec_reason` byte | no struct version bump needed |

---

## In Scope

- `rpm_dr.h` / `rpm_dr.c` — DR state struct + `rpm_dr_update()` function
- `mode_standalone.c` — replace one-liner `spec_hz = valid ? freq : 0` with DR call
- `rpm_spectral_estimator.h` — add `BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED = 5` to enum
- `biba_config.h` — add `BIBA_RPM_DR_MAX_STREAK` (default 5) and `BIBA_RPM_DR_RATIO_LO/HI/ALPHA`
- `test_rpm_pi` or new `test_rpm_dr` — unit tests for DR state machine (streak, ratio update, clamp)
- Python simulation script (`scripts/is_dr_sim.py`) on `sweepraw_SIN_amp100_per8000_n157_20260524-180629_fullsine_{left,right}.csv`

## Out of Scope

- Modifying `rpm_spectral_estimator.c` logic or thresholds (separate concern)
- Modifying `zc_detector.c`
- Changing blackbox binary format or download script
- Per-wheel separate ratio constants in firmware (EMA adapts in-flight)
- IMU-assisted DR (no IMU in standalone mode)

---

## Requirements

### REQ-01: DR state machine
**Current:** `spec_hz_left = (enabled && spec_left.valid) ? spec_left.freq_hz : 0.0f`  
**Target:** When `spec_left.valid == false` and `streak ≤ BIBA_RPM_DR_MAX_STREAK` and `ratio_ema > 0` and `target_hz ≥ 50Hz`, return `ratio_ema × target_hz` and set `invalid_reason = EXTRAPOLATED`.  
**Accept:** Unit test: feed 3 consecutive invalid results to `rpm_dr_update()` — output is non-zero for streak ≤ N, 0 for streak > N.

### REQ-02: ratio EMA update
**Current:** No ratio tracking.  
**Target:** On every valid spectral result, update `ratio_ema = α × (meas_hz/target_hz) + (1-α) × ratio_ema`, clamped to [BIBA_RPM_DR_RATIO_LO, BIBA_RPM_DR_RATIO_HI].  
**Accept:** Unit test: feed 10 valid results with known ratio=0.9 starting from ratio_ema=0 — after 10 updates ratio_ema ≥ 0.5.

### REQ-03: cold start safety
**Current:** N/A  
**Target:** `ratio_ema` initialises to 0.0f. DR returns 0 (not extrapolated) until at least one valid measurement has been received (streak reset triggers ratio > 0 check).  
**Accept:** Unit test: call `rpm_dr_update()` with valid=false from cold — output = 0, reason = original invalid_reason (not EXTRAPOLATED).

### REQ-04: streak expiry → 0
**Current:** Already 0 after first invalid.  
**Target:** After `BIBA_RPM_DR_MAX_STREAK + 1` consecutive invalids, DR returns 0 regardless of ratio_ema. Streak counter does not overflow (uint8_t clamped at 255).  
**Accept:** Unit test: feed `BIBA_RPM_DR_MAX_STREAK + 2` consecutive invalids — last output = 0.

### REQ-05: EXTRAPOLATED reason in telemetry
**Current:** `spec_reason` = 0–4 (NONE, TARGET_LOW, NO_BAND, PEAK_LOW, QUALITY_LOW).  
**Target:** When DR returns extrapolated value, `s_spec_reason_left/right = BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED (5)`. Logged in serial CSV column `spec_reason_L/R`.  
**Accept:** After firmware flash: drive at full throttle, capture serial CSV, verify `spec_reason_L` contains value 5 in rows where previously rpm was 0.

### REQ-06: Python simulation validates improvement before firmware
**Current:** No simulation.  
**Target:** `scripts/is_dr_sim.py` runs ZC + spectral estimator (Python port) on fullsine amp100 sweep raw data, applies DR logic in Python, reports before/after dropout rate at |duty|>15%.  
**Accept:** Simulation shows rpm=0 dropout rate drops from ≥13% to ≤ 5% at |duty|>15% on fullsine sweep data before any firmware is written.

### REQ-07: all existing firmware tests still pass
**Current:** 71 test cases pass in native_test.  
**Target:** After changes, `pio test -e native_test` reports 71+ passed, 0 failed.  
**Accept:** CI terminal output shows `N test cases: N succeeded`.

---

## Calibration Context (from sweep analysis)

Fullsine amp100 sweep (`sweepraw_SIN_amp100_per8000_n157_20260524-180629_fullsine_*.csv`),
ZC A2 subwin schmitt applied in Python:

| Channel | Dir | N | mean ratio | std | p5 | p95 |
|---------|-----|---|-----------|-----|----|-----|
| LEFT  | FWD | 72 | 0.805 | 0.242 | 0.374 | 1.129 |
| RIGHT | FWD | 71 | 0.845 | 0.104 | 0.659 | 0.988 |
| RIGHT | REV | 57 | 0.759 | 0.129 | 0.426 | 0.893 |

LEFT missing REV sweep (hardware was not wired at capture time).  
LEFT/RIGHT differ by ~10% → EMA per-channel (separate state for left/right).

**Proposed config defaults:**
```c
#define BIBA_RPM_DR_MAX_STREAK    5u     /* ~500ms at 10Hz ADC loop */
#define BIBA_RPM_DR_RATIO_LO      0.50f  /* conservative p10 across all channels */
#define BIBA_RPM_DR_RATIO_HI      1.30f  /* p95 + margin */
#define BIBA_RPM_DR_EMA_ALPHA     0.20f  /* ~10 ticks to 90% adaptation */
```

---

## Acceptance Checklist

- [ ] REQ-01: DR state machine unit test passes
- [ ] REQ-02: ratio EMA update unit test passes
- [ ] REQ-03: cold start safety unit test passes
- [ ] REQ-04: streak expiry unit test passes
- [ ] REQ-05: `spec_reason=5` visible in serial telemetry during high-duty driving
- [ ] REQ-06: Python simulation dropout < 5% before firmware written
- [ ] REQ-07: `pio test -e native_test` — 0 failures

---

## Ambiguity Report

```
Goal Clarity:        0.90 (min 0.75) ✓
Boundary Clarity:    0.80 (min 0.70) ✓
Constraint Clarity:  0.80 (min 0.65) ✓
Acceptance Criteria: 0.82 (min 0.70) ✓
Ambiguity: 0.16 — gate PASSED
```
