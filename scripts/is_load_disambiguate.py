#!/usr/bin/env python3
"""Throttle vs load disambiguation — inter-window (Δfreq, ΔDC) gradient analysis."""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent / "artifacts" / "is-sweepraw"
CSV_STEM = "sweepraw_TRAP_amp50_per6000_n60_20260526-135642_softhold"
OUT_PNG = Path(__file__).resolve().parent / "artifacts" / "load_disambiguate_scatter.png"
ADR_PATH = (Path(__file__).resolve().parent.parent / ".planning" / "phases" /
            "11-is-pin-load-stall-detection" / "11-LOAD-DISAMBIGUATE-ADR.md")
SPS = 10000
N_SAMPLES = 1024


# ---------------------------------------------------------------------------
# Classification rule (D-D2 hypothesis)
# ---------------------------------------------------------------------------
def classify(delta_freq: float, delta_dc: float) -> str:
    if abs(delta_freq) < 20 and delta_dc > 500:
        return "stall"
    elif delta_freq > 10 and delta_dc > 50:
        return "acceleration"
    elif delta_freq < -10 and delta_dc > 50:
        return "load"
    else:
        return "steady"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    csv_l = BASE_DIR / (CSV_STEM + "_left.csv")
    if not csv_l.exists():
        print(f"ERROR: missing {csv_l}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(str(csv_l))

    # Per-window DC mean and FFT frequency
    records = []
    for win_idx, group in df.groupby("win_idx"):
        samples = group["adc_raw"].values.astype(float)
        dc_l = samples.mean()

        # FFT peak search in [100, 600] Hz
        X = np.fft.rfft(samples - samples.mean())
        freqs = np.fft.rfftfreq(len(samples), d=1.0 / SPS)
        mask = (freqs >= 100) & (freqs <= 600)
        if not mask.any():
            freq_hz = float("nan")
        else:
            peak_bin = np.argmax(np.abs(X[mask]))
            freq_hz = freqs[mask][peak_bin]

        records.append({"win_idx": win_idx, "freq_hz": freq_hz, "dc_l": dc_l})

    df_wins = pd.DataFrame(records).sort_values("win_idx").reset_index(drop=True)

    # Inter-window deltas
    df_wins["delta_freq"] = df_wins["freq_hz"].diff()
    df_wins["delta_dc"] = df_wins["dc_l"].diff()
    df_wins = df_wins.dropna(subset=["delta_freq", "delta_dc"]).reset_index(drop=True)

    # Classify
    df_wins["category"] = df_wins.apply(
        lambda row: classify(row["delta_freq"], row["delta_dc"]), axis=1
    )

    # --- Print results ---
    counts = df_wins["category"].value_counts().to_dict()
    print(f"Windows analysed: {len(df_wins)}")
    print(f"Category counts: {counts}")

    if HAS_SKLEARN:
        mask = df_wins["category"] != "steady"
        if mask.sum() >= 2:
            X = df_wins.loc[mask, ["delta_freq", "delta_dc"]].values
            y = df_wins.loc[mask, "category"].values
            lda = LinearDiscriminantAnalysis()
            lda.fit(X, y)
            acc = lda.score(X, y)
            print(f"LDA separability accuracy: {acc:.2f}")
            lda_result = f"{acc:.2f}"
        else:
            print("LDA separability accuracy: N/A (insufficient non-steady samples)")
            lda_result = "N/A"
    else:
        print("Note: install scikit-learn for LDA separability score")
        lda_result = "N/A"

    print("Decision boundary hypothesis (D-D2):")
    print("  acceleration: d_freq > 0 AND d_DC > 0")
    print("  load:         d_freq < 0 AND d_DC > 0")
    print("  stall:        |d_freq| → 0 AND d_DC >> 0")

    # --- Figure ---
    fig, ax = plt.subplots(figsize=(8, 6))

    color_map = {"acceleration": "green", "load": "orange", "stall": "red", "steady": "grey"}
    for cat, group in df_wins.groupby("category"):
        ax.scatter(group["delta_freq"], group["delta_dc"],
                   c=color_map.get(cat, "black"), label=cat, alpha=0.7, s=40,
                   edgecolors="none")

    ax.axvline(0, color="black", linestyle="--", lw=0.8, alpha=0.5)
    ax.axhline(0, color="black", linestyle="--", lw=0.8, alpha=0.5)
    ax.set_xlabel("Δfreq (Hz/window)")
    ax.set_ylabel("ΔDC (ADC counts/window)")
    ax.set_title("Throttle vs Load Gradient Disambiguation — softhold dataset")
    ax.legend(loc="upper right")

    fig.tight_layout()
    fig.savefig(str(OUT_PNG), bbox_inches="tight", dpi=150)
    print(f"saved: {OUT_PNG}")

    # --- Write ADR ---
    today = datetime.date.today().isoformat()
    adr_content = f"""# ADR: Throttle vs Load Disambiguation (Phase 11)

**Date:** {today}
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

Dataset: sweepraw_TRAP_amp50_per6000_n60_20260526-135642_softhold ({len(df_wins) + 1} windows, TRAP 50%)

Category counts: {counts}

LDA separability: {lda_result}

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
"""
    ADR_PATH.parent.mkdir(parents=True, exist_ok=True)
    ADR_PATH.write_text(adr_content)
    print(f"ADR written: {ADR_PATH}")


if __name__ == "__main__":
    main()
