#!/usr/bin/env python3
"""Analyze a SWEEPRAW capture: run all candidate ZC algorithms per-window
and plot how each tracks the duty cmd through rise/hold/fall/reversal."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

# import algorithm bench
sys.path.insert(0, str(Path(__file__).resolve().parent))
from is_algo_bench import (  # noqa: E402
    ALGOS, PLANT_K_HZ_PER_PCT, PLANT_DEAD_HZ, SPS,
)


def load_sweepraw(path: Path) -> list[dict]:
    by_idx: dict[int, dict] = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            idx = int(row["win_idx"])
            if idx not in by_idx:
                by_idx[idx] = {
                    "idx": idx,
                    "t_ms": int(row["t_ms"]),
                    "duty": float(row["duty_pct"]),
                    "samples": [],
                }
            by_idx[idx]["samples"].append(int(row["adc_raw"]))
    out = list(sorted(by_idx.values(), key=lambda w: w["idx"]))
    for w in out:
        w["samples"] = np.asarray(w["samples"], dtype=np.int32)
    return out


def expected_hz(duty_pct: float) -> float:
    f = PLANT_K_HZ_PER_PCT * abs(duty_pct) - PLANT_DEAD_HZ
    return max(0.0, f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    windows = load_sweepraw(args.csv)
    print(f"loaded {len(windows)} windows from {args.csv}")

    t = np.asarray([w["t_ms"] / 1000.0 for w in windows])
    duty = np.asarray([w["duty"] for w in windows])
    exp = np.asarray([expected_hz(d) for d in duty])

    # algo × window matrix of estimates
    estimates: dict[str, np.ndarray] = {}
    for alg, fn in ALGOS.items():
        vals = []
        for w in windows:
            try:
                vals.append(fn(w["samples"]))
            except Exception as e:
                print(f"{alg} win{w['idx']}: {e}", file=sys.stderr)
                vals.append(float("nan"))
        estimates[alg] = np.asarray(vals, dtype=np.float32)

    # console summary: mean absolute error per phase bin
    print(f"\nGround truth: f = {PLANT_K_HZ_PER_PCT}·|duty| − {PLANT_DEAD_HZ}")
    print(f"\nPer-window |error| vs expected:")
    print(f"{'algo':22s}  {'mean_err':>9s}  {'med_err':>9s}  {'max_err':>9s}")
    for alg, est in estimates.items():
        # consider only windows where expected > 50 Hz (motor actually spinning)
        mask = exp > 50.0
        if not mask.any():
            continue
        err = np.abs(est[mask] - exp[mask])
        print(f"{alg:22s}  {err.mean():9.1f}  {np.median(err):9.1f}  {err.max():9.1f}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return 0

    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)

    ax = axes[0]
    ax.plot(t, duty, "k-", lw=1.5, label="duty cmd %")
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_ylabel("duty %")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    ax.set_title(f"SWEEPRAW analysis: {args.csv.name}")

    ax = axes[1]
    ax.plot(t, exp, "k--", lw=2, label="expected Hz (model)")
    colors = plt.cm.tab10(np.linspace(0, 1, len(ALGOS)))
    for (alg, est), c in zip(estimates.items(), colors):
        ax.plot(t, est, "-o", ms=4, color=c, label=alg, alpha=0.85)
    ax.set_ylabel("commutation Hz")
    ax.set_xlabel("time (s)")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8, ncol=2)

    fig.tight_layout()
    out_png = args.out or args.csv.with_suffix(".png")
    fig.savefig(out_png, dpi=110)
    print(f"\nplot → {out_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
