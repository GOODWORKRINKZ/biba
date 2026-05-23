#!/usr/bin/env python3
"""IS-signal PoC — open-loop sinusoidal / trapezoidal duty sweep.

Drives the motor with a bidirectional duty modulation (sin or trapezoid)
while linearly chirping the period from p_start to p_end.  Streams raw
ZC frequency, mean current, pkpk ADC, and ZC count per 100 ms window —
the inputs that drive the on-device ZC detector — so we can study how
the commutation spike behaves on rise / hold / fall transitions and on
direction reversals.

Usage:
    python3 scripts/is_poc_sweep.py --port /dev/ttyACM0 \\
            --shape SIN --amp 40 --p-start 3000 --p-end 500 --duration 15000
    python3 scripts/is_poc_sweep.py --port /dev/ttyACM0 \\
            --shape TRAP --amp 35 --p-start 4000 --p-end 1000 --duration 20000
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import serial


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--shape", choices=["SIN", "TRAP"], default="SIN")
    parser.add_argument("--amp", type=int, default=40,
                        help="Peak |duty| in %% (0-80).")
    parser.add_argument("--p-start", type=int, default=3000,
                        help="Initial modulation period (ms).")
    parser.add_argument("--p-end", type=int, default=500,
                        help="Final modulation period (ms, linear chirp).")
    parser.add_argument("--duration", type=int, default=15000,
                        help="Total sweep duration (ms).")
    parser.add_argument("--out", type=Path, default=None,
                        help="CSV path; default auto-named from params.")
    parser.add_argument("--tag", default="",
                        help="Extra suffix appended to auto filename.")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    if args.out is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        suffix = f"_{args.tag}" if args.tag else ""
        name = (f"sweep_{args.shape}_amp{args.amp}"
                f"_p{args.p_start}-{args.p_end}"
                f"_d{args.duration}_{stamp}{suffix}.csv")
        args.out = (Path(__file__).resolve().parent
                    / "artifacts" / "is-sweep" / name)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    timeout = args.duration / 1000.0 + 15.0

    print(f"opening {args.port} @ {args.baud}")
    with serial.Serial(args.port, args.baud, timeout=2.0) as ser:
        time.sleep(2.0)
        ser.reset_input_buffer()
        ser.write(b"PING\n")
        time.sleep(0.2)
        resp = ser.read_all().decode(errors="replace")
        if "PONG" not in resp:
            print(f"no PONG — got: {resp!r}", file=sys.stderr)
            return 1

        cmd = (f"SWEEP {args.shape} {args.amp} "
               f"{args.p_start} {args.p_end} {args.duration}\n")
        print(f">>> {cmd.strip()}")
        ser.write(cmd.encode())

        rows: list[dict] = []
        header_written = False
        with open(args.out, "w", newline="") as fh:
            writer = csv.writer(fh)
            deadline = time.time() + timeout
            while time.time() < deadline:
                line_b = ser.readline()
                if not line_b:
                    continue
                line = line_b.decode(errors="replace").strip()
                if not line:
                    continue
                print(line)
                if line.startswith("SWEEP_START"):
                    continue
                if line.startswith("SWEEP_DATA"):
                    body = line[len("SWEEP_DATA"):].strip()
                    if body.startswith("t_ms"):
                        writer.writerow([c.strip() for c in body.split(",")])
                        header_written = True
                        continue
                    if not header_written:
                        continue
                    parts = [p.strip() for p in body.split(",")]
                    if len(parts) != 6:
                        continue
                    writer.writerow(parts)
                    try:
                        rows.append({
                            "t_ms":    float(parts[0]),
                            "duty":    float(parts[1]),
                            "meas_hz": float(parts[2]),
                            "curr_a":  float(parts[3]),
                            "pkpk":    float(parts[4]),
                            "zc_n":    float(parts[5]),
                        })
                    except ValueError:
                        pass
                elif line.startswith("SWEEP_END") or line.startswith("SWEEP_ABORT"):
                    break

    print(f"wrote {len(rows)} samples → {args.out}")

    if args.no_plot or not rows:
        return 0

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping plot")
        return 0

    t = [r["t_ms"] / 1000.0 for r in rows]
    duty = [r["duty"] for r in rows]
    meas = [r["meas_hz"] for r in rows]
    curr = [r["curr_a"] for r in rows]
    pkpk = [r["pkpk"] for r in rows]
    zcn = [r["zc_n"] for r in rows]

    fig, axes = plt.subplots(4, 1, figsize=(11, 10), sharex=True)

    ax = axes[0]
    ax.plot(t, duty, color="tab:blue", label="duty cmd %")
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_ylabel("duty %")
    ax.set_title(f"SWEEP {args.shape} amp={args.amp}% "
                 f"p:{args.p_start}→{args.p_end}ms dur={args.duration}ms")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")

    ax = axes[1]
    ax.scatter(t, meas, s=8, color="tab:cyan", label="ZC freq Hz (raw)")
    ax.set_ylabel("ZC Hz")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")

    ax = axes[2]
    ax.plot(t, curr, color="tab:orange", label="mean current A")
    ax.set_ylabel("I (A)")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")

    ax = axes[3]
    ax.plot(t, pkpk, color="tab:purple", label="pkpk ADC")
    ax.set_ylabel("pkpk", color="tab:purple")
    ax.tick_params(axis="y", labelcolor="tab:purple")
    ax2 = ax.twinx()
    ax2.plot(t, zcn, color="tab:green", label="ZC count", alpha=0.7)
    ax2.set_ylabel("ZC count", color="tab:green")
    ax2.tick_params(axis="y", labelcolor="tab:green")
    ax.set_xlabel("time (s)")
    ax.grid(alpha=0.3)

    fig.tight_layout()
    png = args.out.with_suffix(".png")
    fig.savefig(png, dpi=110)
    print(f"plot → {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
