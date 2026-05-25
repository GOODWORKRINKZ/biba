#!/usr/bin/env python3
"""IS-signal PoC — time-domain plotter.

Plots raw ADC samples vs time (ms) for every CSV in
scripts/artifacts/is-capture/, arranged in a grid:
rows = duty cycles, columns = directions (FWD / REV).

X-axis: time in milliseconds with 1 ms minor-grid.
Y-axis: ADC counts (0..4095) and equivalent voltage on right axis.

Usage:
    python3 is_poc_plot_time.py                 # default artifact dir
    python3 is_poc_plot_time.py --artifacts <d> # custom dir
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

_FNAME_RE = re.compile(r"duty_(\d+)_(FWD|REV)_sps(\d+)")
ADC_VREF_V = 3.3
ADC_FULLSCALE = 4095


def load_csv(path: Path):
    """Return (samples, duty, direction, sps)."""
    m = _FNAME_RE.search(path.name)
    if not m:
        raise ValueError(f"cannot parse {path.name}")
    duty = int(m.group(1))
    direction = m.group(2)
    sps = int(m.group(3))
    values: list[int] = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if "adc_raw" not in row:
                break
            try:
                values.append(int(row["adc_raw"]))
            except (TypeError, ValueError):
                continue
    return np.asarray(values, dtype=np.int32), duty, direction, sps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "is-capture",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output PNG (default: <artifacts>/is_time_domain.png)",
    )
    parser.add_argument(
        "--window-ms",
        type=float,
        default=None,
        help="Crop X axis to the first N milliseconds (default: full capture).",
    )
    args = parser.parse_args()

    csvs = sorted(args.artifacts.glob("duty_*_sps*.csv"))
    if not csvs:
        print(f"no captures found in {args.artifacts}")
        return 1

    captures = [load_csv(p) for p in csvs]
    duties = sorted({c[1] for c in captures})
    directions = ["FWD", "REV"]

    fig, axes = plt.subplots(
        len(duties), len(directions),
        figsize=(14, 2.6 * len(duties)),
        sharex=True, sharey=True,
        squeeze=False,
    )

    for row, duty in enumerate(duties):
        for col, direction in enumerate(directions):
            ax = axes[row][col]
            match = next(
                (c for c in captures if c[1] == duty and c[2] == direction),
                None,
            )
            if match is None:
                ax.set_title(f"duty={duty}% {direction} (missing)")
                ax.set_visible(False)
                continue
            samples, _, _, sps = match
            t_ms = np.arange(samples.size) * 1000.0 / sps
            ax.plot(t_ms, samples, linewidth=0.6, color="tab:blue")

            mean = samples.mean()
            std = samples.std()
            pk_pk = int(samples.max() - samples.min())
            volt_pk_pk = pk_pk * ADC_VREF_V / ADC_FULLSCALE

            ax.axhline(mean, color="tab:orange", linewidth=0.8, alpha=0.7)
            ax.set_title(
                f"duty={duty}% {direction}  "
                f"mean={mean:.0f}  σ={std:.1f}  "
                f"pk-pk={pk_pk} ({volt_pk_pk*1000:.0f} mV)",
                fontsize=9,
            )
            ax.grid(True, which="major", linestyle="-", linewidth=0.4, alpha=0.5)
            ax.grid(True, which="minor", linestyle=":", linewidth=0.3, alpha=0.4)
            ax.minorticks_on()
            # 1 ms minor grid
            from matplotlib.ticker import MultipleLocator
            ax.xaxis.set_minor_locator(MultipleLocator(1.0))
            ax.xaxis.set_major_locator(MultipleLocator(10.0))
            if args.window_ms is not None:
                ax.set_xlim(0, args.window_ms)
            if row == len(duties) - 1:
                ax.set_xlabel("time (ms)")
            if col == 0:
                ax.set_ylabel("ADC counts")

            # Right Y axis: volts
            ax2 = ax.twinx()
            ax2.set_ylim(
                ax.get_ylim()[0] * ADC_VREF_V / ADC_FULLSCALE,
                ax.get_ylim()[1] * ADC_VREF_V / ADC_FULLSCALE,
            )
            if col == len(directions) - 1:
                ax2.set_ylabel("V", fontsize=8)
            ax2.tick_params(axis="y", labelsize=7)

    fig.suptitle(
        "IS-signal time domain  —  rows = duty, cols = direction  "
        f"(sps={captures[0][3]}, 1 ms minor grid)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    out_path = args.out or (args.artifacts / "is_time_domain.png")
    fig.savefig(out_path, dpi=130)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
