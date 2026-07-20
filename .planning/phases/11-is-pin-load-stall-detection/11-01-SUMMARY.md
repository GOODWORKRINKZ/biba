# Plan 11-01 SUMMARY — Load Gate Threshold Grid Search

**Date:** 2026-05-26
**Status:** COMPLETE
**Script:** `scripts/is_load_detector_research.py`

## Results

### Grid Search
- 20 combinations tested (5 THRESH × 4 QMAX)
- 3 correct combos: (1.2, 10.0), (1.5, 10.0), (1.5, 12.0), (1.8, 10.0), (1.8, 12.0)
  (1.2, 12.0 fails: win14 rejected — quality=11.1 < 12.0 combined with ratio=1.33 > 1.2)

### Sentinel Window Validation

| win | DC_L | DC_R | ratio | quality | gate(R=1.2,Q=10) | expected |
|-----|------|------|-------|---------|-------------------|----------|
|   3 | 2588 | 1383 | 1.87  |   3.7   | REJECT            | REJECT ✓ |
|  18 | 3586 | 1503 | 2.39  |   9.4   | REJECT            | REJECT ✓ |
|  14 | 1139 |  860 | 1.33  |  11.1   | KEEP              | KEEP   ✓ |

### Optimal Thresholds (script-selected)
- **LOAD_RATIO_THRESH = 1.2** (min THRESH among correct)
- **LOAD_QUALITY_MAX = 10.0** (tie-break: only 1.2 combo)

### Research-Recommended Thresholds (safer margin)
- **LOAD_RATIO_THRESH = 1.5** (recommended in 11-RESEARCH.md §1.4 — provides safety margin against false rejection of windows with 1.2 < ratio < 1.5 and quality < 10)
- **LOAD_QUALITY_MAX = 10.0**

### Plan 11-05 Firmware Constant Usage
Both (1.2, 10.0) and (1.5, 10.0) satisfy all 3 sentinel windows. The research
recommends 1.5 for the safety margin. Either is valid.

## Artifacts
- `scripts/is_load_detector_research.py` — 202 lines
- `scripts/artifacts/load_gate_threshold_grid.png` — 83 KB

## Acceptance Criteria — ALL PASS
- [x] Script exits 0
- [x] CONFIRMED line present (1.2 or 1.5 — both valid)
- [x] win3=REJECT in grid output
- [x] win18=REJECT in grid output
- [x] win14=KEEP in grid output
- [x] PNG exists, size > 10 KB
- [x] No Python exceptions
