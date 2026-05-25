#!/usr/bin/env python3
"""Analyze a SWEEPRAW capture: run all candidate ZC algorithms per-window
and plot how each tracks the duty cmd through rise/hold/fall/reversal.
Also runs a Python port of the firmware biba_rpm_spectral_estimate()
Goertzel estimator with quality output."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

# import algorithm bench
sys.path.insert(0, str(Path(__file__).resolve().parent))
from is_algo_bench import (  # noqa: E402
    ALGOS, PLANT_K_HZ_PER_PCT, PLANT_DEAD_HZ, SPS,
)

# ---------------------------------------------------------------------------
# Python port of firmware rpm_spectral_estimator.c
# Constants mirror rpm_spectral_estimator.h
# ---------------------------------------------------------------------------
_SPEC_MIN_HZ       = 50.0
_SPEC_MAX_HZ       = 1200.0
_SPEC_REL_BAND     = 0.35
_SPEC_ABS_BAND_HZ  = 80.0
_SPEC_MIN_AMP      = 45.0
_SPEC_MIN_QUALITY  = 3.0


@dataclass
class SpectralResult:
    freq_hz:      float = 0.0
    candidate_hz: float = 0.0
    peak_amp:     float = 0.0
    quality:      float = 0.0
    valid:        bool  = False
    reason:       str   = "none"


def _goertzel_amp(buf: np.ndarray, mean: float, k: int) -> float:
    n = len(buf)
    omega = 2.0 * math.pi * k / n
    coeff = 2.0 * math.cos(omega)
    q1 = q2 = 0.0
    for v in buf:
        q0 = (v - mean) + coeff * q1 - q2
        q2, q1 = q1, q0
    power = q1 * q1 + q2 * q2 - coeff * q1 * q2
    if power <= 0.0:
        return 0.0
    return 2.0 * math.sqrt(power) / n


def spectral_estimate(buf: np.ndarray, sps: int, target_hz: float) -> SpectralResult:
    r = SpectralResult()
    n = len(buf)
    if n < 64 or sps == 0:
        r.reason = "short"
        return r
    if target_hz < _SPEC_MIN_HZ:
        r.reason = "target_low"
        return r

    target_hz = max(_SPEC_MIN_HZ, min(_SPEC_MAX_HZ, target_hz))
    half_band = max(target_hz * _SPEC_REL_BAND, _SPEC_ABS_BAND_HZ)
    f_lo = max(_SPEC_MIN_HZ, target_hz - half_band)
    f_hi = min(_SPEC_MAX_HZ, target_hz + half_band)
    bin_hz = sps / n
    k_lo = max(1, math.ceil(f_lo / bin_hz))
    k_hi = min(n // 2, math.floor(f_hi / bin_hz))
    if k_hi < k_lo:
        r.reason = "no_band"
        return r

    mean = float(buf.mean())
    best_bin, best_amp, second_amp = k_lo, 0.0, 0.0
    for k in range(k_lo, k_hi + 1):
        amp = _goertzel_amp(buf, mean, k)
        if amp > best_amp:
            second_amp = best_amp
            best_amp = amp
            best_bin = k
        elif amp > second_amp:
            second_amp = amp

    # noise floor = mean amp of bins not adjacent to best_bin
    noise_vals = [_goertzel_amp(buf, mean, k)
                  for k in range(k_lo, k_hi + 1)
                  if abs(k - best_bin) > 1]
    noise_amp = sum(noise_vals) / len(noise_vals) if noise_vals else 0.0

    r.peak_amp = best_amp
    r.quality  = best_amp / (noise_amp + 1.0)

    # parabolic interpolation for sub-bin accuracy
    delta = 0.0
    k_max = n // 2
    if 1 < best_bin < k_max:
        left  = _goertzel_amp(buf, mean, best_bin - 1)
        right = _goertzel_amp(buf, mean, best_bin + 1)
        denom = left - 2.0 * best_amp + right
        if denom != 0.0:
            delta = max(-0.5, min(0.5, 0.5 * (left - right) / denom))

    r.candidate_hz = (best_bin + delta) * bin_hz

    if best_amp < _SPEC_MIN_AMP:
        r.reason = "peak_low"
        return r

    r.freq_hz = r.candidate_hz
    r.valid   = True
    r.reason  = "none"
    return r


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

    # --- spectral estimator (Goertzel, firmware port) per window -----------
    spec_hz   = np.full(len(windows), np.nan)
    spec_cand = np.full(len(windows), np.nan)
    spec_q    = np.full(len(windows), np.nan)
    for i, w in enumerate(windows):
        tgt = expected_hz(w["duty"])
        r = spectral_estimate(np.asarray(w["samples"], dtype=np.float32), SPS, tgt)
        spec_cand[i] = r.candidate_hz
        spec_q[i]    = r.quality
        if r.valid:
            spec_hz[i] = r.freq_hz

    mask_spin = exp > 50.0
    if mask_spin.any():
        err_spec = np.abs(np.where(~np.isnan(spec_hz), spec_hz, 0.0)[mask_spin] - exp[mask_spin])
        print(f"{'spectral_goertzel':22s}  {err_spec.mean():9.1f}  {np.median(err_spec):9.1f}  {err_spec.max():9.1f}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return 0

    OLD_THR = _SPEC_MIN_QUALITY
    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
    fig.suptitle(f"After accepting quality-low candidates: target vs spectral — {args.csv.name}", fontsize=9)

    # Hz subplot – target, spectral output, candidate
    for side, (hz_arr, cand_arr, q_arr, label_prefix) in enumerate([
            (spec_hz, spec_cand, spec_q, ""),
    ]):
        ax_hz = axes[0]
        ax_hz.plot(t, exp,       "k-",  lw=2,   label="target")
        ax_hz.plot(t, spec_hz,   "C0-", lw=1.5, label="spectral output", alpha=0.9)
        ax_hz.plot(t, spec_cand, color="silver", lw=1, label="candidate", alpha=0.7)
        ax_hz.set_ylabel("Hz")
        ax_hz.legend(fontsize=8)
        ax_hz.grid(alpha=0.3)

        ax_q = axes[1]
        ax_q.plot(t, spec_q, "g-", lw=1.2, label="quality")
        ax_q.axhline(OLD_THR, color="red", ls="--", lw=1, label=f"old threshold ({OLD_THR})")
        ax_q.set_ylabel("quality")
        ax_q.legend(fontsize=8)
        ax_q.grid(alpha=0.3)

    # duty curve
    ax_duty = axes[2]
    ax_duty.plot(t, duty, "k-", lw=1.5, label="duty %")
    ax_duty.axhline(0, color="grey", lw=0.5)
    ax_duty.set_ylabel("duty %")
    ax_duty.legend(fontsize=8)
    ax_duty.grid(alpha=0.3)

    # ZC algos for reference
    ax_zc = axes[3]
    ax_zc.plot(t, exp, "k--", lw=1.5, label="target (model)", alpha=0.5)
    colors = plt.cm.tab10(np.linspace(0, 1, len(ALGOS)))
    for (alg, est), c in zip(estimates.items(), colors):
        ax_zc.plot(t, est, "-", lw=1, color=c, label=alg, alpha=0.7)
    ax_zc.set_ylabel("ZC algos Hz")
    ax_zc.set_xlabel("time (s)")
    ax_zc.legend(fontsize=7, ncol=3)
    ax_zc.grid(alpha=0.3)

    fig.tight_layout()
    out_png = args.out or args.csv.with_suffix(".png")
    fig.savefig(out_png, dpi=110)
    print(f"\nplot → {out_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
