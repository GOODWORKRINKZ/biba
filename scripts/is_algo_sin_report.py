#!/usr/bin/env python3
"""Build a compact SIN algoset report from SWEEPRAW_BOTH CSV captures."""
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
STANDALONE_RPM_MAX_HZ = 940.0


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


def zc_freq(samples: np.ndarray, min_pkpk: float = 120.0, min_std: float = 40.0) -> float:
    block_count = 8
    block_len = len(samples) // block_count
    total = 0
    active = 0
    for block in range(block_count):
        seg = samples[block * block_len:(block + 1) * block_len]
        pkpk = float(seg.max() - seg.min())
        if pkpk < min_pkpk or float(seg.std()) < min_std:
            continue
        active += 1
        mid = (float(seg.min()) + float(seg.max())) / 2.0
        hyst = pkpk / 4.0
        up = mid + hyst
        dn = mid - hyst
        state = 1 if seg[0] > mid else -1
        for value in seg[1:]:
            if state > 0 and value < dn:
                state = -1
                total += 1
            elif state < 0 and value > up:
                state = 1
                total += 1
    if active < 2 or total < 2:
        return 0.0
    return total * 0.5 * SPS / len(samples)


def ema(values: np.ndarray, alpha: float = 0.35) -> np.ndarray:
    out = np.zeros_like(values, dtype=np.float64)
    current = 0.0
    for i, value in enumerate(values):
        if value == 0.0:
            current *= 0.85
        else:
            current = alpha * value + (1.0 - alpha) * current
        out[i] = current
    return out


def ema_with_validity(values: np.ndarray, valid: np.ndarray, alpha: float = 0.35) -> np.ndarray:
    out = np.zeros_like(values, dtype=np.float64)
    current = 0.0
    for i, value in enumerate(values):
        if not valid[i]:
            current = 0.0
        elif value == 0.0:
            current *= 0.85
        else:
            current = alpha * value + (1.0 - alpha) * current
        out[i] = current
    return out


def period_from_name(path: Path) -> int:
    match = re.search(r"_per(\d+)_", path.name)
    if match is None:
        raise ValueError(f"cannot parse period from {path}")
    return int(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glob", default="scripts/artifacts/is-sweepraw/*algoset_sin*_left.csv")
    parser.add_argument("--out", type=Path, default=Path("scripts/artifacts/is-sweepraw/sin_algoset_report.png"))
    args = parser.parse_args()

    left_paths = sorted(Path.cwd().glob(args.glob))
    if not left_paths:
        raise SystemExit(f"no files match: {args.glob}")

    periods = []
    rows_by_period = {}
    for left_path in left_paths:
        period = period_from_name(left_path)
        right_path = Path(str(left_path).replace("_left.csv", "_right.csv"))
        if not right_path.exists():
            continue
        periods.append(period)
        rows_by_period[period] = (load_windows(left_path), load_windows(right_path))

    periods = sorted(set(periods), reverse=True)
    fig, axes = plt.subplots(len(periods), 3, figsize=(16, 3.8 * len(periods)), sharex=False)
    if len(periods) == 1:
        axes = np.asarray([axes])
    fig.suptitle("SIN algoset: raw detector vs hardware-valid wheel frequency")

    print("period side region n duty_med std_med raw_zc_med hw_hz_med")
    for row_idx, period in enumerate(periods):
        left_rows, right_rows = rows_by_period[period]
        duty = np.asarray([d for d, _ in left_rows])
        idx = np.arange(len(duty))

        raw_l = np.asarray([zc_freq(s) for _, s in left_rows])
        raw_r = np.asarray([zc_freq(s) for _, s in right_rows])
        std_l = np.asarray([s.std() for _, s in left_rows])
        std_r = np.asarray([s.std() for _, s in right_rows])

        left_valid = duty > 10.0
        right_valid = np.abs(duty) > 10.0
        hw_l_raw = np.where(left_valid, raw_l, 0.0)
        hw_r_raw = np.where(right_valid, raw_r, 0.0)
        hw_l = ema_with_validity(hw_l_raw, left_valid)
        hw_r = ema_with_validity(hw_r_raw, right_valid) * np.where(duty < -10.0, -1.0, 1.0)
        target = duty / 100.0 * STANDALONE_RPM_MAX_HZ

        ax = axes[row_idx, 0]
        ax.plot(idx, duty, "k-", lw=1.3, label="duty %")
        ax.axhline(0, color="0.4", lw=0.6)
        ax.fill_between(idx, -85, 85, where=duty < -10, color="C0", alpha=0.08, label="REV region")
        ax.set_ylabel(f"{period/1000:.1f}s\nduty %")
        ax.grid(alpha=0.25)
        if row_idx == 0:
            ax.legend(fontsize=8, loc="upper right")

        ax = axes[row_idx, 1]
        ax.plot(idx, std_l, "C0o-", ms=3, lw=0.8, label="LEFT std")
        ax.plot(idx, std_r, "C3x-", ms=3, lw=0.8, label="RIGHT std")
        ax.axhline(40, color="g", ls="--", lw=0.8, label="std gate=40")
        ax.fill_between(idx, 0, max(float(std_l.max()), float(std_r.max())) * 1.05,
                        where=duty < -10, color="C0", alpha=0.08)
        ax.set_ylabel("ADC std")
        ax.grid(alpha=0.25)
        if row_idx == 0:
            ax.legend(fontsize=8, loc="upper right")

        ax = axes[row_idx, 2]
        ax.plot(idx, target, "k--", lw=1.2, label="target signed Hz")
        ax.plot(idx, raw_l, "C0:", alpha=0.5, label="LEFT raw ZC")
        ax.plot(idx, raw_r * np.where(duty < -10.0, -1.0, 1.0), "C3:", alpha=0.5, label="RIGHT raw ZC signed")
        ax.plot(idx, hw_l, "C0-", lw=2.0, label="LEFT valid Hz (REV burned=0)")
        ax.plot(idx, hw_r, "C3-", lw=2.0, label="RIGHT hardware-valid Hz")
        ax.axhline(0, color="0.4", lw=0.6)
        ax.fill_between(idx, -850, 850, where=duty < -10, color="C0", alpha=0.08)
        ax.set_ylabel("Hz")
        ax.grid(alpha=0.25)
        if row_idx == 0:
            ax.legend(fontsize=7, loc="upper right", ncol=2)

        for side, std, raw, hw in (("L", std_l, raw_l, hw_l), ("R", std_r, raw_r, np.abs(hw_r))):
            for region, mask in (("FWD", duty > 10), ("REV", duty < -10), ("ZERO", np.abs(duty) <= 10)):
                if not np.any(mask):
                    continue
                print(
                    f"{period:5d} {side} {region:4s} {int(mask.sum()):3d} "
                    f"{np.median(duty[mask]):8.1f} {np.median(std[mask]):8.1f} "
                    f"{np.median(raw[mask]):10.1f} {np.median(hw[mask]):9.1f}"
                )

    for ax in axes[-1, :]:
        ax.set_xlabel("window index")
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=120)
    print(f"plot -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())