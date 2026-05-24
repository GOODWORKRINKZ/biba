#!/usr/bin/env python3
"""Render sonograms for the SIN SWEEPRAW_BOTH algoset captures."""
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SPS = 10000.0
FREQ_MAX_HZ = 1500.0


def load_windows(path: Path) -> list[tuple[float, np.ndarray]]:
    wins: dict[int, dict] = defaultdict(lambda: {"duty": 0.0, "samples": []})
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            idx = int(row["win_idx"])
            wins[idx]["duty"] = float(row["duty_pct"])
            wins[idx]["samples"].append(int(row["adc_raw"]))
    return [
        (wins[idx]["duty"], np.asarray(wins[idx]["samples"], dtype=np.float64))
        for idx in sorted(wins)
    ]


def period_from_name(path: Path) -> int:
    match = re.search(r"_per(\d+)_", path.name)
    if match is None:
        raise ValueError(f"cannot parse period from {path}")
    return int(match.group(1))


def sonogram(rows: list[tuple[float, np.ndarray]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    duty = np.asarray([d for d, _ in rows], dtype=np.float64)
    samples = [s - np.mean(s) for _, s in rows]
    n = len(samples[0])
    window = np.hanning(n)
    freqs = np.fft.rfftfreq(n, d=1.0 / SPS)
    keep = freqs <= FREQ_MAX_HZ
    spec = []
    for signal in samples:
        mag = np.abs(np.fft.rfft(signal * window))
        spec.append(mag[keep])
    spec_arr = np.asarray(spec, dtype=np.float64).T
    db = 20.0 * np.log10(spec_arr + 1e-6)
    db -= np.nanmax(db)
    return duty, freqs[keep], db


def overlay_rev_spans(ax, duty: np.ndarray, y_min: float, y_max: float) -> None:
    rev = duty < -10.0
    start = None
    for i, is_rev in enumerate(rev):
        if is_rev and start is None:
            start = i - 0.5
        if start is not None and (not is_rev or i == len(rev) - 1):
            end = (i - 0.5) if not is_rev else (i + 0.5)
            ax.axvspan(start, end, ymin=0.0, ymax=1.0, color="C0", alpha=0.10)
            start = None
    ax.set_ylim(y_min, y_max)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glob", default="scripts/artifacts/is-sweepraw/*algoset_sin*_left.csv")
    parser.add_argument("--out", type=Path, default=Path("scripts/artifacts/is-sweepraw/sin_algoset_sonograms.png"))
    args = parser.parse_args()

    left_paths = sorted(Path.cwd().glob(args.glob))
    if not left_paths:
        raise SystemExit(f"no files match: {args.glob}")

    captures = {}
    for left_path in left_paths:
        period = period_from_name(left_path)
        right_path = Path(str(left_path).replace("_left.csv", "_right.csv"))
        if right_path.exists():
            captures[period] = (load_windows(left_path), load_windows(right_path))

    periods = sorted(captures, reverse=True)
    fig, axes = plt.subplots(len(periods), 3, figsize=(17, 3.7 * len(periods)), sharex=False)
    if len(periods) == 1:
        axes = np.asarray([axes])
    fig.suptitle("SIN algoset sonograms: raw ADC spectrum, REV zones shaded")

    last_image = None
    for row_idx, period in enumerate(periods):
        left_rows, right_rows = captures[period]
        duty_l, freqs, db_l = sonogram(left_rows)
        duty_r, _, db_r = sonogram(right_rows)
        x = np.arange(len(duty_l))

        ax = axes[row_idx, 0]
        ax.plot(x, duty_l, "k-", lw=1.2)
        ax.axhline(0, color="0.4", lw=0.6)
        overlay_rev_spans(ax, duty_l, -90, 90)
        ax.set_ylabel(f"{period / 1000:.1f}s\nduty %")
        ax.grid(alpha=0.25)
        if row_idx == 0:
            ax.set_title("Input duty")

        for ax, db, title, duty in (
            (axes[row_idx, 1], db_l, "LEFT raw ADC spectrum\n(REV burned: ignore as wheel speed)", duty_l),
            (axes[row_idx, 2], db_r, "RIGHT raw ADC spectrum\n(valid both directions)", duty_r),
        ):
            last_image = ax.imshow(
                db,
                origin="lower",
                aspect="auto",
                interpolation="nearest",
                extent=(-0.5, len(duty) - 0.5, freqs[0], freqs[-1]),
                cmap="magma",
                vmin=-45,
                vmax=0,
            )
            overlay_rev_spans(ax, duty, 0.0, FREQ_MAX_HZ)
            ax.set_ylabel("Hz")
            if row_idx == 0:
                ax.set_title(title)

    for ax in axes[-1, :]:
        ax.set_xlabel("window index")
    fig.tight_layout(rect=(0.0, 0.0, 0.97, 0.96))
    if last_image is not None:
        cbar = fig.colorbar(last_image, ax=axes[:, 1:].ravel().tolist(), fraction=0.025, pad=0.01)
        cbar.set_label("dB relative to panel max")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=120)
    print(f"plot -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())