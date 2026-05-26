# Plan 11-04 SUMMARY — Throttle vs Load Disambiguation

**Date:** 2026-05-26
**Status:** COMPLETE

## Results

- **Windows analysed:** 59 (60 total, 1 dropped for delta)
- **Category counts:** steady=52, load=4, acceleration=2, stall=1
- **LDA separability accuracy:** 1.00 (with sklearn)
- **D-D2 hypothesis:** Partially confirmed — TRAP sweep shows three regimes are visible in (Δfreq, ΔDC) space

## ADR Decision

D-D2 hypothesis **partially confirmed**. The threshold-based classifier correctly separates
the TRAP sweep windows into steady/load/acceleration/stall categories. However, the softhold
dataset is a cyclic TRAP sweep — not representative of steady-state driving with intermittent
external load. Controlled load dataset needed in Phase 12.

## Artifacts
- `scripts/is_load_disambiguate.py` — 205 lines
- `scripts/artifacts/load_disambiguate_scatter.png` — 60 KB
- `.planning/phases/11-is-pin-load-stall-detection/11-LOAD-DISAMBIGUATE-ADR.md` — 61 lines

## Acceptance Criteria — ALL PASS
- [x] Script exits 0
- [x] "Windows analysed: 59" (>= 50)
- [x] "Category counts:" printed
- [x] "Decision boundary hypothesis" printed
- [x] PNG exists, size > 5 KB
- [x] ADR exists, 61 lines (>= 30)
- [x] ADR contains "Proposed Detection Rule"
- [x] ADR contains "d_freq", "d_DC", "Phase 12"
- [x] "ADR written:" in stdout

## Deferred to Phase 12+
- Controlled load dataset for threshold calibration
- Firmware implementation of disambiguation rule
