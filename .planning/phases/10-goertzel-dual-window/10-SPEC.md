# SPEC — Phase 10: Goertzel Dual-Window Search

**Phase:** 10
**Status:** spec-complete
**Ambiguity score:** 0.112 (gate ≤ 0.20 ✓)
**Created:** 2026-05-26

---

## Problem Statement

Phase 9 analysis (session `dr_v2_hint.png`) revealed that the Goertzel spectral estimator fails
at low duty (|duty| ≈ 28%) not because the IS signal is weak, but because the plant-model search
window is **centred on the wrong frequency**:

| | Value |
|-|-------|
| duty | 28% |
| plant model target | 208 Hz |
| search band (plant) | 128 – 288 Hz |
| actual IS peak | ~370 Hz, amp = 52 (above MIN_AMP = 45) |
| peak inside plant band | amp = 10 (MISS) |

Root cause: `target_hz = 10.13 × |duty_pct| − 74.6` has largest relative error at low duty.
The motor is still spinning at a frequency close to the previous window's `freq_hz`; only the
plant model prediction drifted.

**Fix:** dual-window search — run a second Goertzel search centred on the previous valid
`freq_hz` (hint) when it differs from `target_hz` by more than the deadband. Take the candidate
with higher `peak_amp`. This requires zero firmware data: hint is simply the last output of
`biba_rpm_spectral_estimate()` that returned `valid = true`.

**Simulation results on amp100/per8000 fullsine LEFT:**
- Single-window: valid=64, DR=11, invalid=7 (dropout 22%)
- Dual-window: valid=70, DR=5, invalid=7 (dropout 15%)  → −7 pp improvement

---

## Decisions (locked)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Extend existing `biba_rpm_spectral_estimate()` — add `hint_hz` as 5th parameter | No duplicate signature; all 6 call sites updated in this phase |
| D2 | Deadband = `BIBA_RPM_SPECTRAL_ABS_BAND_HZ / 2` (= 40 Hz at defaults) | Derived from constant — no new magic number; validated in simulation |
| D3 | `hint_hz = 0.0f` → second window suppressed (backward-compatible sentinel) | Allows test files to call with 0 = identical to old behaviour |
| D4 | Best-of-two selection by `peak_amp` | Peak amplitude is the primary signal quality indicator already used for validity |
| D5 | Plant-model window always evaluated first; hint window only when deadband exceeded | Ensures no regression when model is accurate; extra Goertzel bins = 0 cost when hint ≈ target |
| D6 | Research script runs on all 28 CSV files (SIN + TRAP, all amplitudes); FWD windows only | Broadest possible evidence; REV windows excluded (motor in opposite direction, separate analysis) |
| D7 | Research output: per-file table + pooled total; comparison chart `is_sweepraw_hint_research.png` | Visual + numeric evidence before any firmware is touched |
| D8 | `hint_hz` tracking in `mode_standalone.c`: updated only when `spec.valid == true && spec.invalid_reason == BIBA_RPM_SPECTRAL_INVALID_NONE` | DR extrapolations must not feed back into hint (would lock hint at stale value) |
| D9 | `hint_hz` state reset to 0.0f on arm/disarm alongside existing `biba_rpm_dr_reset()` calls | Fresh start each session; no stale inter-session hints |

---

## Scope

### In scope
- Research script `scripts/is_hint_research.py` — batch analysis of all 28 CSV files
- Extend `firmware/src/app/rpm_spectral_estimator.h/c` with `hint_hz` parameter
- Update all 6 existing call sites (4 in test_main.c, 2 in mode_standalone.c)
- Add `s_hint_hz_left / s_hint_hz_right` state + update logic in `mode_standalone.c`
- Unity tests for new hint behaviour in `firmware/test/test_rpm_spectral_estimator/test_main.c`
- Research gate: pooled FWD dropout improves by ≥ 5 pp before proceeding to firmware

### Out of scope
- Changes to `rpm_dr.h/c` (DR fallback logic unchanged)
- Changes to PI loop, telemetry fields, or blackbox schema
- REV-direction windows (motor in reverse — separate plant model needed, future phase)
- Adaptive deadband or multi-history hint (keep it simple; single last-valid hint only)

---

## Acceptance Criteria

| # | Criterion | Pass condition |
|---|-----------|----------------|
| AC1 | Research gate | Pooled (DR + invalid) / total_fwd improves by ≥ 5 pp across all 28 files |
| AC2 | No regression at hint=0 | `biba_rpm_spectral_estimate(buf, n, sps, tgt, 0.0f)` returns **identical** result to old 4-arg call |
| AC3 | Second window fires correctly | When `|hint_hz − target_hz| > BIBA_RPM_SPECTRAL_ABS_BAND_HZ/2`, hint search executes and best candidate selected |
| AC4 | Best-of-two selection | When hint window has higher peak_amp AND ≥ MIN_AMP, result uses hint freq/amp |
| AC5 | hint_hz state isolation | DR/extrapolated windows do NOT update hint in mode_standalone.c |
| AC6 | Unity tests pass | `pio test -e native_test`: ≥ 6 new hint test cases + 0 regressions on existing 78 |
| AC7 | Research artifact committed | `scripts/artifacts/is_sweepraw_hint_research.png` + `scripts/is_hint_research.py` committed before firmware wave |

---

## Ambiguity Scores (at spec-complete)

```
Goal Clarity:        0.92   (specific: research gate + firmware extension defined)
Boundary Clarity:    0.88   (explicit in/out-of-scope; 6 call sites enumerated)
Constraint Clarity:  0.85   (deadband formula, hint sentinel, state reset rules)
Acceptance Criteria: 0.88   (7 falsifiable ACs with numeric thresholds)

Ambiguity = 1.0 − (0.35×0.92 + 0.25×0.88 + 0.20×0.85 + 0.20×0.88) = 0.112 ✓
```
