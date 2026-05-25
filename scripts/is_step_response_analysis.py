#!/usr/bin/env python3
"""PID closed-loop step response analysis.

Reads RPMRUN CSV files (step 0→target) and optionally RPMTRACK TRAP CSV
(extracts each plateau-to-plateau transition as a pseudo-step).

Outputs:
  - Overlaid step response plot (normalised 0→1)
  - Absolute plot with all runs
  - Console table: rise_time, settling_time, overshoot, SS error

Usage:
    python3 scripts/is_step_response_analysis.py
    python3 scripts/is_step_response_analysis.py --rpmrun artifacts/is-pid/rpmrun1.csv
    python3 scripts/is_step_response_analysis.py --trap artifacts/is-rpmtrack/rpmtrack_TRAP*.csv
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
DEFAULT_RPMRUN_GLOB = str(ARTIFACTS / "is-pid" / "rpmrun*.csv")
DEFAULT_TRAP_GLOB   = str(ARTIFACTS / "is-rpmtrack" / "rpmtrack_TRAP*.csv")
DEFAULT_OUT         = ARTIFACTS / "is-step-analysis"
SETTLE_BAND_PCT     = 0.05   # ±5 % of final value → settling criterion
RISE_LO, RISE_HI   = 0.10, 0.90


# ---------------------------------------------------------------------------
def compute_metrics(t_s: np.ndarray, y: np.ndarray, target: float) -> dict:
    """Classic step-response metrics (absolute scale, same units as y)."""
    lo   = RISE_LO * target
    hi   = RISE_HI * target
    band = SETTLE_BAND_PCT * target

    # Rise time: first crossing of 10% → first crossing of 90%
    idx_lo = np.argmax(y >= lo) if np.any(y >= lo) else None
    idx_hi = np.argmax(y >= hi) if np.any(y >= hi) else None
    rise_ms = (t_s[idx_hi] - t_s[idx_lo]) * 1000 if (idx_lo is not None and idx_hi is not None) else float("nan")

    # Overshoot (only forward direction)
    peak = float(np.max(y))
    overshoot_pct = (peak - target) / target * 100.0 if peak > target else 0.0

    # Settling time: last time |y - target| > band, measured from start
    outside = np.where(np.abs(y - target) > band)[0]
    if outside.size > 0:
        settle_ms = t_s[outside[-1]] * 1000
    else:
        settle_ms = 0.0

    # Steady-state: mean of last 20% of samples
    ss_start = int(0.80 * len(y))
    ss_mean  = float(np.mean(y[ss_start:]))
    ss_err   = ss_mean - target

    return dict(
        rise_ms=rise_ms,
        overshoot_pct=overshoot_pct,
        settle_ms=settle_ms,
        ss_err=ss_err,
        ss_mean=ss_mean,
        peak=peak,
    )


# ---------------------------------------------------------------------------
def load_rpmrun(path: Path) -> list[dict]:
    """Load a single RPMRUN CSV → list of step records."""
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]

    # Detect the setpoint (may vary: take mode / most common value)
    targets = df["target_hz"].abs().unique()
    targets = targets[targets > 10]
    if len(targets) == 0:
        return []

    steps = []
    for tgt in targets:
        mask = df["target_hz"].abs() > tgt * 0.9
        sub  = df[mask].copy()
        if len(sub) < 5:
            continue
        # Find first non-zero meas row → that's t0
        t0_ms = float(sub["t_ms"].iloc[0])
        t = (sub["t_ms"].values - t0_ms) / 1000.0
        y = sub["meas_hz"].values
        duty = sub["duty_pct"].values
        steps.append(dict(
            label=f"RPMRUN target={tgt:.0f} Hz ({path.stem})",
            target=float(tgt),
            t=t, y=y, duty=duty,
            source=path.stem,
        ))
    return steps


# ---------------------------------------------------------------------------
def load_trap_transitions(path: Path, min_step_hz: float = 100.0) -> list[dict]:
    """Extract each plateau-to-plateau transition from a RPMTRACK TRAP CSV."""
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]

    # Identify transitions: where setpoint changes sign or crosses ±50%
    tgt = df["target_hz"].values
    t_ms = df["t_ms"].values
    meas = df["meas_hz"].values
    duty = df["duty_pct"].values

    # Find plateau segments (setpoint stable within ±2 Hz for ≥3 samples)
    plateaus = []
    i = 0
    while i < len(tgt) - 3:
        window = tgt[i:i+4]
        if np.max(np.abs(np.diff(window))) < 3.0:
            val = float(np.mean(window))
            if abs(val) > 20.0:  # skip zero-crossings
                plateaus.append((i, val))
            i += 3
        else:
            i += 1

    if len(plateaus) < 2:
        return []

    steps = []
    for k in range(len(plateaus) - 1):
        i0, v0 = plateaus[k]
        i1, v1 = plateaus[k + 1]
        step_size = abs(v1 - v0)
        if step_size < min_step_hz:
            continue
        # Slice from end of first plateau to well into second plateau
        t_slice = t_ms[i0:i1 + 20]
        y_slice = meas[i0:i1 + 20]
        d_slice = duty[i0:i1 + 20]
        # Normalise time so t=0 at transition start
        # Detect transition start: first sample where |tgt - v0| > 10 Hz
        rel_tgt = tgt[i0:i1 + 20]
        trans_idx = np.argmax(np.abs(rel_tgt - v0) > 10)
        if trans_idx == 0:
            continue
        t0_ms = float(t_slice[trans_idx])
        t = (t_slice[trans_idx:] - t0_ms) / 1000.0
        y = y_slice[trans_idx:]
        d = d_slice[trans_idx:]
        target_abs = abs(v1)
        if len(y) < 5 or target_abs < 20:
            continue
        # Use signed y if transition is forward, negate if reverse
        if v1 < 0:
            y = -y
        steps.append(dict(
            label=f"TRAP {v0:+.0f}→{v1:+.0f} Hz ({path.stem[-8:]})",
            target=float(target_abs),
            t=t, y=y, duty=d,
            source=path.stem,
        ))
    return steps


# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpmrun", nargs="*",
                        help="RPMRUN CSV files (default: artifacts/is-pid/rpmrun*.csv)")
    parser.add_argument("--trap", nargs="*",
                        help="RPMTRACK TRAP CSV files to extract transitions from")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-trap", action="store_true",
                        help="Skip TRAP extraction even if files are found")
    args = parser.parse_args()

    rpmrun_paths = [Path(p) for p in (args.rpmrun or glob.glob(DEFAULT_RPMRUN_GLOB))]
    trap_paths   = [] if args.no_trap else [
        Path(p) for p in (args.trap or glob.glob(DEFAULT_TRAP_GLOB))
    ]

    all_steps: list[dict] = []
    for p in sorted(set(rpmrun_paths)):
        if p.exists():
            all_steps.extend(load_rpmrun(p))

    for p in sorted(set(trap_paths)):
        if p.exists():
            all_steps.extend(load_trap_transitions(p))

    if not all_steps:
        print("No data found. Check artifact paths.")
        return

    # --- Print metrics table ------------------------------------------------
    print(f"\n{'Label':<50} {'Target':>8} {'Rise ms':>8} {'Settle ms':>10} "
          f"{'Overshoot%':>11} {'SS err Hz':>10} {'SS mean Hz':>11}")
    print("-" * 110)
    table_rows = []
    for s in all_steps:
        t, y, tgt = s["t"], s["y"], s["target"]
        m = compute_metrics(t, y, tgt)
        print(f"{s['label']:<50} {tgt:>8.0f} {m['rise_ms']:>8.0f} "
              f"{m['settle_ms']:>10.0f} {m['overshoot_pct']:>11.1f} "
              f"{m['ss_err']:>10.1f} {m['ss_mean']:>11.1f}")
        table_rows.append({**s, **m})

    # --- Per-run subplot grid -----------------------------------------------
    args.out.mkdir(parents=True, exist_ok=True)
    n = len(all_steps)
    ncols = min(n, 3)
    nrows = (n + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(6 * ncols, 5 * nrows),
                             squeeze=False)
    # Hide unused axes
    for k in range(n, nrows * ncols):
        axes[k // ncols][k % ncols].set_visible(False)

    COLORS = plt.cm.tab10.colors

    for idx, s in enumerate(table_rows):
        ax = axes[idx // ncols][idx % ncols]
        c = COLORS[idx % len(COLORS)]
        t, y, tgt = s["t"], s["y"], s["target"]
        y_norm = np.clip(y / tgt, -0.2, 1.6)

        ax.plot(t, y_norm, color=c, lw=2.0)
        ax.axhline(1.0, color="grey", lw=1.0, linestyle="--", alpha=0.8)
        ax.axhline(1.0 + SETTLE_BAND_PCT, color="grey", lw=0.6,
                   linestyle=":", alpha=0.5)
        ax.axhline(1.0 - SETTLE_BAND_PCT, color="grey", lw=0.6,
                   linestyle=":", alpha=0.5)
        ax.axhline(0.9, color="silver", lw=0.5, linestyle="-.", alpha=0.5)
        ax.axhline(0.1, color="silver", lw=0.5, linestyle="-.", alpha=0.5)
        ax.axhline(0.0, color="grey",   lw=0.4)

        # Annotations
        rise_s  = s["rise_ms"]  / 1000.0
        settle_s = s["settle_ms"] / 1000.0
        if not np.isnan(rise_s) and rise_s > 0:
            ax.axvline(rise_s, color=c, lw=1.0, linestyle=":", alpha=0.7)
            ax.text(rise_s + 0.05, 0.05, f"rise\n{s['rise_ms']:.0f} ms",
                    fontsize=7, color=c, va="bottom")
        if settle_s > 0 and settle_s < t[-1]:
            ax.axvline(settle_s, color="orange", lw=1.0, linestyle=":", alpha=0.7)
            ax.text(settle_s + 0.05, 0.5, f"settle\n{s['settle_ms']:.0f} ms",
                    fontsize=7, color="orange", va="center")

        info = (f"overshoot={s['overshoot_pct']:.1f}%\n"
                f"SS err={s['ss_err']:+.1f} Hz  ({s['ss_mean']:.0f} Hz)")
        ax.text(0.97, 0.05, info, transform=ax.transAxes,
                fontsize=7, ha="right", va="bottom",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7))

        ax.set_ylim(-0.1, 1.6)
        ax.set_xlabel("time since step (s)", fontsize=8)
        ax.set_ylabel("normalised (0→1)", fontsize=8)
        ax.set_title(s["label"], fontsize=8)
        ax.grid(alpha=0.25)

    fig.suptitle("PID closed-loop step responses — normalised", fontsize=11, y=1.01)
    fig.tight_layout()
    png = args.out / "step_response_analysis.png"
    fig.savefig(png, dpi=120, bbox_inches="tight")
    print(f"\nplot → {png}")


if __name__ == "__main__":
    main()
