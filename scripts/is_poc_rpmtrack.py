#!/usr/bin/env python3
"""IS-signal PoC — closed-loop tracking test with time-varying setpoint.

Sends RPMTRACK command: PI+FF controller with sinusoidal or trapezoidal
setpoint profile with linear period chirp.

Usage:
    python3 scripts/is_poc_rpmtrack.py --port /dev/ttyACM0 \\
            --shape SIN --base 350 --amp 200 --p-start 4000 --p-end 1500 --duration 30
    python3 scripts/is_poc_rpmtrack.py --port /dev/ttyACM0 \\
            --shape TRAP --base 300 --amp 150 --p-start 5000 --p-end 1500 --duration 25
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
    parser.add_argument("--base", type=float, default=350.0,
                        help="Centre of setpoint oscillation (Hz).")
    parser.add_argument("--amp", type=float, default=200.0,
                        help="Amplitude of setpoint oscillation (Hz). "
                             "target = base ± amp. Clamped to [0, 2000].")
    parser.add_argument("--p-start", type=int, default=4000,
                        help="Initial setpoint modulation period (ms).")
    parser.add_argument("--p-end", type=int, default=1500,
                        help="Final setpoint modulation period (ms, linear chirp).")
    parser.add_argument("--duration", type=float, default=25.0,
                        help="Total test duration (s, max 60).")
    parser.add_argument("--kp", type=float, default=0.002)
    parser.add_argument("--ki", type=float, default=0.010)
    parser.add_argument("--stiction", type=int, default=20,
                        help="Stiction floor duty %% (0-50).")
    parser.add_argument("--ff-slope", type=float, default=10.13)
    parser.add_argument("--ff-dead", type=float, default=74.6)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--tag", default="")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    if args.out is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        suffix = f"_{args.tag}" if args.tag else ""
        name = (f"rpmtrack_{args.shape}_base{int(args.base)}_amp{int(args.amp)}"
                f"_p{args.p_start}-{args.p_end}_d{int(args.duration*1000)}"
                f"_{stamp}{suffix}.csv")
        args.out = (Path(__file__).resolve().parent
                    / "artifacts" / "is-rpmtrack" / name)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    duration_ms = int(args.duration * 1000)
    kp_mil = int(round(args.kp * 1_000_000))
    ki_mil = int(round(args.ki * 1_000_000))
    ff_slope_x100 = int(round(args.ff_slope * 100))
    ff_dead_x10   = int(round(args.ff_dead * 10))

    print(f"opening {args.port} @ {args.baud}")
    with serial.Serial(args.port, args.baud, timeout=2.0) as ser:
        time.sleep(2.0)
        ser.reset_input_buffer()
        ser.write(b"PING\n")
        time.sleep(0.2)
        resp = ser.read_all().decode(errors="replace")
        if "PONG" not in resp:
            print(f"no PONG: {resp!r}", file=sys.stderr)
            return 1

        cmd = (f"RPMTRACK {args.shape} {args.base:.1f} {args.amp:.1f} "
               f"{args.p_start} {args.p_end} {duration_ms} "
               f"{kp_mil} {ki_mil} {args.stiction} "
               f"{ff_slope_x100} {ff_dead_x10}\n")
        print(f">>> {cmd.strip()}")
        ser.write(cmd.encode())

        rows: list[dict] = []
        header_written = False
        t_deadline = time.time() + args.duration + 10.0
        with open(args.out, "w", newline="") as fh:
            writer = csv.writer(fh)
            while time.time() < t_deadline:
                line_b = ser.readline()
                if not line_b:
                    continue
                line = line_b.decode(errors="replace").strip()
                if not line:
                    continue
                print(line)
                if line.startswith("RPMTRACK_START"):
                    continue
                if line.startswith("RPM_DATA"):
                    body = line[len("RPM_DATA"):].strip()
                    if body.startswith("t_ms"):
                        writer.writerow([c.strip() for c in body.split(",")])
                        header_written = True
                        continue
                    if not header_written:
                        continue
                    parts = [p.strip() for p in body.split(",")]
                    if len(parts) != 8:
                        continue
                    writer.writerow(parts)
                    try:
                        rows.append({
                            "t_ms":   float(parts[0]),
                            "target": float(parts[1]),
                            "meas":   float(parts[2]),
                            "duty":   float(parts[3]),
                            "curr_a": float(parts[4]),
                            "err":    float(parts[5]),
                            "i_term": float(parts[6]),
                            "p_term": float(parts[7]),
                            "raw_hz": None,
                        })
                    except ValueError:
                        pass
                elif line.startswith("# raw_hz="):
                    if rows:
                        try:
                            rows[-1]["raw_hz"] = float(line.split("=", 1)[1])
                        except ValueError:
                            pass
                elif line.startswith("RPMTRACK_END") or line.startswith("RPMTRACK_ABORT"):
                    break

        ser.write(b"STOP\n")
        time.sleep(0.2)

    print(f"\nwrote {len(rows)} samples → {args.out}")

    if args.no_plot or not rows:
        return 0

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available")
        return 0

    t = [r["t_ms"] / 1000.0 for r in rows]
    target = [r["target"] for r in rows]
    meas = [r["meas"] for r in rows]
    raw_t  = [r["t_ms"] / 1000.0 for r in rows if r.get("raw_hz") is not None]
    raw_hz = [r["raw_hz"] for r in rows if r.get("raw_hz") is not None]
    duty = [r["duty"] for r in rows]
    curr = [r["curr_a"] for r in rows]
    err  = [r["err"] for r in rows]
    p_term = [r["p_term"] * 100.0 for r in rows]
    i_term = [r["i_term"] * 100.0 for r in rows]

    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
    title = (f"RPMTRACK {args.shape}  base={args.base:.0f} ±{args.amp:.0f} Hz  "
             f"period {args.p_start}→{args.p_end} ms  dur={args.duration:.0f}s")

    ax = axes[0]
    ax.plot(t, target, "--", color="tab:gray", lw=1.5, label="setpoint")
    ax.plot(t, meas, color="tab:blue", lw=1.5, label="meas EMA (signed)")
    if raw_hz:
        ax.scatter(raw_t, raw_hz, s=6, color="tab:cyan", alpha=0.4,
                   label="raw ZC (mag)", zorder=3)
    ax.axhline(0, color="k", lw=0.5)
    ax.set_ylabel("freq (Hz)")
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(t, err, color="tab:purple", label="error Hz")
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_ylabel("error (Hz)")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)

    ax = axes[2]
    ax.plot(t, duty, color="tab:orange", label="duty %")
    ax.set_ylabel("duty %")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)

    ax = axes[3]
    ax.plot(t, curr, color="tab:red", label="current A")
    ax2 = ax.twinx()
    ax2.plot(t, p_term, color="tab:green", alpha=0.6, label="P %")
    ax2.plot(t, i_term, color="tab:brown", alpha=0.6, label="I %")
    ax2.set_ylabel("P/I contribution %")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("I (A)")
    ax.grid(alpha=0.3)
    lines1, lbl1 = ax.get_legend_handles_labels()
    lines2, lbl2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, lbl1 + lbl2, loc="upper right", fontsize=8)

    fig.tight_layout()
    png = args.out.with_suffix(".png")
    fig.savefig(png, dpi=110)
    print(f"plot → {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
