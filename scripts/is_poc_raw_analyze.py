#!/usr/bin/env python3
"""IS-signal raw ADC capture + analysis.

Captures raw ADC samples from IS_POC firmware via CAPTURE command,
then plots time domain + FFT to understand what the ZC detector actually sees.

Usage:
    python3 scripts/is_poc_raw_analyze.py --port /dev/ttyACM0 --duty 40
    python3 scripts/is_poc_raw_analyze.py --port /dev/ttyACM0 --duty 40 --motor right
    python3 scripts/is_poc_raw_analyze.py --port /dev/ttyACM0 --duty 40 --both
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
import numpy as np

try:
    import serial
except ImportError:
    print("ERROR: pip install pyserial"); sys.exit(1)

try:
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    HAS_PLT = True
except ImportError:
    HAS_PLT = False
    print("WARNING: matplotlib not found, will save data but not plot")


ARTIFACTS_DIR = Path(__file__).parent / "artifacts" / "is-raw"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def wait_ready(ser, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = ser.readline().decode(errors="replace").strip()
        if line == "IS_POC_READY":
            return
    # not critical — just means it was already running


def capture(ser, motor: str, duty: int, n: int, sps: int, settle_ms: int) -> np.ndarray:
    """Send CAPTURE / CAPTURE_R and return raw uint16 samples."""
    cmd_name = "CAPTURE_R" if motor == "right" else "CAPTURE"
    cmd = f"{cmd_name} FWD {duty} {n} {sps} {settle_ms}\n"
    print(f"  → sending: {cmd.strip()}")
    ser.reset_input_buffer()
    ser.write(cmd.encode())

    # wait for CAPTURE_START header
    t0 = time.monotonic()
    header = {}
    while time.monotonic() - t0 < 15.0:
        line = ser.readline().decode(errors="replace").strip()
        if not line:
            continue
        if line.startswith("ERROR"):
            raise RuntimeError(f"firmware: {line}")
        if line.startswith("CAPTURE_START"):
            # parse key=val pairs
            for tok in line.split()[1:]:
                k, _, v = tok.partition("=")
                header[k] = v
            print(f"  ← {line}")
            break

    # read CSV data until CAPTURE_END
    tokens: list[str] = []
    while time.monotonic() - t0 < 30.0:
        line = ser.readline().decode(errors="replace").strip()
        if line == "CAPTURE_END":
            break
        if line:
            tokens.extend(line.split(","))

    samples = np.array([int(x) for x in tokens if x.strip().lstrip("-").isdigit()],
                       dtype=np.uint16)
    print(f"  got {len(samples)} samples, sps={header.get('sps','?')}, chan={header.get('chan','?')}")
    return samples


def analyze_and_plot(samples: np.ndarray, sps: int, label: str, duty: int,
                     ax_time, ax_fft):
    """Fill provided axes with time-domain and FFT plots."""
    t = np.arange(len(samples)) / sps * 1000.0  # ms

    # Time domain
    ax_time.plot(t, samples, linewidth=0.5, color="steelblue")
    ax_time.set_title(f"{label} — time domain (duty={duty}%)", fontsize=9)
    ax_time.set_xlabel("time (ms)")
    ax_time.set_ylabel("ADC raw (0-4095)")
    ax_time.grid(True, alpha=0.3)

    # DC-remove for FFT
    sig = samples.astype(np.float32) - np.mean(samples)
    # Hann window
    win = np.hanning(len(sig))
    sig_w = sig * win

    N = len(sig_w)
    freqs = np.fft.rfftfreq(N, d=1.0 / sps)
    mag = np.abs(np.fft.rfft(sig_w)) * 2.0 / N

    # Find top peaks below 2000 Hz (motor range)
    mask = freqs < 2000
    freqs_m = freqs[mask]
    mag_m = mag[mask]

    # peak detection — local maxima with prominence
    from scipy.signal import find_peaks
    peaks, props = find_peaks(mag_m, height=np.max(mag_m) * 0.05, distance=5)
    top_peaks = sorted(peaks, key=lambda i: mag_m[i], reverse=True)[:5]

    ax_fft.plot(freqs_m, mag_m, linewidth=0.8, color="darkorange")
    for pk in top_peaks:
        ax_fft.axvline(freqs_m[pk], color="red", linewidth=0.8, alpha=0.7,
                       label=f"{freqs_m[pk]:.1f} Hz")
        ax_fft.annotate(f"{freqs_m[pk]:.0f} Hz",
                        xy=(freqs_m[pk], mag_m[pk]),
                        xytext=(5, 5), textcoords="offset points",
                        fontsize=7, color="red")
    ax_fft.set_title(f"{label} — FFT (< 2 kHz)", fontsize=9)
    ax_fft.set_xlabel("frequency (Hz)")
    ax_fft.set_ylabel("|FFT| (ADC counts)")
    ax_fft.grid(True, alpha=0.3)
    if top_peaks:
        ax_fft.legend(fontsize=7)

    # Print dominant freq
    dominant = freqs_m[top_peaks[0]] if top_peaks else 0.0
    print(f"  dominant freq: {dominant:.1f} Hz  (pkpk={int(samples.max()-samples.min())}  mean={np.mean(samples):.0f})")
    return dominant


def main():
    ap = argparse.ArgumentParser(description="IS raw ADC capture and FFT analysis")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--duty", type=int, default=40, help="motor duty %%")
    ap.add_argument("--n", type=int, default=8192, help="samples per capture")
    ap.add_argument("--sps", type=int, default=10000)
    ap.add_argument("--settle-ms", type=int, default=2000)
    ap.add_argument("--motor", choices=["left", "right"], default="left")
    ap.add_argument("--both", action="store_true", help="capture both motors sequentially")
    args = ap.parse_args()

    # scipy needed for peak detection
    try:
        from scipy.signal import find_peaks  # noqa: F401
    except ImportError:
        print("ERROR: pip install scipy"); sys.exit(1)

    print(f"Connecting to {args.port} ...")
    ser = serial.Serial(args.port, args.baud, timeout=20)
    time.sleep(0.5)
    ser.write(b"PING\n")
    pong = ser.readline().decode(errors="replace").strip()
    print(f"  {pong}")

    motors = ["left", "right"] if args.both else [args.motor]

    if HAS_PLT:
        fig = plt.figure(figsize=(14, 4 * len(motors)))
        gs = gridspec.GridSpec(len(motors), 2, figure=fig)
        fig.suptitle(f"IS raw ADC analysis — duty={args.duty}%  sps={args.sps}  n={args.n}", fontsize=11)

    results = {}
    for idx, motor in enumerate(motors):
        label = f"{motor.upper()} motor (IS_{motor.upper()})"
        print(f"\n[{label}]")
        samples = capture(ser, motor, args.duty, args.n, args.sps, args.settle_ms)

        # Save raw CSV
        ts = time.strftime("%Y%m%d_%H%M%S")
        csv_path = ARTIFACTS_DIR / f"raw_{motor}_{args.duty}pct_{ts}.csv"
        np.savetxt(str(csv_path), samples.astype(int), fmt="%d", delimiter=",")
        print(f"  saved → {csv_path}")

        if HAS_PLT:
            ax_t = fig.add_subplot(gs[idx, 0])
            ax_f = fig.add_subplot(gs[idx, 1])
            dom = analyze_and_plot(samples, args.sps, label, args.duty, ax_t, ax_f)
            results[motor] = dom

    ser.close()

    if HAS_PLT:
        plt.tight_layout()
        out = ARTIFACTS_DIR / f"raw_analysis_{time.strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(str(out), dpi=150)
        print(f"\nPlot saved → {out}")
        plt.show()


if __name__ == "__main__":
    main()
