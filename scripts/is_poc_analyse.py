#!/usr/bin/env python3
"""IS-signal RPM PoC — capture analyser (Phase 06 Task 6).

Loads CSVs produced by is_poc_capture.py (header: duty,dir,sample_idx,adc_raw)
and recovers the dominant IS-frequency per capture via three independent
estimators: FFT peak, zero-crossing rate, autocorrelation peak.

For each direction (FWD / REV) it computes R² of duty-vs-frequency
linearity and emits one PNG with two subplots:
 - Welch PSDs of every capture
 - duty-vs-frequency scatter with per-algorithm best-fit lines.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.signal import find_peaks, welch  # noqa: E402

_FNAME_RE = re.compile(r"duty_(\d+)_(FWD|REV)")


def load_csv(path: Path) -> tuple[np.ndarray, int, str]:
    """Return (samples, duty, direction) for one capture CSV."""
    values: list[float] = []
    duty: int | None = None
    direction: str | None = None
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if "adc_raw" not in row:
                break
            values.append(float(row["adc_raw"]))
            if duty is None:
                try:
                    duty = int(row.get("duty", "0"))
                except ValueError:
                    duty = None
                direction = row.get("dir") or None

    if duty is None or direction is None:
        m = _FNAME_RE.search(path.name)
        if m:
            duty = int(m.group(1))
            direction = m.group(2)
        else:
            raise ValueError(f"cannot infer duty/dir from {path}")

    return np.asarray(values, dtype=float), int(duty), str(direction)


def freq_fft(samples: np.ndarray, sps: int) -> float:
    n = len(samples)
    if n < 4:
        return 0.0
    # DC removal before windowing — otherwise Hanning side-lobes of the
    # large DC component leak into the low-frequency RPM band.
    ac = samples - samples.mean()
    window = np.hanning(n)
    spectrum = np.abs(np.fft.rfft(ac * window))
    freqs = np.fft.rfftfreq(n, d=1.0 / sps)
    # Time-domain plot shows RPM-modulated IS at 2–20 Hz across the duty
    # sweep.  Search 1–200 Hz; the PWM comb above that is irrelevant.
    mask = (freqs >= 1.0) & (freqs <= 200.0)
    if not mask.any():
        return 0.0
    return float(freqs[mask][int(np.argmax(spectrum[mask]))])


def freq_zero_crossing(samples: np.ndarray, sps: int) -> float:
    """Schmitt-trigger zero-crossing rate.

    A naive `signal > threshold` detector glitches on noisy slow signals
    because the signal hovers near the threshold for many samples while
    noise oscillates around it.  We use a two-level hysteresis (Schmitt
    trigger) so a False→True transition requires crossing `+hi` and the
    inverse requires crossing `-lo`.  Hysteresis is sized to the AC std
    of the signal so it scales with amplitude.
    """
    if len(samples) < 4:
        return 0.0
    ac = samples - samples.mean()
    sigma = float(ac.std())
    if sigma <= 0.0:
        return 0.0
    hi = sigma * 0.5
    lo = -sigma * 0.5

    crossings: list[int] = []
    state_high = False
    for i, v in enumerate(ac):
        if state_high:
            if v < lo:
                state_high = False
        else:
            if v > hi:
                state_high = True
                crossings.append(i)
    if len(crossings) < 2:
        return 0.0
    period = float(np.median(np.diff(crossings)))
    if period <= 0.0:
        return 0.0
    return float(sps) / period


def freq_autocorr(samples: np.ndarray, sps: int) -> float:
    if len(samples) < 4:
        return 0.0
    ac = samples - samples.mean()
    if ac.std() == 0.0:
        return 0.0
    corr = np.correlate(ac, ac, mode="full")[len(ac) - 1:]
    # Search 5 ms (200 Hz) lag floor.  Cap max lag at min(500 ms, N/3) —
    # the N/3 cap keeps the /overlap normalisation well-conditioned
    # (overlap ≥ 2N/3, division is stable).  Without the cap the
    # normalised autocorr blows up in the tail and reports spurious
    # ultra-low-frequency peaks.
    min_lag = max(int(sps * 0.005), 1)
    max_lag = min(int(sps * 0.5), len(ac) // 3)
    max_lag = min(max_lag, len(corr) - 1)
    if max_lag <= min_lag + 1:
        return 0.0
    # Normalise by overlap count: np.correlate returns unnormalised sums
    # whose envelope tapers as (N - lag), which biases peak detection
    # toward short lags.  After /overlap the fundamental and its
    # harmonics have ~equal amplitude for a clean sine, so we cannot
    # rely on global argmax — it would pick a random harmonic under
    # noise.  Instead, take the FIRST sufficiently prominent peak in
    # the search window: that is, by definition, the fundamental
    # period of the signal.
    overlap = np.arange(len(corr), 0, -1, dtype=float)
    norm = corr / overlap
    segment = norm[min_lag:max_lag]
    # Prominence threshold: at least 30 % of the peak-to-trough range
    # in the search window — enough to reject noise micro-peaks while
    # accepting both clean sine peaks and the lower-SNR real captures.
    prominence = 0.3 * (segment.max() - segment.min())
    peaks, _ = find_peaks(segment, prominence=prominence)
    if len(peaks) == 0:
        # Fall back to global max if no prominent peak found.
        peak_idx = int(np.argmax(segment)) + min_lag
    else:
        peak_idx = int(peaks[0]) + min_lag
    if peak_idx <= 0:
        return 0.0
    return float(sps) / float(peak_idx)


def r_squared(x: list[float], y: list[float]) -> float:
    if len(x) < 2 or len(y) < 2:
        return 0.0
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    slope, intercept = np.polyfit(xa, ya, 1)
    pred = slope * xa + intercept
    ss_res = float(np.sum((ya - pred) ** 2))
    ss_tot = float(np.sum((ya - ya.mean()) ** 2))
    if ss_tot == 0.0:
        return 0.0
    return 1.0 - ss_res / ss_tot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyse IS-PoC capture CSVs.")
    parser.add_argument("--dir", default="artifacts/is-capture",
                        help="Directory containing duty_*.csv files")
    parser.add_argument("--sps", type=int, default=10000)
    args = parser.parse_args(argv)

    cap_dir = Path(args.dir)
    files = sorted(cap_dir.glob("duty_*.csv"))
    if not files:
        print(f"no CSVs found in {cap_dir}", file=sys.stderr)
        return 1

    results = []  # list of dicts {duty, dir, samples, f_fft, f_zc, f_ac}
    for path in files:
        samples, duty, direction = load_csv(path)
        f_fft = freq_fft(samples, args.sps)
        f_zc = freq_zero_crossing(samples, args.sps)
        f_ac = freq_autocorr(samples, args.sps)
        print(
            f"duty={duty:3d}%  dir={direction}  "
            f"FFT={f_fft:7.1f}Hz  ZC={f_zc:7.1f}Hz  AC={f_ac:7.1f}Hz"
        )
        results.append({
            "duty": duty, "dir": direction, "samples": samples,
            "f_fft": f_fft, "f_zc": f_zc, "f_ac": f_ac,
        })

    # R² per direction, per algorithm
    def _r2(direction: str, key: str) -> float:
        xs = [r["duty"] for r in results if r["dir"] == direction]
        ys = [r[key] for r in results if r["dir"] == direction]
        return r_squared(xs, ys)

    r2_fwd_fft = _r2("FWD", "f_fft")
    r2_fwd_zc = _r2("FWD", "f_zc")
    r2_fwd_ac = _r2("FWD", "f_ac")
    r2_rev_fft = _r2("REV", "f_fft")
    r2_rev_zc = _r2("REV", "f_zc")
    r2_rev_ac = _r2("REV", "f_ac")
    print(f"R² FWD — FFT:{r2_fwd_fft:.3f}  ZC:{r2_fwd_zc:.3f}  AC:{r2_fwd_ac:.3f}")
    print(f"R² REV — FFT:{r2_rev_fft:.3f}  ZC:{r2_rev_zc:.3f}  AC:{r2_rev_ac:.3f}")

    # PNG: PSDs + scatter
    fig, (ax_psd, ax_scatter) = plt.subplots(1, 2, figsize=(14, 6))
    for r in results:
        # nperseg = full capture for best low-frequency resolution:
        # Δf = sps/N ≈ 2.4 Hz at 4096 samples @ 10 kSPS.
        nps = min(len(r["samples"]), 4096)
        f, pxx = welch(r["samples"], fs=args.sps, nperseg=nps)
        ax_psd.semilogy(f, pxx, label=f"duty={r['duty']}% {r['dir']}", linewidth=0.8)
    ax_psd.set_xlabel("Frequency (Hz)")
    ax_psd.set_ylabel("PSD (mV²/Hz)")
    ax_psd.set_title("Welch PSD per capture (RPM band)")
    ax_psd.set_xlim(0, 200)
    ax_psd.legend(fontsize=7, ncol=2)
    ax_psd.grid(True, which="both", alpha=0.3)

    for direction, marker_style in [("FWD", "o"), ("REV", "s")]:
        rows = [r for r in results if r["dir"] == direction]
        if not rows:
            continue
        duties = [r["duty"] for r in rows]
        for key, label_short in [("f_fft", "FFT"), ("f_zc", "ZC"), ("f_ac", "AC")]:
            ys = [r[key] for r in rows]
            r2 = r_squared(duties, ys)
            face = "none" if direction == "REV" else None
            ax_scatter.scatter(
                duties, ys, marker=marker_style, facecolors=face,
                label=f"{label_short} {direction} R²={r2:.2f}",
            )
    ax_scatter.set_xlabel("Duty (%)")
    ax_scatter.set_ylabel("IS frequency (Hz)")
    ax_scatter.set_title("Duty vs peak frequency")
    ax_scatter.legend(fontsize=8)
    ax_scatter.grid(True, alpha=0.3)

    out_png = cap_dir / "is_spectrum_analysis.png"
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[plot] wrote {out_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
