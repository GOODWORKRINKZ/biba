#!/usr/bin/env python3
"""Load gate threshold grid search — validates LOAD_RATIO_THRESH and LOAD_QUALITY_MAX
against softhold capture before firmware implementation."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent / "artifacts" / "is-sweepraw"
CSV_STEM = "sweepraw_TRAP_amp50_per6000_n60_20260526-135642_softhold"
OUT_PNG = Path(__file__).resolve().parent / "artifacts" / "load_gate_threshold_grid.png"

THRESH_GRID = [1.2, 1.5, 1.8, 2.0, 2.5]
QMAX_GRID = [5.0, 7.0, 10.0, 12.0]
ABS_THRESH_DEFAULT = 3800.0  # fallback absolute gate (from D-A3)

# ---------------------------------------------------------------------------
# Sentinel windows (ground truth from research notes)
# ---------------------------------------------------------------------------
SENTINEL_WINS = {
    3:  {"dc_l": 2588.0, "dc_r": 1383.0, "quality": 3.7,  "expected": "REJECT"},
    14: {"dc_l": 1139.0, "dc_r":  860.0, "quality": 11.1, "expected": "KEEP"},
    18: {"dc_l": 3586.0, "dc_r": 1503.0, "quality": 9.4,  "expected": "REJECT"},
}


# ---------------------------------------------------------------------------
# Gate function (D-A2 + D-A3)
# ---------------------------------------------------------------------------
def apply_load_gate(dc_primary: float, dc_other: float,
                    quality: float,
                    ratio_thresh: float, quality_max: float,
                    abs_thresh: float = ABS_THRESH_DEFAULT) -> bool:
    """Return True if window should be REJECTED (HIGH_LOAD)."""
    ratio = dc_primary / (dc_other + 1e-6)
    if ratio > ratio_thresh and quality < quality_max:
        return True
    if dc_primary > abs_thresh:
        return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    # --- Load data ---
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

    # --- Grid search ---
    print("Load Gate Threshold Grid Search")
    print("=" * 60)
    correct_combos = []

    for thresh in THRESH_GRID:
        for qmax in QMAX_GRID:
            results = {}
            for win_idx, sw in SENTINEL_WINS.items():
                rejected = apply_load_gate(
                    sw["dc_l"], sw["dc_r"], sw["quality"], thresh, qmax
                )
                results[win_idx] = "REJECT" if rejected else "KEEP"

            r3, r18, r14 = results[3], results[18], results[14]
            correct = (r3 == "REJECT" and r18 == "REJECT" and r14 == "KEEP")
            status = "OK" if correct else "FAIL"

            print(f"  THRESH={thresh:.1f}  QMAX={qmax:.1f}  "
                  f"win3={r3}  win18={r18}  win14={r14}  {status}")

            if correct:
                correct_combos.append((thresh, qmax))

    # --- Optimal selection ---
    print()
    if not correct_combos:
        print("ERROR: no valid threshold found — review sentinel data")
        sys.exit(1)

    # Min THRESH, tie-break by max QMAX
    optimal = min(correct_combos, key=lambda x: (x[0], -x[1]))
    opt_t, opt_q = optimal
    print(f"CONFIRMED: LOAD_RATIO_THRESH={opt_t:.1f} LOAD_QUALITY_MAX={opt_q:.1f}")

    # --- Build grid matrix ---
    grid = np.zeros((len(QMAX_GRID), len(THRESH_GRID)), dtype=int)
    for qi, qmax in enumerate(QMAX_GRID):
        for ti, thresh in enumerate(THRESH_GRID):
            r3 = apply_load_gate(
                SENTINEL_WINS[3]["dc_l"], SENTINEL_WINS[3]["dc_r"],
                SENTINEL_WINS[3]["quality"], thresh, qmax
            )
            r18 = apply_load_gate(
                SENTINEL_WINS[18]["dc_l"], SENTINEL_WINS[18]["dc_r"],
                SENTINEL_WINS[18]["quality"], thresh, qmax
            )
            r14 = apply_load_gate(
                SENTINEL_WINS[14]["dc_l"], SENTINEL_WINS[14]["dc_r"],
                SENTINEL_WINS[14]["quality"], thresh, qmax
            )
            if r3 and r18 and not r14:
                grid[qi, ti] = 1

    # --- Figure ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Left: heatmap
    im = ax1.imshow(grid, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto", origin="lower")
    ax1.set_xticks(range(len(THRESH_GRID)))
    ax1.set_xticklabels([f"{t:.1f}" for t in THRESH_GRID])
    ax1.set_yticks(range(len(QMAX_GRID)))
    ax1.set_yticklabels([f"{q:.1f}" for q in QMAX_GRID])
    ax1.set_xlabel("LOAD_RATIO_THRESH")
    ax1.set_ylabel("LOAD_QUALITY_MAX")
    ax1.set_title("Load Gate Grid (green=correct)")

    # Mark optimal cell
    opt_ti = THRESH_GRID.index(opt_t)
    opt_qi = QMAX_GRID.index(opt_q)
    ax1.annotate("*", (opt_ti, opt_qi), color="white", fontsize=18,
                 ha="center", va="center", fontweight="bold")

    # Right: scatter of ratio vs dc_l for all windows, coloured by optimal gate
    merged = dc_l.to_frame("dc_l").join(dc_r.to_frame("dc_r"), how="inner").reset_index()
    merged["ratio"] = merged["dc_l"] / (merged["dc_r"] + 1e-6)
    # Use sentinel quality for known windows, NaN for rest
    merged["quality"] = np.nan
    for win_idx, sw in SENTINEL_WINS.items():
        merged.loc[merged["win_idx"] == win_idx, "quality"] = sw["quality"]

    # Classify all windows with optimal gate (using sentinel quality where available)
    def classify_row(row):
        q = row["quality"]
        if pd.isna(q):
            ratio = row["dc_l"] / (row["dc_r"] + 1e-6)
            if ratio > opt_t:
                return "REJECT"
            if row["dc_l"] > ABS_THRESH_DEFAULT:
                return "REJECT"
            return "KEEP"
        rejected = apply_load_gate(row["dc_l"], row["dc_r"], q, opt_t, opt_q)
        return "REJECT" if rejected else "KEEP"

    merged["gate"] = merged.apply(classify_row, axis=1)

    colors = {"REJECT": "red", "KEEP": "steelblue"}
    for gate_val, group in merged.groupby("gate"):
        ax2.scatter(group["ratio"], group["dc_l"], c=colors[gate_val],
                    alpha=0.5, s=30, label=f"gate={gate_val}", edgecolors="none")

    # Overlay sentinel windows
    for win_idx, sw in SENTINEL_WINS.items():
        ratio = sw["dc_l"] / (sw["dc_r"] + 1e-6)
        rejected = apply_load_gate(sw["dc_l"], sw["dc_r"], sw["quality"], opt_t, opt_q)
        marker_color = "darkred" if rejected else "darkgreen"
        ax2.scatter(ratio, sw["dc_l"], c=marker_color, s=120, edgecolors="black",
                    linewidths=1.5, zorder=5)
        ax2.annotate(f"win{win_idx}", (ratio, sw["dc_l"]),
                     textcoords="offset points", xytext=(8, 6), fontsize=9,
                     fontweight="bold")

    # Boundary lines
    ax2.axvline(opt_t, color="orange", linestyle="--", lw=1.5, alpha=0.7,
                label=f"THRESH={opt_t:.1f}")
    ax2.axhline(ABS_THRESH_DEFAULT, color="purple", linestyle=":", lw=1.5, alpha=0.5,
                label=f"ABS={ABS_THRESH_DEFAULT:.0f}")

    ax2.set_xlabel("ratio (dc_l / dc_r)")
    ax2.set_ylabel("DC_L (ADC counts)")
    ax2.set_title("Sentinel Windows — optimal gate boundary")
    ax2.legend(loc="upper left", fontsize=8)

    fig.tight_layout()
    fig.savefig(str(OUT_PNG), bbox_inches="tight", dpi=150)
    print(f"saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
