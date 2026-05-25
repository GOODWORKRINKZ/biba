#!/usr/bin/env python3
"""Offline ZC algorithm bench.

Replays raw 10 kSPS IS-signal captures from artifacts/is-capture/duty_*.csv
through several candidate detection algorithms and compares their output
to the calibrated plant model `f_expected ≈ K·duty − dead`.

Algorithms benchmarked
----------------------
A1 globalmean_schmitt   – current on-device method (mean+25% hyst)
A2 subwindow_schmitt    – split window in 8 sub-blocks, local mean, sum ZC
A3 hpf_schmitt          – 1-pole DC-blocking HPF (α≈0.97) then ZC at 0
A4 adaptive_midpoint    – running min/max over 200-sample slider
A5 fft_peak             – |FFT| peak in 30–1500 Hz band
A6 autocorr             – first non-trivial peak of autocorrelation

For each algorithm we report frequency in Hz per 1024-sample (102.4 ms)
sub-window, then aggregate (mean ± std) over all sub-windows of the file
and compute absolute error vs the model prediction.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

ROOT = Path(__file__).resolve().parent
DEFAULT_DIR = ROOT / "artifacts" / "is-capture"

# Calibrated plant (from Phase 06 step + steady tests)
PLANT_K_HZ_PER_PCT = 10.13
PLANT_DEAD_HZ = 74.6
SPS = 10000
N_WIN = 1024  # 102.4 ms

# ------------------------------ algorithms ------------------------------

def alg_globalmean_schmitt(x: np.ndarray) -> float:
    """Current on-device method."""
    lo, hi = int(x.min()), int(x.max())
    pkpk = hi - lo
    if pkpk < 40:
        return 0.0
    mid = (lo + hi) / 2.0
    hyst = pkpk / 4.0
    up, dn = mid + hyst, mid - hyst
    state = 1 if x[0] > mid else -1
    n = 0
    for v in x:
        if state > 0 and v < dn:
            state = -1
            n += 1
        elif state < 0 and v > up:
            state = 1
            n += 1
    return n * 0.5 * SPS / len(x)


def alg_subwindow_schmitt(x: np.ndarray, k: int = 8) -> float:
    """Split into k blocks; local mean removes linear drift."""
    n_total = 0
    blk = len(x) // k
    for i in range(k):
        seg = x[i * blk:(i + 1) * blk]
        lo, hi = int(seg.min()), int(seg.max())
        pkpk = hi - lo
        if pkpk < 30:
            continue
        mid = (lo + hi) / 2.0
        hyst = pkpk / 4.0
        up, dn = mid + hyst, mid - hyst
        state = 1 if seg[0] > mid else -1
        for v in seg:
            if state > 0 and v < dn:
                state = -1
                n_total += 1
            elif state < 0 and v > up:
                state = 1
                n_total += 1
    return n_total * 0.5 * SPS / len(x)


def alg_hpf_schmitt(x: np.ndarray, alpha: float = 0.97) -> float:
    """1-pole HPF y[n] = α*(y[n-1] + x[n] - x[n-1]); ZC at 0 with hyst."""
    y = np.empty_like(x, dtype=np.float32)
    y[0] = 0.0
    prev = x[0]
    for i in range(1, len(x)):
        y[i] = alpha * (y[i - 1] + x[i] - prev)
        prev = x[i]
    # adaptive hysteresis from HPF output amplitude
    pkpk = float(y.max() - y.min())
    if pkpk < 20:
        return 0.0
    hyst = pkpk / 8.0  # tighter hyst since baseline is now 0
    state = 1 if y[0] > 0 else -1
    n = 0
    for v in y:
        if state > 0 and v < -hyst:
            state = -1
            n += 1
        elif state < 0 and v > hyst:
            state = 1
            n += 1
    return n * 0.5 * SPS / len(x)


def alg_adaptive_midpoint(x: np.ndarray, slider: int = 200) -> float:
    """Local min/max envelope → midpoint that tracks drift."""
    n = len(x)
    if n < slider * 2:
        return alg_globalmean_schmitt(x)
    # running min/max via simple expanding window (cheap; not real-time tight)
    half = slider // 2
    lo = np.empty(n, dtype=np.int32)
    hi = np.empty(n, dtype=np.int32)
    for i in range(n):
        a = max(0, i - half)
        b = min(n, i + half)
        lo[i] = x[a:b].min()
        hi[i] = x[a:b].max()
    mid = (lo + hi) * 0.5
    pkpk_local = hi - lo
    if pkpk_local.max() < 40:
        return 0.0
    hyst = pkpk_local / 4.0
    crossings = 0
    state = 1 if x[0] > mid[0] else -1
    for i in range(1, n):
        if state > 0 and x[i] < mid[i] - hyst[i]:
            state = -1
            crossings += 1
        elif state < 0 and x[i] > mid[i] + hyst[i]:
            state = 1
            crossings += 1
    return crossings * 0.5 * SPS / n


def alg_fft_peak(x: np.ndarray, f_lo: float = 30.0, f_hi: float = 1500.0) -> float:
    """Pick the dominant FFT bin within [f_lo, f_hi]."""
    n = len(x)
    xf = x.astype(np.float32) - x.mean()
    # Hann window to suppress leakage
    w = np.hanning(n).astype(np.float32)
    xf = xf * w
    spec = np.abs(np.fft.rfft(xf))
    freqs = np.fft.rfftfreq(n, d=1.0 / SPS)
    mask = (freqs >= f_lo) & (freqs <= f_hi)
    if not mask.any():
        return 0.0
    band_spec = spec.copy()
    band_spec[~mask] = 0
    k = int(np.argmax(band_spec))
    if band_spec[k] < spec.sum() * 0.005:  # weak peak → no signal
        return 0.0
    # parabolic interpolation around peak for sub-bin precision
    if 1 <= k < len(spec) - 1:
        a, b, c = spec[k - 1], spec[k], spec[k + 1]
        denom = (a - 2 * b + c)
        delta = 0.5 * (a - c) / denom if denom != 0 else 0.0
    else:
        delta = 0.0
    f_est = (k + delta) * SPS / n
    return float(f_est)


def alg_autocorr(x: np.ndarray, f_lo: float = 30.0, f_hi: float = 1500.0) -> float:
    """First peak of autocorr in lag range [SPS/f_hi, SPS/f_lo]."""
    n = len(x)
    xc = x.astype(np.float32) - x.mean()
    # full autocorr via FFT for speed
    f = np.fft.rfft(xc, n=2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    if ac[0] <= 0:
        return 0.0
    ac = ac / ac[0]
    lag_min = max(2, int(SPS / f_hi))
    lag_max = min(n - 1, int(SPS / f_lo))
    if lag_max <= lag_min + 2:
        return 0.0
    seg = ac[lag_min:lag_max]
    k = int(np.argmax(seg)) + lag_min
    if ac[k] < 0.15:  # weak periodicity
        return 0.0
    if 1 <= k < n - 1:
        a, b, c = ac[k - 1], ac[k], ac[k + 1]
        denom = (a - 2 * b + c)
        delta = 0.5 * (a - c) / denom if denom != 0 else 0.0
    else:
        delta = 0.0
    return float(SPS / (k + delta))


ALGOS: dict[str, Callable[[np.ndarray], float]] = {
    "A1_globmean_schmitt": alg_globalmean_schmitt,
    "A2_subwin_schmitt":   alg_subwindow_schmitt,
    "A3_hpf_schmitt":      alg_hpf_schmitt,
    "A4_adapt_midpoint":   alg_adaptive_midpoint,
    "A5_fft_peak":         alg_fft_peak,
    "A6_autocorr":         alg_autocorr,
}


# ------------------------------ helpers ------------------------------

@dataclass
class Capture:
    name: str
    duty: int
    direction: str
    samples: np.ndarray  # int16


def load_capture(path: Path) -> Capture:
    duty = None
    direction = None
    samples: list[int] = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if duty is None:
                duty = int(row["duty"])
                direction = row["dir"]
            samples.append(int(row["adc_raw"]))
    return Capture(name=path.stem, duty=duty or 0,
                   direction=direction or "?",
                   samples=np.asarray(samples, dtype=np.int32))


def expected_hz(duty_pct: int) -> float:
    """Plant model. Sign-agnostic (we use |duty|)."""
    f = PLANT_K_HZ_PER_PCT * abs(duty_pct) - PLANT_DEAD_HZ
    return max(0.0, f)


# ------------------------------ main ------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts" /
                    "is-algo-bench" / "bench.csv")
    ap.add_argument("--plot", type=Path, default=ROOT / "artifacts" /
                    "is-algo-bench" / "bench.png")
    ap.add_argument("--waveforms", action="store_true",
                    help="Also dump per-capture waveform/HPF plots.")
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    paths = sorted(args.in_dir.glob("duty_*.csv"))
    if not paths:
        print(f"no CSVs in {args.in_dir}", file=sys.stderr)
        return 1

    captures = [load_capture(p) for p in paths]

    # Per (capture × algorithm) → list of sub-window estimates
    results: dict[str, dict[str, list[float]]] = {}
    for cap in captures:
        n_wins = len(cap.samples) // N_WIN
        if n_wins == 0:
            continue
        results[cap.name] = {alg: [] for alg in ALGOS}
        for i in range(n_wins):
            seg = cap.samples[i * N_WIN:(i + 1) * N_WIN]
            for alg, fn in ALGOS.items():
                try:
                    f = fn(seg)
                except Exception as e:
                    print(f"{cap.name}/{alg}: {e}", file=sys.stderr)
                    f = float("nan")
                results[cap.name][alg].append(f)

    # write CSV
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["capture", "duty", "dir", "expected_hz", "algo",
                    "n_windows", "mean_hz", "std_hz", "err_hz", "err_pct"])
        for cap in captures:
            exp = expected_hz(cap.duty)
            for alg in ALGOS:
                vals = results[cap.name][alg]
                arr = np.asarray(vals, dtype=np.float32)
                m = float(arr.mean()) if arr.size else float("nan")
                s = float(arr.std())  if arr.size else float("nan")
                err = m - exp
                err_pct = (err / exp * 100.0) if exp > 1e-3 else float("nan")
                w.writerow([cap.name, cap.duty, cap.direction,
                            f"{exp:.1f}", alg, arr.size,
                            f"{m:.1f}", f"{s:.1f}",
                            f"{err:.1f}", f"{err_pct:.1f}"])

    # console table
    print(f"\nGround truth: f = {PLANT_K_HZ_PER_PCT}·|duty| − {PLANT_DEAD_HZ}")
    print(f"Window size: {N_WIN} samples ({N_WIN*1000/SPS:.1f} ms)\n")
    header = f"{'capture':28s} {'exp':>6s}"
    for alg in ALGOS:
        header += f" {alg:>22s}"
    print(header)
    print("-" * len(header))
    for cap in captures:
        exp = expected_hz(cap.duty)
        line = f"{cap.name:28s} {exp:6.1f}"
        for alg in ALGOS:
            arr = np.asarray(results[cap.name][alg])
            m = float(arr.mean())
            s = float(arr.std())
            err = m - exp
            line += f" {m:8.0f}±{s:4.0f}({err:+5.0f})"
        print(line)

    # plot: grouped bars per capture, one bar per algorithm; line = expected
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping plot")
        return 0

    cap_names = [c.name for c in captures]
    expecteds = [expected_hz(c.duty) for c in captures]
    n_algos = len(ALGOS)
    x = np.arange(len(cap_names))
    width = 0.8 / n_algos

    fig, ax = plt.subplots(figsize=(13, 6))
    colors = plt.cm.tab10(np.linspace(0, 1, n_algos))
    for i, alg in enumerate(ALGOS):
        means = [float(np.mean(results[c.name][alg])) for c in captures]
        stds = [float(np.std(results[c.name][alg])) for c in captures]
        ax.bar(x + i * width - 0.4 + width / 2,
               means, width, yerr=stds, label=alg,
               color=colors[i], alpha=0.85, capsize=2)

    # expected as black dashed markers
    ax.plot(x, expecteds, "kD", ms=10, mfc="none", mew=2,
            label=f"expected ({PLANT_K_HZ_PER_PCT}·d − {PLANT_DEAD_HZ})")
    ax.set_xticks(x)
    ax.set_xticklabels(cap_names, rotation=25, ha="right")
    ax.set_ylabel("commutation freq estimate (Hz)")
    ax.set_title("ZC algorithm bench on Phase 04 captures")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.plot, dpi=110)
    print(f"\nplot → {args.plot}")
    print(f"csv  → {args.out}")

    # optional per-capture waveform comparison
    if args.waveforms:
        wdir = args.plot.parent / "waveforms"
        wdir.mkdir(parents=True, exist_ok=True)
        for cap in captures:
            seg = cap.samples[:N_WIN].astype(np.float32)
            # HPF preview
            y = np.empty_like(seg)
            y[0] = 0.0
            for i in range(1, len(seg)):
                y[i] = 0.97 * (y[i - 1] + seg[i] - seg[i - 1])
            # FFT preview
            xf = seg - seg.mean()
            xf *= np.hanning(len(xf)).astype(np.float32)
            spec = np.abs(np.fft.rfft(xf))
            freqs = np.fft.rfftfreq(len(xf), d=1.0 / SPS)

            fig2, axs = plt.subplots(3, 1, figsize=(10, 7))
            t_ms = np.arange(N_WIN) * 1000.0 / SPS
            axs[0].plot(t_ms, seg)
            axs[0].set_title(f"{cap.name} raw (1st window)")
            axs[0].set_ylabel("ADC")
            axs[0].grid(alpha=0.3)
            axs[1].plot(t_ms, y, color="tab:purple")
            axs[1].axhline(0, color="grey", lw=0.5)
            axs[1].set_title("HPF (α=0.97)")
            axs[1].set_ylabel("HPF out")
            axs[1].set_xlabel("ms")
            axs[1].grid(alpha=0.3)
            axs[2].plot(freqs, spec, color="tab:red")
            axs[2].set_xlim(0, 2000)
            axs[2].set_title("FFT magnitude")
            axs[2].set_xlabel("Hz")
            axs[2].grid(alpha=0.3)
            fig2.tight_layout()
            fig2.savefig(wdir / f"{cap.name}.png", dpi=100)
            plt.close(fig2)
        print(f"waveforms → {wdir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
