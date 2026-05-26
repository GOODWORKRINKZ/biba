# Phase 10: Goertzel Dual-Window Search — Context

**Gathered:** 2026-05-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Extend the Goertzel spectral RPM estimator with a second search window centred
on the previous valid `freq_hz` (hint). Research first on all 28 sweepraw CSV
files to quantify improvement, then implement in firmware.

The plant-model search window fails at low duty because `target_hz` prediction
error is largest there. Adding a hint window costs ~20 extra Goertzel bins only
when `|hint_hz − target_hz| > deadband` — zero overhead when the model is good.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**9 decisions + 7 ACs are locked.** See `10-SPEC.md` for full requirements,
boundaries, and acceptance criteria.

Downstream agents MUST read `10-SPEC.md` before planning or implementing.

**In scope (from SPEC.md):**
- Research script `scripts/is_hint_research.py` — batch analysis of all 28 CSV files
- Extend `firmware/src/app/rpm_spectral_estimator.h/c` with `hint_hz` parameter
- Update all 6 existing call sites (4 in test_main.c, 2 in mode_standalone.c)
- Add `s_hint_hz_left / s_hint_hz_right` state + update logic in `mode_standalone.c`
- Unity tests for new hint behaviour
- Research gate: pooled FWD dropout improves by ≥ 5 pp before proceeding to firmware

**Out of scope (from SPEC.md):**
- Changes to `rpm_dr.h/c`
- Changes to PI loop, telemetry fields, or blackbox schema
- REV-direction windows
- Adaptive deadband or multi-history hint

</spec_lock>

<decisions>
## Implementation Decisions

### A: Result attribution when hint window wins

- **D-A1:** When the hint window produces the winning candidate (higher `peak_amp`),
  return `invalid_reason = BIBA_RPM_SPECTRAL_HINT_MEASURED` (new enum value = 6),
  `valid = true`. This lets `spec_reason_L/R` in telemetry/blackbox distinguish
  hint-assisted measurements from pure plant-model measurements. The PI loop and
  DR see a normal valid result regardless.

### B: Direction change — hint reset

- **D-B1:** `s_hint_hz_left` and `s_hint_hz_right` are reset to `0.0f` **both** on
  arm/disarm (existing SPEC D9) **and** whenever `s_meas_left_reverse /
  s_meas_right_reverse` changes (direction flip). A hint from the opposite
  direction is physically meaningless (different IS frequency behaviour).

- **D-B2 (empirical):** The research script (`is_hint_research.py`) runs the
  simulation under **two variants**:
  - `hint_reset_on_dir=True` — reset hint whenever direction flag changes
  - `hint_reset_on_dir=False` — reset only on arm/disarm

  The script reports per-variant dropout comparison on TRAP sweeps (which
  contain fwd↔rev transitions). The implementation decision is confirmed by
  data, not by assumption. D-B1 is the initial expected winner but may change.

### C: Research script output format

- **D-C1:** `is_hint_research.py` produces:
  - A per-file summary table (CSV file name, total_fwd, orig_dropout%,
    hint_dropout%, improvement_pp, winner_variant for B)
  - A pooled summary row
  - One chart PNG: `scripts/artifacts/is_sweepraw_hint_research.png`
    (bar chart per file + pooled total, colour-coded orig vs hint)
  - No exit-code gate — gate verdict read visually from the table.

### D: Python dual-window API location

- **D-D1:** `spectral_estimate_hint(buf, sps, target_hz, hint_hz)` is added to
  `scripts/is_sweepraw_analyze.py` as a first-class public function alongside
  the existing `spectral_estimate()`. It is the Python port of the extended
  firmware function and is reusable by future analysis scripts.
  `is_hint_research.py` imports and calls it from there.

### Deferred Ideas

- **DEFER-01 — Stall/slip detection via current-RPM correlation:** Use IS mean
  current trend + RPM estimate to classify: motor load vs. wheel slip vs. stall
  (needs IS current + wheel RPM + throttle command in one time series). Requires
  correlation of BMS/IS current data — separate research phase (Phase 11 candidate).

### the agent's Discretion

- Research script visual style: dark-themed matplotlib matching existing
  `dr_v2_hint.png` aesthetics (already established in this repo).
- New Unity test helper functions (`fill_sine_far()` etc.) to generate out-of-band
  signals — planner decides the exact helper names.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core firmware files
- `firmware/src/app/rpm_spectral_estimator.h` — struct + enum to extend
- `firmware/src/app/rpm_spectral_estimator.c` — Goertzel logic to extend
- `firmware/src/modes/mode_standalone.c` — 2 call sites + hint state to add
- `firmware/test/test_rpm_spectral_estimator/test_main.c` — 4 call sites + ≥6 new tests

### Python analysis
- `scripts/is_sweepraw_analyze.py` — add `spectral_estimate_hint()` here
- `scripts/is_algo_bench.py` — `PLANT_K_HZ_PER_PCT`, `PLANT_DEAD_HZ`, `SPS` constants
- `scripts/artifacts/is-sweepraw/*.csv` — all 28 CSV files (research input)

### Planning context
- `.planning/phases/10-goertzel-dual-window/10-SPEC.md` — locked requirements
  (9 decisions, 7 ACs, ambiguity 0.112)
- `scripts/artifacts/dr_v2_hint.png` — simulation result that motivated this phase
  (22% → 15% dropout on amp100/per8000 LEFT, 6 windows fixed)

### Key constants (do not change in this phase)
- `BIBA_RPM_SPECTRAL_MIN_PEAK_AMP_LSB = 45.0f`
- `BIBA_RPM_SPECTRAL_REL_BAND = 0.35f`
- `BIBA_RPM_SPECTRAL_ABS_BAND_HZ = 80.0f`  (deadband = this / 2 = 40 Hz)
- Enum value 5 = `BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED` (DR, already used)
- **New:** Enum value 6 = `BIBA_RPM_SPECTRAL_HINT_MEASURED` (hint window won)

</canonical_refs>
