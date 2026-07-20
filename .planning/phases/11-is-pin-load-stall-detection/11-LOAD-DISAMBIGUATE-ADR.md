# ADR: Throttle vs Load Disambiguation (Phase 11)

**Date:** 2026-05-26
**Status:** Research
**Phase:** 11 — IS-Pin Load & Stall Detection

## Context

The spectral RPM estimator provides per-window freq_hz and quality. The IS-pin DC mean
(mean_adc) is available after Phase 11's load gate extension. Together these two signals
form a 2D feature vector (Δfreq, ΔDC) per inter-window transition that may distinguish
three operating modes:
- **Acceleration:** motor spinning up (d_freq > 0 AND d_DC > 0 — more current, rising RPM)
- **Load increase:** external torque applied (d_freq < 0 AND d_DC > 0 — more current, falling RPM)
- **Stall:** motor stopped (|d_freq| ≈ 0 AND d_DC >> 0 — maximum current, no rotation)

## Research Results

Dataset: sweepraw_TRAP_amp50_per6000_n60_20260526-135642_softhold (60 windows, TRAP 50%)

Category counts: {'steady': 52, 'load': 4, 'acceleration': 2, 'stall': 1}

LDA separability: 1.00

## Decision

**D-D2 hypothesis: partially confirmed.**

The TRAP sweep (cyclic acceleration/deceleration/stall) shows the three regimes are visible
in (Δfreq, ΔDC) space. The classification using threshold rules (|d_freq|<20 & d_DC>500 for
stall, d_freq>10 & d_DC>50 for acceleration, d_freq<-10 & d_DC>50 for load) produces the
category distribution above.

Limitations:
- Softhold dataset is a TRAP sweep — not representative of steady-state driving with
  intermittent external load.
- Thresholds (20 Hz, 500 counts, 10 Hz, 50 counts) are heuristic starting points.
- A controlled load dataset (Phase 12) is needed for calibration.

## Proposed Detection Rule (Phase 12+ firmware target)

```
if |d_freq| < 20 Hz AND d_DC > 500 counts:
    state = STALL
elif d_freq > 10 Hz AND d_DC > 50 counts:
    state = ACCELERATION
elif d_freq < -10 Hz AND d_DC > 50 counts:
    state = LOAD_INCREASE
else:
    state = STEADY
```

## Deferred

Firmware implementation deferred to Phase 12+.
Thresholds require validation against additional captures (free run, controlled load).

## See Also

- scripts/is_load_disambiguate.py
- scripts/artifacts/load_disambiguate_scatter.png
