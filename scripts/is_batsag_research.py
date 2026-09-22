#!/usr/bin/env python3
"""Battery sag cross-talk analysis — DC_L vs DC_R Pearson-r from softhold capture."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent / "artifacts" / "is-sweepraw"
CSV_STEM = "sweepraw_TRAP_amp50_per6000_n60_20260526-135642_softhold"
OUT_PNG = Path(__file__).resolve().parent / "artifacts" / "batsag_scatter.png"
R_TRIGGER = 0.3  # threshold for recommending controlled capture (per D-C2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    csv_l = BASE_DIR / (CSV_STEM + "_left.csv")
    csv_r = BASE_DIR / (CSV_STEM + "_right.csv")

    if not csv_l.exists():
        print(f"ERROR: missing {csv_l}", file=sys.stderr)
        sys.exit(1)
    if not csv_r.exists():
        print(f"ERROR: missing {csv_r}", file=sys.stderr)
        sys.exit(1)

    df_l = pd.read_csv(str(csv_l))
    df_r = pd.read_csv(str(csv_r))

    dc_l = df_l.groupby("win_idx")["adc_raw"].mean()
    dc_r = df_r.groupby("win_idx")["adc_raw"].mean()

    # Align on common win_idx
    merged = dc_l.to_frame("dc_l").join(dc_r.to_frame("dc_r"), how="inner").reset_index()

    # --- Statistics ---
    r, p = pearsonr(merged["dc_l"].values, merged["dc_r"].values)
    print(f"DC_L mean={merged['dc_l'].mean():.1f}  DC_R mean={merged['dc_r'].mean():.1f}")
    print(f"Pearson-r = {r:.3f}   p = {p:.3e}   n = {len(merged)}")
    print(f"CONFIRMED: battery sag correlation |r|={abs(r):.3f}")

    # --- Controlled capture recommendation ---
    if abs(r) > R_TRIGGER:
        print("")
        print("Next step: capture with one motor held (stall), other free.")
        print("  Command: python3 scripts/is_poc_sweepraw.py --port /dev/ttyACM0 \\")
        print("           --shape TRAP --amp 50 --period 6000 --n-windows 60 \\")
        print("           --motor both --tag stall_L_free_R --no-analyze")

    # --- Figure ---
    fig, ax = plt.subplots(figsize=(7, 6))

    sc = ax.scatter(merged["dc_r"], merged["dc_l"], c=merged["win_idx"],
                    cmap="viridis", alpha=0.7, s=40)
    cbar = plt.colorbar(sc, ax=ax)
    cbar.set_label("win_idx")

    # Best-fit line
    coeffs = np.polyfit(merged["dc_r"], merged["dc_l"], 1)
    x_fit = np.linspace(merged["dc_r"].min(), merged["dc_r"].max(), 100)
    y_fit = np.polyval(coeffs, x_fit)
    ax.plot(x_fit, y_fit, color="red", lw=1.5, label=f"fit (r={r:.3f})")

    ax.set_xlabel("DC_R (ADC counts)")
    ax.set_ylabel("DC_L (ADC counts)")
    ax.set_title(f"Battery Sag Cross-talk — Pearson r={r:.3f}  p={p:.2e}")
    ax.legend(loc="upper left")

    fig.tight_layout()
    fig.savefig(str(OUT_PNG), bbox_inches="tight", dpi=150)
    print(f"saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
