#!/usr/bin/env python3
"""SWEEPRAW host driver — captures full waveform during one sin/trap cycle.

Streams N×1024 raw ADC samples + per-window duty cmd, saves to CSV,
then runs the offline algorithm bench (is_algo_bench) on each window
and produces a per-window comparison plot.

Usage:
    python3 scripts/is_poc_sweepraw.py --port /dev/ttyACM0 \\
            --shape TRAP --amp 35 --period 4000 --n-windows 25
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import serial


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--shape", choices=["SIN", "TRAP"], default="TRAP")
    ap.add_argument("--amp", type=int, default=35)
    ap.add_argument("--period", type=int, default=4000)
    ap.add_argument("--n-windows", type=int, default=25)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-analyze", action="store_true")
    args = ap.parse_args()

    if args.out is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        suffix = f"_{args.tag}" if args.tag else ""
        name = (f"sweepraw_{args.shape}_amp{args.amp}"
                f"_per{args.period}_n{args.n_windows}_{stamp}{suffix}.csv")
        args.out = (Path(__file__).resolve().parent
                    / "artifacts" / "is-sweepraw" / name)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    timeout_s = args.n_windows * 1.0 + 60.0  # capture + dump

    print(f"opening {args.port} @ {args.baud}")
    with serial.Serial(args.port, args.baud, timeout=5.0) as ser:
        time.sleep(2.0)
        ser.reset_input_buffer()
        ser.write(b"PING\n")
        time.sleep(0.2)
        resp = ser.read_all().decode(errors="replace")
        if "PONG" not in resp:
            print(f"no PONG: {resp!r}", file=sys.stderr)
            return 1

        cmd = (f"SWEEPRAW {args.shape} {args.amp} "
               f"{args.period} {args.n_windows}\n")
        print(f">>> {cmd.strip()}")
        ser.write(cmd.encode())

        windows: list[dict] = []
        in_dump = False
        current_meta = None
        baseline = None
        deadline = time.time() + timeout_s

        while time.time() < deadline:
            line_b = ser.readline()
            if not line_b:
                continue
            line = line_b.decode(errors="replace").strip()
            if not line:
                continue
            if line.startswith("SWEEPRAW_START"):
                in_dump = True
                # parse baseline_adc=
                for tok in line.split():
                    if tok.startswith("baseline_adc="):
                        baseline = float(tok.split("=", 1)[1])
                print(line)
                continue
            if line.startswith("SWEEPRAW_WIN"):
                # SWEEPRAW_WIN <idx> <t_ms> <duty_pct>
                parts = line.split()
                current_meta = {
                    "idx":   int(parts[1]),
                    "t_ms":  int(parts[2]),
                    "duty":  float(parts[3]),
                }
                continue
            if line.startswith("SWEEPRAW_END"):
                print(line)
                break
            if line.startswith("SWEEPRAW_ABORT") or line.startswith("ERROR"):
                print(line, file=sys.stderr)
                break
            if line.startswith("ERR"):
                print(line, file=sys.stderr)
                return 2
            # samples line — only when we just saw a WIN header
            if in_dump and current_meta is not None and "," in line:
                try:
                    vals = [int(v) for v in line.split(",")]
                except ValueError:
                    continue
                current_meta["samples"] = vals
                windows.append(current_meta)
                if current_meta["idx"] % 5 == 0:
                    print(f"  win {current_meta['idx']:2d}  t={current_meta['t_ms']:5d}ms  "
                          f"duty={current_meta['duty']:+6.1f}%  n={len(vals)}")
                current_meta = None

    if not windows:
        print("no windows captured", file=sys.stderr)
        return 3

    # write wide-format CSV: one row per sample, plus a metadata column
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["win_idx", "t_ms", "duty_pct", "sample_idx", "adc_raw"])
        for win in windows:
            for i, v in enumerate(win["samples"]):
                w.writerow([win["idx"], win["t_ms"], f"{win['duty']:.2f}", i, v])
    print(f"wrote {len(windows)} windows × {len(windows[0]['samples'])} samples → {args.out}")
    if baseline is not None:
        print(f"baseline_adc={baseline:.1f}")

    if args.no_analyze:
        return 0

    # delegate to bench in offline mode on this single file
    print("\n--- running offline algorithm bench ---")
    import subprocess
    bench = Path(__file__).resolve().parent / "is_sweepraw_analyze.py"
    if not bench.exists():
        print(f"analyzer missing: {bench}", file=sys.stderr)
        return 0
    rc = subprocess.call([sys.executable, str(bench), str(args.out)])
    return rc


if __name__ == "__main__":
    sys.exit(main())
