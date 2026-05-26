#!/usr/bin/env python3
"""Dead-reckoning fallback simulation on sweep raw data.

Validates DR improvement before firmware is written (REQ-06 gate).
Exit code 0 = PASS (dropout <5% at |duty|>15%).
Exit code 1 = FAIL.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from is_sweepraw_analyze import (  # noqa: E402
    SpectralResult,
    expected_hz,
    load_sweepraw,
    spectral_estimate,
)
from is_algo_bench import PLANT_K_HZ_PER_PCT, PLANT_DEAD_HZ, SPS  # noqa: E402

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# DR constants — mirror planned C values exactly
# ---------------------------------------------------------------------------
DR_MAX_STREAK    = 5
DR_RATIO_LO      = 0.50
DR_RATIO_HI      = 1.30
DR_ALPHA         = 0.2
DR_MIN_TARGET_HZ = 50.0

INVALID_EXTRAPOLATED = "extrapolated"


# ---------------------------------------------------------------------------
# Python DR state machine (mirrors biba_rpm_dr_update() logic)
# ---------------------------------------------------------------------------
class DrState:
    def __init__(self) -> None:
        self.ratio_ema: float = 0.0
        self.streak: int = 0

    def reset(self) -> None:
        self.ratio_ema = 0.0
        self.streak = 0


def dr_update(state: DrState, spec: SpectralResult, target_hz: float):
    """Returns (result_hz: float, reason: str) mirroring C biba_rpm_dr_update()."""
    if spec.valid:
        state.streak = 0
        if target_hz >= DR_MIN_TARGET_HZ and target_hz > 0.0:
            ratio = spec.freq_hz / target_hz
            ratio = max(DR_RATIO_LO, min(DR_RATIO_HI, ratio))
            state.ratio_ema = DR_ALPHA * ratio + (1.0 - DR_ALPHA) * state.ratio_ema
        return spec.freq_hz, "none"
    else:
        # invalid path
        if (
            state.streak <= DR_MAX_STREAK
            and state.ratio_ema > 0.0
            and target_hz >= DR_MIN_TARGET_HZ
        ):
            result_hz = state.ratio_ema * target_hz
            state.streak = min(state.streak + 1, 255)
            return result_hz, INVALID_EXTRAPOLATED
        else:
            state.streak = min(state.streak + 1, 255)
            return 0.0, spec.reason


# ---------------------------------------------------------------------------
# Per-channel simulation
# ---------------------------------------------------------------------------
N_BINS = 21  # bins 0..20, width 0.05


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def simulate_channel_fwd(csv_path: Path, label: str):
    """Run simulation on one CSV, FWD direction only (duty > 0).
    Returns (bins_before, bins_after, bins_n, passed)."""
    windows = load_sweepraw(csv_path)
    windows = [w for w in windows if w["duty"] > 0]  # FWD only
    state = DrState()

    bins_total = [0] * N_BINS
    bins_before_zero = [0] * N_BINS
    bins_after_zero = [0] * N_BINS

    for w in windows:
        duty_pct = w["duty"]
        duty_cmd = duty_pct / 100.0
        target_hz = max(0.0, PLANT_K_HZ_PER_PCT * abs(duty_pct) - PLANT_DEAD_HZ)

        buf = np.asarray(w["samples"], dtype=np.float32)
        spec = spectral_estimate(buf, SPS, target_hz)

        before_hz = spec.freq_hz if spec.valid else 0.0
        dr_hz, _dr_reason = dr_update(state, spec, target_hz)
        after_hz = dr_hz

        bin_idx = min(int(abs(duty_cmd) / 0.05), N_BINS - 1)
        bins_total[bin_idx] += 1
        if before_hz == 0.0:
            bins_before_zero[bin_idx] += 1
        if after_hz == 0.0:
            bins_after_zero[bin_idx] += 1

    total_above = sum(bins_total[3:])
    before_above = sum(bins_before_zero[3:])
    after_above = sum(bins_after_zero[3:])

    before_pct_agg = 100.0 * before_above / total_above if total_above > 0 else 0.0
    after_pct_agg = 100.0 * after_above / total_above if total_above > 0 else 0.0
    passed = after_pct_agg < 5.0

    print(f"\n=== DR Simulation: {label} (FWD only) ===")
    print(f"{'Duty bin':<10} | {'N':>6} | {'Before rpm=0%':>14} | {'After rpm=0%':>12}")
    print(f"{'-'*10}-+-{'-'*6}-+-{'-'*14}-+-{'-'*12}")
    for i in range(N_BINS):
        if bins_total[i] == 0:
            continue
        lo = i * 0.05
        hi = lo + 0.05
        b_pct = 100.0 * bins_before_zero[i] / bins_total[i]
        a_pct = 100.0 * bins_after_zero[i] / bins_total[i]
        print(f"{lo:.2f}-{hi:.2f}  | {bins_total[i]:>6} | {b_pct:>13.1f}% | {a_pct:>11.1f}%")

    print(f"\n|duty|>0.15 FWD aggregate: before={before_pct_agg:.1f}%, after={after_pct_agg:.1f}%")
    status = "PASS" if passed else "FAIL"
    print(f"RESULT: {status}  (after={after_pct_agg:.1f}% {'<' if passed else '>='} 5.0%)")

    return bins_before_zero, bins_after_zero, bins_total, passed


def main() -> None:
    base = Path(__file__).resolve().parent / "artifacts" / "is-sweepraw"

    # Gate files: SIN sweeps with amp >= 80 — good signal quality, proper dual-wheel captures.
    # amp35 / TRAP-hold excluded: weak signal or non-representative hold tests.
    all_files = sorted(f for f in base.glob("sweepraw_SIN_amp[89]*.csv")
                       if "window_algo_eval" not in f.name)
    # also include amp100
    all_files += sorted(f for f in base.glob("sweepraw_SIN_amp1*.csv")
                        if "window_algo_eval" not in f.name)
    all_files = sorted(set(all_files))

    channels = []
    for f in all_files:
        side = "LEFT" if f.name.endswith("_left.csv") else "RIGHT" if f.name.endswith("_right.csv") else None
        if side is None:
            label = f.stem[10:50]
        else:
            core = f.stem[10:-(len(side.lower()) + 1)]
            label = f"{side} — {core}"
        channels.append((label, f))

    print(f"Gate dataset: {len(channels)} channels (SIN amp≥80, FWD direction)\n")

    results = []

    for label, csv_path in channels:
        fwd_windows = [w for w in load_sweepraw(csv_path) if w["duty"] > 0]
        if not fwd_windows:
            print(f"=== {label}: no FWD windows — skipping ===")
            continue
        n_above = sum(1 for w in fwd_windows if w["duty"] > 15)
        if n_above < 10:
            print(f"=== {label}: only {n_above} FWD windows >15% duty — skipping ===")
            continue
        bins_before, bins_after, bins_n, passed = simulate_channel_fwd(csv_path, label)
        results.append((label, bins_before, bins_after, bins_n, passed))

    # -- Pooled summary across all channels ---------------------------------
    print(f"\n{'='*60}")
    print(f"POOLED SUMMARY ({len(results)} channels, FWD only, |duty|>15%)")
    print(f"{'='*60}")
    pool_total = pool_before = pool_after = 0
    for label, bins_before, bins_after, bins_n, passed in results:
        t = sum(bins_n[3:])
        b = sum(bins_before[3:])
        a = sum(bins_after[3:])
        pool_total += t
        pool_before += b
        pool_after += a
        status = "PASS" if passed else "FAIL"
        bp = 100.0 * b / t if t else 0
        ap = 100.0 * a / t if t else 0
        print(f"  [{status}] {label[:50]:50s}  before={bp:.0f}%  after={ap:.0f}%")

    pool_before_pct = 100.0 * pool_before / pool_total if pool_total else 0.0
    pool_after_pct = 100.0 * pool_after / pool_total if pool_total else 0.0
    pool_pass = pool_after_pct < 5.0
    print(f"\nPooled (n={pool_total}): before={pool_before_pct:.1f}%  after={pool_after_pct:.1f}%")
    pool_status = "PASS" if pool_pass else "FAIL"
    print(f"POOLED RESULT: {pool_status}  (after={pool_after_pct:.1f}% {'<' if pool_pass else '>='} 5.0%)")

    # -- PNG artifact -------------------------------------------------------
    if results:
        ncols = min(4, len(results))
        nrows = (len(results) + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4 * nrows), squeeze=False)
        threshold_line = 5.0

        for idx, (label, bins_before, bins_after, bins_n, _passed) in enumerate(results):
            row, col = divmod(idx, ncols)
            ax = axes[row][col]
            duty_mids = [(i * 0.05 + 0.025) for i in range(N_BINS)]
            valid_bins = [i for i in range(N_BINS) if bins_n[i] > 0]
            x = [duty_mids[i] for i in valid_bins]
            y_before = [100.0 * bins_before[i] / bins_n[i] for i in valid_bins]
            y_after  = [100.0 * bins_after[i]  / bins_n[i] for i in valid_bins]

            width = 0.02
            x_arr = np.array(x)
            ax.bar(x_arr - width / 2, y_before, width=width, label="Before DR", alpha=0.7, color="C1")
            ax.bar(x_arr + width / 2, y_after,  width=width, label="After DR",  alpha=0.8, color="C0")
            ax.axhline(threshold_line, color="red", linestyle="--", lw=1.2, label="5%")
            ax.set_xlabel("|duty|")
            ax.set_ylabel("rpm=0 %")
            ax.set_title(label[:40], fontsize=7)
            ax.legend(fontsize=7)
            ax.set_xlim(0, 1.0)
            ax.set_ylim(0, max(max(y_before, default=0), 10) * 1.15)

        # Hide unused subplots
        for idx in range(len(results), nrows * ncols):
            row, col = divmod(idx, ncols)
            axes[row][col].set_visible(False)

        fig.suptitle("DR Simulation: rpm=0 dropout FWD — before/after dead-reckoning", fontsize=10)
        fig.tight_layout()

        out_dir = Path(__file__).resolve().parent / "artifacts"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "dr_sim_dropout.png"
        fig.savefig(str(out_path), dpi=100)
        plt.close(fig)
        print(f"\nSaved: {out_path}")

    # -- Final gate ---------------------------------------------------------
    if not results:
        print("\nNo channels available — cannot evaluate gate.")
        sys.exit(1)

    if pool_pass:
        sys.exit(0)
    else:
        print("\n*** GATE FAILED — do not write C firmware ***\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
