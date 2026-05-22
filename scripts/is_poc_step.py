#!/usr/bin/env python3
"""IS-signal PoC — open-loop step response test.

Sends STEPRUN to the firmware: holds duty_start for N pre-windows, then
instantly steps to duty_end and records the ZC frequency response.
Plots the step response with rise time and 63% time-constant annotations.

Usage:
    python3 scripts/is_poc_step.py --port /dev/ttyACM0 --from 20 --to 50
    python3 scripts/is_poc_step.py --port /dev/ttyACM0 --from 0 --to 40 \\
            --pre 5 --post 20
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
    parser.add_argument("--from", dest="duty_start", type=int, default=0,
                        help="Starting duty %% before the step.")
    parser.add_argument("--to", dest="duty_end", type=int, default=40,
                        help="Target duty %% after the step.")
    parser.add_argument("--pre", type=int, default=5,
                        help="Number of 200 ms windows before step (baseline).")
    parser.add_argument("--post", type=int, default=20,
                        help="Number of 200 ms windows after step (response).")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parent
                        / "artifacts" / "is-step" / "step.csv")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    total_windows = args.pre + args.post
    timeout = total_windows * 0.22 + 10.0  # 220 ms per window + margin

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

        cmd = f"STEPRUN {args.duty_start} {args.duty_end} {args.pre} {args.post}\n"
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
                if line.startswith("STEPRUN_START"):
                    continue
                if line.startswith("STEP_DATA"):
                    body = line[len("STEP_DATA"):].strip()
                    if body.startswith("t_ms"):
                        cols = [c.strip() for c in body.split(",")]
                        writer.writerow(cols)
                        header_written = True
                        continue
                    if not header_written:
                        continue
                    parts = [p.strip() for p in body.split(",")]
                    if len(parts) != 5:
                        continue
                    writer.writerow(parts)
                    try:
                        rows.append({
                            "t_ms":    float(parts[0]),
                            "phase":   parts[1],
                            "duty":    float(parts[2]),
                            "meas_hz": float(parts[3]),
                            "curr_a":  float(parts[4]),
                        })
                    except ValueError:
                        pass
                elif line.startswith("STEPRUN_END") or line.startswith("STEPRUN_ABORT"):
                    break
        ser.write(b"STOP\n")
        time.sleep(0.2)

    print(f"\nwrote {args.out}  ({len(rows)} samples)")
    if not rows:
        print("!!! no STEP_DATA received", file=sys.stderr)
        return 1

    if args.no_plot:
        return 0

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib/numpy not available, skipping plot")
        return 0

    t    = np.array([r["t_ms"] / 1000.0 for r in rows])
    duty = np.array([r["duty"]    for r in rows])
    hz   = np.array([r["meas_hz"] for r in rows])
    curr = np.array([r["curr_a"]  for r in rows])

    # Find step time (first POST window)
    step_idx = next((i for i, r in enumerate(rows) if r["phase"] == "POST"), None)
    t_step = t[step_idx] if step_idx is not None else None

    # Steady-state estimates: mean of last 5 PRE and last 5 POST windows
    pre_hz  = float(np.mean(hz[:args.pre][-5:]))
    post_hz = float(np.mean(hz[-5:]))
    delta   = post_hz - pre_hz

    # 10%, 63% (tau), 90% rise markers
    markers = {}
    if delta != 0 and step_idx is not None:
        for pct, label in [(10, "t10"), (63, "tau"), (90, "t90")]:
            thresh = pre_hz + delta * pct / 100.0
            for i in range(step_idx, len(hz)):
                if (delta > 0 and hz[i] >= thresh) or (delta < 0 and hz[i] <= thresh):
                    markers[label] = t[i]
                    break

    fig, (ax_f, ax_d, ax_i) = plt.subplots(3, 1, figsize=(11, 8), sharex=True)

    # --- Frequency panel ---
    ax_f.plot(t, hz, color="tab:blue", lw=1.5, label="meas_hz (ZC)")
    ax_f.axhline(pre_hz,  color="tab:gray",  ls="--", lw=0.8, label=f"pre  {pre_hz:.1f} Hz")
    ax_f.axhline(post_hz, color="tab:green", ls="--", lw=0.8, label=f"post {post_hz:.1f} Hz")
    if t_step is not None:
        ax_f.axvline(t_step, color="k", lw=1.2, label="step")
    colors_m = {"t10": "tab:orange", "tau": "tab:red", "t90": "tab:purple"}
    for label, tv in markers.items():
        ax_f.axvline(tv, color=colors_m[label], ls=":", lw=1,
                     label=f"{label} = {tv - t_step:.2f}s" if t_step else label)
    ax_f.set_ylabel("Frequency (Hz)")
    ax_f.legend(loc="upper right", fontsize=8)
    ax_f.grid(True, alpha=0.3)

    title = (f"Step response  {args.duty_start}% → {args.duty_end}% duty   "
             f"Δfreq={delta:+.1f} Hz")
    if "tau" in markers and t_step:
        title += f"   τ={markers['tau'] - t_step:.2f}s"
    if "t10" in markers and "t90" in markers and t_step:
        title += f"   t_rise(10-90%)={markers['t90'] - markers['t10']:.2f}s"
    ax_f.set_title(title, fontsize=10)

    # --- Duty panel ---
    ax_d.step(t, duty, color="tab:orange", lw=1.5, where="post")
    ax_d.set_ylabel("Duty (%)")
    ax_d.set_ylim(-5, 105)
    ax_d.grid(True, alpha=0.3)
    if t_step is not None:
        ax_d.axvline(t_step, color="k", lw=1.2)

    # --- Current panel ---
    ax_i.plot(t, curr, color="tab:red", lw=1.2)
    ax_i.set_ylabel("Current (A)\n(IS DC)")
    ax_i.set_xlabel("Time (s)")
    ax_i.grid(True, alpha=0.3)
    if t_step is not None:
        ax_i.axvline(t_step, color="k", lw=1.2)

    fig.tight_layout()
    png = args.out.with_suffix(".png")
    fig.savefig(png, dpi=130)
    print(f"wrote {png}")

    # Print summary to console
    print(f"\n--- Step response summary ---")
    print(f"  from:       {args.duty_start}% duty → {pre_hz:.1f} Hz")
    print(f"  to:         {args.duty_end}% duty → {post_hz:.1f} Hz")
    print(f"  Δfreq:      {delta:+.1f} Hz")
    for label, tv in markers.items():
        if t_step:
            print(f"  {label}:        {tv - t_step:.3f} s after step")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
