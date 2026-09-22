# Plan 11-02 SUMMARY — Battery Sag Cross-talk Analysis

**Date:** 2026-05-26
**Status:** COMPLETE
**Script:** `scripts/is_batsag_research.py`

## Results

- **DC_L mean:** 2997.0 ADC counts
- **DC_R mean:** 1734.2 ADC counts
- **Pearson-r:** 0.890
- **p-value:** 1.866e-21
- **n:** 60 windows
- **Conclusion:** Strong positive correlation confirmed (|r| = 0.890 >> 0.3 trigger)

## Controlled Capture Recommended

Per D-C2: |r| > 0.3 → controlled capture warranted.

```
python3 scripts/is_poc_sweepraw.py --port /dev/ttyACM0 \
    --shape TRAP --amp 50 --period 6000 --n-windows 60 \
    --motor both --tag stall_L_free_R --no-analyze
```

Goal: compute k_sag = mean(ΔDC_free) / DC_free_base.

## Artifacts
- `scripts/is_batsag_research.py` — 81 lines
- `scripts/artifacts/batsag_scatter.png` — 82 KB

## Acceptance Criteria — ALL PASS
- [x] Script exits 0
- [x] CONFIRMED line with |r|=0.890
- [x] Controlled capture procedure printed (|r| > 0.3)
- [x] batsag_scatter.png exists, size > 5 KB
- [x] "Pearson-r = 0.890" in output
