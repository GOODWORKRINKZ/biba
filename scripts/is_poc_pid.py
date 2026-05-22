#!/usr/bin/env python3
"""IS-signal PoC — closed-loop PI controller test driver.

Talks to the rpico_rp2040_is_poc firmware over USB CDC.  Sends a
RPMRUN command with the requested target frequency (Hz) and duration,
streams the per-iteration CSV telemetry to disk, prints it live, and
plots target / measured / duty / current vs time at the end.

Usage:
    python3 is_poc_pid.py --port /dev/ttyACM0 --target 15 --duration 10
    python3 is_poc_pid.py --port /dev/ttyACM0 --target 15 --duration 10 \\
            --kp 0.05 --ki 1.0

Manual disturbance test (the whole point):
    1. Run with --target 15 --duration 15
    2. After a few seconds, grab the wheel by hand and resist rotation.
    3. Observe in the live stream:
       - meas_hz dips (wheel slows)
       - duty_pct climbs (controller pushes harder)
       - curr_a rises (more current drawn to fight you)
    4. Release the wheel — meas_hz should recover to target.
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
    parser.add_argument("--target", type=float, required=True,
                        help="Target IS frequency in Hz (5..20 typical).")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="Run duration in seconds (max 60).")
    parser.add_argument("--kp", type=float, default=0.001,
                        help="Proportional gain (duty per Hz of error). "
                             "Open-loop gain measured at ~950 Hz/duty, so "
                             "Kp=0.001 means ~1 % duty per Hz error.")
    parser.add_argument("--ki", type=float, default=0.002,
                        help="Integral gain.  Loop dt is 0.2 s.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "is-pid"
        / "rpmrun.csv",
    )
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    duration_ms = int(args.duration * 1000)
    kp_mil = int(round(args.kp * 1000))
    ki_mil = int(round(args.ki * 1000))

    print(f"opening {args.port} @ {args.baud}")
    with serial.Serial(args.port, args.baud, timeout=2.0) as ser:
        time.sleep(2.0)                  # USB CDC reset settling
        ser.reset_input_buffer()
        ser.write(b"PING\n")
        time.sleep(0.2)
        resp = ser.read_all().decode(errors="replace")
        if "PONG" not in resp:
            print(f"no PONG — got: {resp!r}", file=sys.stderr)
            return 1

        cmd = f"RPMRUN {args.target:.2f} {duration_ms} {kp_mil} {ki_mil}\n"
        print(f">>> {cmd.strip()}")
        ser.write(cmd.encode())

        rows: list[dict[str, float]] = []
        header_written = False
        with open(args.out, "w", newline="") as fh:
            writer = csv.writer(fh)
            t_deadline = time.time() + args.duration + 5.0
            while time.time() < t_deadline:
                line_b = ser.readline()
                if not line_b:
                    continue
                line = line_b.decode(errors="replace").strip()
                if not line:
                    continue
                print(line)
                if line.startswith("RPM_DATA"):
                    body = line[len("RPM_DATA"):].strip()
                    if body.startswith("t_ms"):
                        # header row
                        cols = [c.strip() for c in body.split(",")]
                        writer.writerow(cols)
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
                            "t_ms": float(parts[0]),
                            "target": float(parts[1]),
                            "meas": float(parts[2]),
                            "duty": float(parts[3]),
                            "curr_a": float(parts[4]),
                            "err": float(parts[5]),
                            "i_term": float(parts[6]),
                            "p_term": float(parts[7]),
                        })
                    except ValueError:
                        pass
                elif line.startswith("RPMRUN_END") or line.startswith("RPMRUN_ABORT"):
                    break

        # Safety: explicit STOP in case the firmware is wedged.
        ser.write(b"STOP\n")
        time.sleep(0.2)

    print(f"\nwrote {args.out}  ({len(rows)} samples)")

    if rows and not args.no_plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("matplotlib not available, skipping plot")
            return 0
        t = [r["t_ms"] / 1000.0 for r in rows]
        target = [r["target"] for r in rows]
        meas = [r["meas"] for r in rows]
        duty = [r["duty"] for r in rows]
        curr = [r["curr_a"] for r in rows]
        err = [r["err"] for r in rows]
        p_term = [r["p_term"] * 100.0 for r in rows]
        i_term = [r["i_term"] * 100.0 for r in rows]

        fig, (ax_f, ax_d, ax_pi, ax_i) = plt.subplots(
            4, 1, figsize=(11, 10), sharex=True,
        )
        ax_f.plot(t, target, "--", color="tab:gray", label="target")
        ax_f.plot(t, meas, color="tab:blue", label="measured (ZC)")
        ax_f.plot(t, err, color="tab:purple", alpha=0.5, label="error")
        ax_f.axhline(0, color="k", lw=0.4)
        ax_f.set_ylabel("Frequency (Hz)")
        ax_f.legend(loc="upper right")
        ax_f.grid(True, alpha=0.3)

        ax_d.plot(t, duty, color="tab:orange", label="duty")
        ax_d.set_ylabel("Duty (%)")
        ax_d.set_ylim(-5, 105)
        ax_d.grid(True, alpha=0.3)

        ax_pi.plot(t, p_term, color="tab:green", label="P term (% duty)")
        ax_pi.plot(t, i_term, color="tab:red", label="I term (% duty)")
        ax_pi.axhline(0, color="k", lw=0.4)
        ax_pi.set_ylabel("PI contribution (% duty)")
        ax_pi.legend(loc="upper right")
        ax_pi.grid(True, alpha=0.3)

        ax_i.plot(t, curr, color="tab:red")
        ax_i.set_ylabel("Current (A)\n(IS DC)")
        ax_i.set_xlabel("Time (s)")
        ax_i.grid(True, alpha=0.3)

        fig.suptitle(
            f"Closed-loop IS-PoC  target={args.target} Hz  "
            f"Kp={args.kp}  Ki={args.ki}",
        )
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        png = args.out.with_suffix(".png")
        fig.savefig(png, dpi=130)
        print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
