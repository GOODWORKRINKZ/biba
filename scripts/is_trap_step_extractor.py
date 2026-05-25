#!/usr/bin/env python3
"""Extract pseudo-step responses from RPMTRACK TRAP data.

At every direction reversal (target crosses zero) the motor coasts to zero
and restarts — that is a 0 → ±plateau_hz step.  This script:

  1. Finds every zero-crossing in target_hz.
  2. Extracts meas_hz starting from that crossing until 2 s later.
  3. Normalises to (0 → 1) using the plateau target magnitude.
  4. Overlays all extracts + computes mean ± std envelope.
  5. Reports classic step-response metrics for each transition.

Usage:
    python3 scripts/is_trap_step_extractor.py
    python3 scripts/is_trap_step_extractor.py --csv path/to/rpmtrack_TRAP*.csv
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

ARTIFACTS  = Path(__file__).resolve().parent / "artifacts"
TRAP_GLOB  = str(ARTIFACTS / "is-rpmtrack" / "rpmtrack_TRAP*.csv")
OUT_DIR    = ARTIFACTS / "is-step-analysis"

WINDOW_S       = 2.5    # seconds after zero-crossing to extract
INTERP_DT_S    = 0.01   # 10 ms grid for resampling before averaging
PLATEAU_TOL    = 30.0   # Hz — target within this of peak = "plateau reached"
SETTLE_BAND    = 0.05   # ±5 % settling criterion


def compute_metrics(t: np.ndarray, y_norm: np.ndarray) -> dict:
    """Metrics on normalised (0→1) step response."""
    valid = ~np.isnan(y_norm)
    if valid.sum() < 3:
        return dict(rise_ms=float("nan"), overshoot_pct=0.0,
                    settle_ms=0.0, ss_err_norm=float("nan"))

    yv = y_norm[valid]
    tv = t[valid]

    # Rise 10%→90%
    i10 = np.argmax(yv >= 0.10) if np.any(yv >= 0.10) else None
    i90 = np.argmax(yv >= 0.90) if np.any(yv >= 0.90) else None
    rise_ms = (tv[i90] - tv[i10]) * 1000.0 if (i10 is not None and i90 is not None) else float("nan")

    peak = float(np.nanmax(y_norm))
    overshoot_pct = (peak - 1.0) * 100.0 if peak > 1.0 else 0.0

    outside = np.where((valid) & (np.abs(y_norm - 1.0) > SETTLE_BAND))[0]
    settle_ms = t[outside[-1]] * 1000.0 if outside.size > 0 else 0.0

    # SS error from last 25% of valid samples
    n_ss = max(1, int(0.25 * valid.sum()))
    ss_mean = float(np.nanmean(yv[-n_ss:]))
    ss_err_norm = ss_mean - 1.0

    return dict(rise_ms=rise_ms, overshoot_pct=overshoot_pct,
                settle_ms=settle_ms, ss_err_norm=ss_err_norm)


def extract_transitions(df: pd.DataFrame, window_s: float) -> list[dict]:
    """Return list of normalised step slices."""
    t_ms  = df["t_ms"].values.astype(float)
    tgt   = df["target_hz"].values.astype(float)
    meas  = df["meas_hz"].values.astype(float)

    # Find zero-crossings: target changes sign
    sign = np.sign(tgt)
    # Treat near-zero as transition (target within ±15 Hz of 0 → next nonzero)
    transitions = []
    i = 0
    while i < len(tgt) - 1:
        # Look for target crossing through zero:
        # i-1 side has significant magnitude, i or i+1 has opposite sign
        if sign[i] != 0 and i > 0 and sign[i] != sign[i - 1] and sign[i - 1] != 0:
            # zero crossing here — but we want to find where motor actually
            # stops (meas ≈ 0) and then starts in new direction
            # Use as t0 the first sample where meas_hz is ~0 near this crossing
            # Search up to 5 samples before/after
            search_start = max(0, i - 3)
            search_end   = min(len(meas) - 1, i + 10)
            zero_idx = None
            for k in range(search_start, search_end):
                if abs(meas[k]) < 20.0:
                    zero_idx = k
                    break
            if zero_idx is None:
                i += 1
                continue

            # Find the plateau target magnitude — use max target over the window
            new_sign = sign[i]
            t0 = t_ms[zero_idx]
            end_ms_scan = t0 + window_s * 1000.0

            # Find next direction change to cap scan
            next_change_ms = end_ms_scan
            for k in range(zero_idx + 3, min(len(tgt), zero_idx + 200)):
                if sign[k] != 0 and sign[k] != new_sign:
                    next_change_ms = t_ms[k]
                    break
            # Also cap when target starts declining after peak
            peak_seen = 0.0
            for k in range(zero_idx + 3, min(len(tgt), zero_idx + 200)):
                if abs(tgt[k]) > peak_seen:
                    peak_seen = abs(tgt[k])
                elif peak_seen > 100 and abs(tgt[k]) < peak_seen - 30.0:
                    next_change_ms = min(next_change_ms, t_ms[k])
                    break

            actual_window_ms = next_change_ms - t0
            if actual_window_ms < 600.0:   # skip if plateau too short (<0.6 s)
                i += 1
                continue

            scan_mask = (t_ms >= t0) & (t_ms <= next_change_ms)
            if scan_mask.sum() < 3:
                i += 1
                continue
            # Use max of signed target in this direction as plateau_mag
            plateau_mag = float(np.max(new_sign * tgt[scan_mask]))
            if plateau_mag < 100.0:
                i += 1
                continue

            # Extract slice: from zero_idx to plateau end
            end_ms = t0 + min(actual_window_ms, window_s * 1000.0)
            mask = (t_ms >= t0) & (t_ms <= end_ms)
            if mask.sum() < 5:
                i += 1
                continue

            t_slice    = (t_ms[mask] - t0) / 1000.0
            meas_slice = meas[mask]

            # Normalise: signed meas into new direction / plateau_mag
            y_norm = new_sign * meas_slice / plateau_mag

            transitions.append(dict(
                t0_ms=t0,
                new_sign=new_sign,
                plateau_mag=plateau_mag,
                t=t_slice,
                y_norm=np.clip(y_norm, -0.3, 1.8),
            ))
            i = zero_idx + 5  # skip past this transition
            continue
        i += 1
    return transitions


def resample(t: np.ndarray, y: np.ndarray, dt: float, t_max: float) -> tuple:
    """Linear interpolation onto uniform grid."""
    t_grid = np.arange(0.0, t_max + dt, dt)
    y_interp = np.interp(t_grid, t, y, left=float("nan"), right=float("nan"))
    return t_grid, y_interp


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", nargs="*",
                        help="RPMTRACK TRAP CSV files (default: auto-find)")
    parser.add_argument("--window", type=float, default=WINDOW_S,
                        help="Extraction window in seconds (default 2.5)")
    args = parser.parse_args()
    window_s = args.window

    csv_paths = [Path(p) for p in (args.csv or glob.glob(TRAP_GLOB))]
    csv_paths = sorted(set(p for p in csv_paths if p.exists()))

    if not csv_paths:
        print(f"No TRAP CSV files found under {TRAP_GLOB}")
        return

    all_transitions: list[dict] = []
    for path in csv_paths:
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        trans = extract_transitions(df, window_s)
        print(f"{path.name}: {len(trans)} transitions extracted")
        for tr in trans:
            tr["source"] = path.stem[-12:]
        all_transitions.extend(trans)

    if not all_transitions:
        print("No transitions found.")
        return

    # --- Metrics table ---------------------------------------------------
    print(f"\n{'#':>3}  {'dir':>4}  {'plateau':>8}  {'rise ms':>8}  "
          f"{'settle ms':>10}  {'overshoot%':>11}  {'SS err%':>8}")
    print("-" * 62)
    for k, tr in enumerate(all_transitions):
        m = compute_metrics(tr["t"], tr["y_norm"])
        tr["metrics"] = m
        print(f"{k+1:>3}  {'+' if tr['new_sign']>0 else '-':>4}  "
              f"{tr['plateau_mag']:>8.0f}  {m['rise_ms']:>8.0f}  "
              f"{m['settle_ms']:>10.0f}  {m['overshoot_pct']:>11.1f}  "
              f"{m['ss_err_norm']*100:>7.1f}%")

    # --- Plots -----------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_max   = window_s
    dt      = INTERP_DT_S
    t_grid  = np.arange(0.0, t_max + dt, dt)

    # Separate forward / reverse
    groups = {"+1": [], "-1": []}
    for tr in all_transitions:
        key = "+1" if tr["new_sign"] > 0 else "-1"
        _, y_i = resample(tr["t"], tr["y_norm"], dt, t_max)
        groups[key].append(y_i)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    dirs = [("+1", "Forward  0 → +plateau", "tab:blue", axes[0]),
            ("-1", "Reverse  0 → −plateau", "tab:orange", axes[1])]

    for key, title, color, ax in dirs:
        mat = np.vstack([r for r in groups[key] if not np.all(np.isnan(r))])
        if mat.shape[0] == 0:
            ax.set_title(title + "\n(no data)")
            continue

        mean_y = np.nanmean(mat, axis=0)
        std_y  = np.nanstd(mat,  axis=0)

        # Individual traces (thin, transparent)
        for row in mat:
            ax.plot(t_grid, row, color=color, alpha=0.15, lw=0.8)

        # Mean ± std envelope
        ax.fill_between(t_grid, mean_y - std_y, mean_y + std_y,
                        color=color, alpha=0.25, label="±1σ")
        ax.plot(t_grid, mean_y, color=color, lw=2.5, label="mean")

        # Reference lines
        ax.axhline(1.0, color="grey", lw=1.0, linestyle="--", alpha=0.7, label="target")
        ax.axhline(1.0 + SETTLE_BAND, color="grey", lw=0.5, linestyle=":", alpha=0.5)
        ax.axhline(1.0 - SETTLE_BAND, color="grey", lw=0.5, linestyle=":",
                   alpha=0.5, label=f"±{SETTLE_BAND*100:.0f}% band")
        ax.axhline(0.9, color="silver", lw=0.4, linestyle="-.", alpha=0.6)
        ax.axhline(0.1, color="silver", lw=0.4, linestyle="-.", alpha=0.6,
                   label="10%/90% rise marks")
        ax.axhline(0.0, color="grey", lw=0.5)

        # Rise time on mean
        m_mean = compute_metrics(t_grid, mean_y)
        if not np.isnan(m_mean["rise_ms"]):
            ax.axvline(m_mean["rise_ms"] / 1000.0, color=color,
                       lw=1.2, linestyle=":", alpha=0.9)
        settle_s = m_mean["settle_ms"] / 1000.0
        if 0 < settle_s < t_max:
            ax.axvline(settle_s, color="orange", lw=1.2, linestyle=":", alpha=0.9)

        stats_txt = (f"n={mat.shape[0]}\n"
                     f"rise  {m_mean['rise_ms']:.0f} ms\n"
                     f"settle {m_mean['settle_ms']:.0f} ms\n"
                     f"OS  {m_mean['overshoot_pct']:.1f}%\n"
                     f"SS err  {m_mean['ss_err_norm']*100:+.1f}%")
        ax.text(0.97, 0.05, stats_txt,
                transform=ax.transAxes, fontsize=8,
                ha="right", va="bottom",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8))

        ax.set_xlim(0, t_max)
        ax.set_ylim(-0.2, 1.7)
        ax.set_xlabel("time since step (s)")
        ax.set_ylabel("normalised response")
        ax.set_title(title + f"  [{mat.shape[0]} samples]")
        ax.legend(fontsize=7, loc="upper left")
        ax.grid(alpha=0.25)

    fig.suptitle("PID step response extracted from TRAP dynamic tests", fontsize=11)
    fig.tight_layout()
    png = OUT_DIR / "trap_step_response.png"
    fig.savefig(png, dpi=130, bbox_inches="tight")
    print(f"\nplot → {png}")


if __name__ == "__main__":
    main()
