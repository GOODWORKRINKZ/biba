#!/usr/bin/env python3
"""IS-signal RPM PoC — capture orchestrator (Phase 06 Task 5).

Drives the rpico_rp2040_is_poc firmware over USB CDC and sweeps a
direction × duty matrix, saving one CSV per capture.

Direction-first command format per D-01:
    CAPTURE <FWD|REV> <duty_pct> <n_samples> <sps>

CSV header per D-13:
    duty,dir,sample_idx,adc_raw

Sweeps FWD + REV for each duty (D-09) with a 500 ms gap (D-10).
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

try:
    import serial  # type: ignore
except ImportError:  # pragma: no cover - serial only required at run-time
    serial = None  # type: ignore

DUTY_POINTS_DEFAULT = [25, 50, 75, 100]
DIRECTIONS = ["FWD", "REV"]
N_SAMPLES_DEFAULT = 4096
SPS_DEFAULT = 10000
SETTLE_MS_DEFAULT = 1500  # firmware default; bench shows IS waveform stabilises ~1 s after duty step


def wait_for_ready(ser, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = ser.readline().decode(errors="replace").strip()
        if line == "IS_POC_READY":
            return
    raise TimeoutError("IS_POC_READY not received within timeout")


def capture_one(ser, duty: int, direction: str, n: int, sps: int,
                settle_ms: int) -> list[int]:
    """Send one CAPTURE command and read back samples.

    Direction-first command per D-01.  Accumulates data across multiple
    readlines until CAPTURE_END is observed (Pitfall 4 fix).
    """
    cmd = f"CAPTURE {direction} {duty} {n} {sps} {settle_ms}\n"
    ser.write(cmd.encode())

    # Wait for header
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if not line:
            continue
        if line.startswith("ERROR"):
            raise RuntimeError(f"firmware error: {line}")
        if line.startswith("CAPTURE_START"):
            break

    # Accumulate CSV-data across as many lines as it takes
    raw_tokens: list[str] = []
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if line == "CAPTURE_END":
            break
        if not line:
            continue
        raw_tokens.extend(line.split(","))

    return [int(x) for x in raw_tokens if x.strip().lstrip("-").isdigit()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Drive IS-PoC firmware and capture ADC bursts to CSV."
    )
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--out", default="artifacts/is-capture")
    parser.add_argument(
        "--duty", nargs="+", type=int, default=DUTY_POINTS_DEFAULT,
        help="Duty cycle percentages to sweep (default: 25 50 75 100)",
    )
    parser.add_argument("--n", type=int, default=N_SAMPLES_DEFAULT)
    parser.add_argument("--sps", type=int, default=SPS_DEFAULT)
    parser.add_argument(
        "--settle-ms", type=int, default=SETTLE_MS_DEFAULT,
        help="Spin-up delay (ms) between PWM command and capture start. "
             "Bumped from old 500 ms to let the motor reach steady state.",
    )
    parser.add_argument(
        "--motor", choices=["left", "right"], required=True,
        help="Motor to drive: left uses IS_LEFT (GP26), right uses IS_RIGHT (GP27)",
    )
    args = parser.parse_args(argv)

    if serial is None:
        print("ERROR: pyserial not installed; pip install pyserial", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ser = serial.Serial(args.port, 115200, timeout=10)
    time.sleep(1.5)
    ser.reset_input_buffer()

    ser.write(b"PING\n")
    pong = ser.readline().decode(errors="replace").strip()
    if pong != "PONG":
        print(f"WARNING: expected PONG, got {pong!r}", file=sys.stderr)

    try:
        for duty in args.duty:
            for direction in DIRECTIONS:
                samples = capture_one(
                    ser, duty, direction, args.n, args.sps, args.settle_ms,
                )
                fname = out_dir / f"duty_{duty:03d}_{direction}_sps{args.sps}.csv"
                with open(fname, "w", newline="") as fh:
                    w = csv.writer(fh)
                    w.writerow(["duty", "dir", "sample_idx", "adc_raw"])
                    for i, v in enumerate(samples):
                        w.writerow([duty, direction, i, v])
                print(f"[capture] duty={duty:3d}% dir={direction} n={len(samples)} -> {fname}")
                time.sleep(0.5)
    finally:
        try:
            ser.write(b"STOP\n")
            ser.readline()
        except Exception:
            pass
        ser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
