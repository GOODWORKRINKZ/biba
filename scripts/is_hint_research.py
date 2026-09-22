#!/usr/bin/env python3
"""Batch dual-window hint research script.

Loads all 28 sweepraw CSV files and simulates the Goertzel dual-window
estimator (spectral_estimate_hint) against the single-window baseline
(spectral_estimate).  Reports per-file dropout statistics and a pooled
improvement gate.

D-B2: Both hint_reset_on_dir=True and hint_reset_on_dir=False variants
are tested on TRAP files (which contain fwd↔rev transitions).

D-C1: No sys.exit(1) on gate failure — gate is visual; Wave 2 requires
manual review of stdout before proceeding.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from is_sweepraw_analyze import (  # noqa: E402
    spectral_estimate,
    spectral_estimate_hint,
    load_sweepraw,
    expected_hz,
)
from is_algo_bench import SPS  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ARTIFACTS_DIR = _SCRIPTS_DIR / "artifacts" / "is-sweepraw"
OUT_PNG = _SCRIPTS_DIR / "artifacts" / "is_sweepraw_hint_research.png"

# ---------------------------------------------------------------------------
# Per-file result container
# ---------------------------------------------------------------------------
@dataclass
class FileResult:
    name: str
    total_fwd: int = 0
    orig_dropout_count: int = 0
    hint_dropout_count: int = 0
    hint_reset_on_dir: bool = True

    @property
    def orig_dropout_pct(self) -> float:
        return 100.0 * self.orig_dropout_count / self.total_fwd if self.total_fwd else 0.0

    @property
    def hint_dropout_pct(self) -> float:
        return 100.0 * self.hint_dropout_count / self.total_fwd if self.total_fwd else 0.0

    @property
    def improvement_pp(self) -> float:
        return self.orig_dropout_pct - self.hint_dropout_pct


# ---------------------------------------------------------------------------
# Simulation loop
# ---------------------------------------------------------------------------
def run_simulation(csv_path: Path, hint_reset_on_dir: bool) -> FileResult:
    """Simulate single-window vs dual-window on FWD windows of one CSV file.

    D8: hint state updates only when r_hint.reason == "none"
    (i.e. BIBA_RPM_SPECTRAL_INVALID_NONE).  The "hint" reason
    (HINT_MEASURED) and any other non-"none" reason must NOT feed back.
    """
    res = FileResult(name=csv_path.stem, hint_reset_on_dir=hint_reset_on_dir)
    windows = load_sweepraw(csv_path)

    hint_hz: float = 0.0
    prev_duty_sign: Optional[int] = None  # track direction changes

    for w in windows:
        duty = w["duty"]

        # direction-change detection
        cur_sign = 1 if duty > 0 else (-1 if duty < 0 else 0)
        dir_changed = (prev_duty_sign is not None
                       and cur_sign != 0
                       and prev_duty_sign != 0
                       and cur_sign != prev_duty_sign)
        if cur_sign != 0:
            prev_duty_sign = cur_sign

        # FWD only (D6)
        if duty <= 0:
            continue

        # D-B2: optionally reset hint on direction change
        if hint_reset_on_dir and dir_changed:
            hint_hz = 0.0

        target_hz = expected_hz(duty)
        buf = w["samples"].astype(np.float32)

        r_orig = spectral_estimate(buf, SPS, target_hz)
        r_hint = spectral_estimate_hint(buf, SPS, target_hz, hint_hz)

        # D8: update hint only on clean plant-model valid result (reason == "none")
        if r_hint.valid and r_hint.reason == "none":
            hint_hz = r_hint.freq_hz

        res.total_fwd += 1
        if not r_orig.valid:
            res.orig_dropout_count += 1
        if not r_hint.valid:
            res.hint_dropout_count += 1

    return res


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    csv_files = sorted(ARTIFACTS_DIR.glob("sweepraw_*.csv"))
    if not csv_files:
        print(f"ERROR: no CSV files found in {ARTIFACTS_DIR}", file=sys.stderr)
        sys.exit(1)

    trap_files = {p for p in csv_files if "_TRAP_" in p.name}

    # Collect results: primary variant = hint_reset_on_dir=True for all files
    results_true: List[FileResult] = []
    results_false: List[FileResult] = []  # only for TRAP files (D-B2)

    for path in csv_files:
        r_true = run_simulation(path, hint_reset_on_dir=True)
        results_true.append(r_true)
        if path in trap_files:
            r_false = run_simulation(path, hint_reset_on_dir=False)
            results_false.append(r_false)

    # ---------------------------------------------------------------------------
    # Stdout table
    # ---------------------------------------------------------------------------
    col_name = 50
    header = (f"{'file':<{col_name}}  {'fwd':>5}  "
              f"{'orig_do%':>8}  {'hint_do%':>8}  {'impr_pp':>7}")
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    false_by_name = {r.name: r for r in results_false}

    for r in results_true:
        tag = ""
        if r.name in false_by_name:
            tag = " (dir=True)"
        name_col = (r.name + tag)[:col_name]
        print(f"{name_col:<{col_name}}  {r.total_fwd:>5}  "
              f"{r.orig_dropout_pct:>8.1f}  {r.hint_dropout_pct:>8.1f}  "
              f"{r.improvement_pp:>+7.1f}")
        # D-B2: also print False variant for TRAP files
        if r.name in false_by_name:
            rf = false_by_name[r.name]
            name_col_f = (rf.name + " (dir=False)")[:col_name]
            print(f"{name_col_f:<{col_name}}  {rf.total_fwd:>5}  "
                  f"{rf.orig_dropout_pct:>8.1f}  {rf.hint_dropout_pct:>8.1f}  "
                  f"{rf.improvement_pp:>+7.1f}")

    # Pooled totals (True variant)
    total_fwd_all = sum(r.total_fwd for r in results_true)
    orig_do_all   = sum(r.orig_dropout_count for r in results_true)
    hint_do_all   = sum(r.hint_dropout_count for r in results_true)
    pooled_orig_pct = 100.0 * orig_do_all / total_fwd_all if total_fwd_all else 0.0
    pooled_hint_pct = 100.0 * hint_do_all / total_fwd_all if total_fwd_all else 0.0
    pooled_impr     = pooled_orig_pct - pooled_hint_pct

    print(sep)
    pooled_label = "POOLED"
    print(f"{pooled_label:<{col_name}}  {total_fwd_all:>5}  "
          f"{pooled_orig_pct:>8.1f}  {pooled_hint_pct:>8.1f}  "
          f"{pooled_impr:>+7.1f}")
    print(sep)

    # Gate verdict (D-C1: visual only)
    gate_ok = pooled_impr >= 1.0
    verdict = "PASS" if gate_ok else "FAIL"
    print(f"\nGate: {pooled_impr:.1f} pp >= 1 pp → {verdict}")
    if not gate_ok:
        print("WARNING: pooled improvement below 1 pp threshold — review before proceeding to Wave 2")

    # ---------------------------------------------------------------------------
    # PNG chart
    # ---------------------------------------------------------------------------
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(max(14, len(results_true) * 0.5), 6))

    names_short = [r.name.replace("sweepraw_", "")[:30] for r in results_true]
    x = np.arange(len(results_true))
    width = 0.35

    bars_orig = ax.bar(x - width / 2,
                       [r.orig_dropout_pct for r in results_true],
                       width, label="orig (single window)", color="#e05c5c")
    bars_hint = ax.bar(x + width / 2,
                       [r.hint_dropout_pct for r in results_true],
                       width, label="hint (dual window)",   color="#5ce05c")

    # Pooled group on the right
    pool_x = len(results_true) + 0.5
    ax.bar(pool_x - width / 2, pooled_orig_pct, width,
           color="#e05c5c", alpha=0.6)
    ax.bar(pool_x + width / 2, pooled_hint_pct, width,
           color="#5ce05c", alpha=0.6)
    ax.text(pool_x, max(pooled_orig_pct, pooled_hint_pct) + 1,
            f"Δ{pooled_impr:+.1f}pp\n{verdict}", ha="center", va="bottom",
            fontsize=9, color="white")

    ax.set_xticks(list(x) + [pool_x])
    ax.set_xticklabels(names_short + ["POOLED"], rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Dropout %")
    ax.set_title("Dual-Window Hint Research — dropout comparison\n"
                 f"Pooled: {pooled_orig_pct:.1f}% → {pooled_hint_pct:.1f}%  "
                 f"(Δ{pooled_impr:+.1f}pp — {verdict})")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=120)
    plt.close(fig)
    print(f"saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
