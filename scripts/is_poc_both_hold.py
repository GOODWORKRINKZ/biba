#!/usr/bin/env python3
"""IS-signal PoC dual-wheel closed-loop capture driver.

Runs the RP2040 PoC firmware command RPMRUN_BOTH, streams live telemetry
to CSV, optionally plots the run, and marks a manual hand-hold interval so
dropouts can be reproduced consistently and saved under scripts/artifacts.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import serial


def build_default_out(script_dir: Path,
                      left_target: float,
                      right_target: float,
                      hold_side: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    side_tag = f"_{hold_side}hold" if hold_side != "none" else ""
    name = (
        f"rpmrun_both_L{int(round(left_target))}"
        f"_R{int(round(right_target))}{side_tag}_{stamp}.csv"
    )
    return script_dir / "artifacts" / "is-pid" / name


def parse_start_targets(line: str) -> tuple[float | None, float | None]:
    tgt_l = None
    tgt_r = None
    for token in line.split():
        if token.startswith("tgt_L="):
            try:
                tgt_l = float(token.split("=", 1)[1])
            except ValueError:
                tgt_l = None
        elif token.startswith("tgt_R="):
            try:
                tgt_r = float(token.split("=", 1)[1])
            except ValueError:
                tgt_r = None
    return tgt_l, tgt_r


def summarize_hold_window(rows: list[dict[str, float]],
                          hold_after: float,
                          hold_for: float) -> None:
    if not rows or hold_for <= 0.0:
        return

    window = [
        row for row in rows
        if hold_after <= row["t_s"] <= (hold_after + hold_for)
    ]
    if not window:
        print("no samples inside hold window")
        return

    def metric(name: str) -> tuple[float, float, int]:
        values = [row[name] for row in window]
        zeros = sum(1 for value in values if value == 0.0)
        return min(values), max(values), zeros

    raw_l_min, raw_l_max, raw_l_zero = metric("raw_l")
    raw_r_min, raw_r_max, raw_r_zero = metric("raw_r")
    meas_l_min, meas_l_max, _ = metric("meas_l")
    meas_r_min, meas_r_max, _ = metric("meas_r")

    print("\nhold-window summary")
    print(
        f"  raw_L: min={raw_l_min:.1f} max={raw_l_max:.1f} zeros={raw_l_zero}/{len(window)}"
    )
    print(
        f"  raw_R: min={raw_r_min:.1f} max={raw_r_max:.1f} zeros={raw_r_zero}/{len(window)}"
    )
    print(f"  meas_L: min={meas_l_min:.1f} max={meas_l_max:.1f}")
    print(f"  meas_R: min={meas_r_min:.1f} max={meas_r_max:.1f}")


def main() -> int:
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--left-target", type=float, default=282.0)
    parser.add_argument("--right-target", type=float, default=282.0)
    parser.add_argument("--duration", type=float, default=20.0,
                        help="Run duration in seconds (max 60).")
    parser.add_argument("--kp", type=float, default=0.002)
    parser.add_argument("--ki", type=float, default=0.010)
    parser.add_argument("--stiction", type=float, default=20.0,
                        help="Stiction floor duty percent (0-50).")
    parser.add_argument("--ff-slope", type=float, default=10.13)
    parser.add_argument("--ff-dead", type=float, default=74.6)
    parser.add_argument("--hold-side", choices=["left", "right", "none"],
                        default="right")
    parser.add_argument("--hold-after", type=float, default=6.0,
                        help="Seconds after run start to begin manual hold.")
    parser.add_argument("--hold-for", type=float, default=6.0,
                        help="How long to keep holding the wheel.")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    if args.out is None:
        args.out = build_default_out(
            script_dir,
            args.left_target,
            args.right_target,
            args.hold_side,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)

    duration_ms = int(args.duration * 1000.0)
    kp_mil = int(round(args.kp * 1_000_000))
    ki_mil = int(round(args.ki * 1_000_000))
    stiction_x100 = int(round(args.stiction * 100.0))
    ff_slope_x100 = int(round(args.ff_slope * 100.0))
    ff_dead_x10 = int(round(args.ff_dead * 10.0))

    print(f"opening {args.port} @ {args.baud}")
    if args.hold_side != "none":
        hold_end = args.hold_after + args.hold_for
        print(
            f"manual plan: free-spin until {args.hold_after:.1f}s, "
            f"hold {args.hold_side.upper()} until {hold_end:.1f}s, then release"
        )

    with serial.Serial(args.port, args.baud, timeout=2.0) as ser:
        time.sleep(2.0)
        ser.reset_input_buffer()
        ser.write(b"PING\n")
        time.sleep(0.2)
        resp = ser.read_all().decode(errors="replace")
        if "PONG" not in resp:
            print(f"no PONG - got: {resp!r}", file=sys.stderr)
            return 1

        cmd = (
            f"RPMRUN_BOTH {args.left_target:.2f} {args.right_target:.2f} {duration_ms} "
            f"{kp_mil} {ki_mil} {stiction_x100} {ff_slope_x100} {ff_dead_x10}\n"
        )
        print(f">>> {cmd.strip()}")
        ser.write(cmd.encode())

        rows: list[dict[str, float]] = []
        header_written = False
        start_seen = False
        hold_announced = False
        release_announced = False

        with open(args.out, "w", newline="") as fh:
            writer = csv.writer(fh)
            deadline = time.time() + args.duration + 8.0
            while time.time() < deadline:
                line_b = ser.readline()
                if not line_b:
                    continue
                line = line_b.decode(errors="replace").strip()
                if not line:
                    continue
                print(line)

                if line.startswith("RPMRUN2_START"):
                    start_seen = True
                    got_l, got_r = parse_start_targets(line)
                    if got_l is not None and abs(got_l - args.left_target) > 0.5:
                        print(
                            f"firmware echoed tgt_L={got_l} but asked {args.left_target}",
                            file=sys.stderr,
                        )
                    if got_r is not None and abs(got_r - args.right_target) > 0.5:
                        print(
                            f"firmware echoed tgt_R={got_r} but asked {args.right_target}",
                            file=sys.stderr,
                        )
                    continue

                if line.startswith("RPM2_DATA"):
                    body = line[len("RPM2_DATA"):].strip()
                    if body.startswith("t_ms"):
                        cols = [col.strip() for col in body.split(",")]
                        writer.writerow(cols)
                        header_written = True
                        continue
                    if not header_written:
                        continue
                    parts = [part.strip() for part in body.split(",")]
                    if len(parts) != 9:
                        continue
                    writer.writerow(parts)
                    try:
                        row = {
                            "t_ms": float(parts[0]),
                            "t_s": float(parts[0]) / 1000.0,
                            "tgt_l": float(parts[1]),
                            "tgt_r": float(parts[2]),
                            "meas_l": float(parts[3]),
                            "meas_r": float(parts[4]),
                            "duty_l": float(parts[5]),
                            "duty_r": float(parts[6]),
                            "raw_l": float(parts[7]),
                            "raw_r": float(parts[8]),
                        }
                    except ValueError:
                        continue
                    rows.append(row)

                    if args.hold_side != "none":
                        if not hold_announced and row["t_s"] >= args.hold_after:
                            print(f"*** HOLD {args.hold_side.upper()} wheel now ***\a")
                            hold_announced = True
                        if (
                            not release_announced
                            and row["t_s"] >= (args.hold_after + args.hold_for)
                        ):
                            print("*** RELEASE wheel now ***\a")
                            release_announced = True
                    continue

                if line.startswith("RPMRUN2_END") or line.startswith("RPMRUN2_ABORT"):
                    break

        ser.write(b"STOP\n")
        time.sleep(0.2)

    print(f"\nwrote {args.out} ({len(rows)} samples)")
    if not start_seen:
        print("never saw RPMRUN2_START", file=sys.stderr)
    if not rows:
        print("no RPM2_DATA rows collected", file=sys.stderr)
        return 1

    summarize_hold_window(rows, args.hold_after, args.hold_for)

    if not args.no_plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("matplotlib not available, skipping plot")
            return 0

        t = [row["t_s"] for row in rows]
        tgt_l = [row["tgt_l"] for row in rows]
        tgt_r = [row["tgt_r"] for row in rows]
        meas_l = [row["meas_l"] for row in rows]
        meas_r = [row["meas_r"] for row in rows]
        duty_l = [row["duty_l"] for row in rows]
        duty_r = [row["duty_r"] for row in rows]
        raw_l = [row["raw_l"] for row in rows]
        raw_r = [row["raw_r"] for row in rows]

        fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

        axes[0].plot(t, tgt_l, "--", color="tab:blue", alpha=0.6, label="target L")
        axes[0].plot(t, tgt_r, "--", color="tab:red", alpha=0.6, label="target R")
        axes[0].plot(t, meas_l, color="tab:blue", lw=1.5, label="meas L")
        axes[0].plot(t, meas_r, color="tab:red", lw=1.5, label="meas R")
        axes[0].scatter(t, raw_l, s=10, color="tab:cyan", alpha=0.5, label="raw L")
        axes[0].scatter(t, raw_r, s=10, color="tab:orange", alpha=0.5, label="raw R")
        axes[0].set_ylabel("Frequency (Hz)")
        axes[0].grid(True, alpha=0.3)
        axes[0].legend(loc="upper right", ncol=2)

        axes[1].plot(t, duty_l, color="tab:blue", label="duty L")
        axes[1].plot(t, duty_r, color="tab:red", label="duty R")
        axes[1].set_ylabel("Duty (%)")
        axes[1].set_ylim(-5, 105)
        axes[1].grid(True, alpha=0.3)
        axes[1].legend(loc="upper right")

        axes[2].plot(t, raw_l, color="tab:cyan", lw=1.5, label="raw L")
        axes[2].plot(t, raw_r, color="tab:orange", lw=1.5, label="raw R")
        axes[2].axhline(0.0, color="k", lw=0.6)
        axes[2].set_ylabel("Raw ZC (Hz)")
        axes[2].set_xlabel("Time (s)")
        axes[2].grid(True, alpha=0.3)
        axes[2].legend(loc="upper right")

        if args.hold_side != "none" and args.hold_for > 0.0:
            start = args.hold_after
            end = args.hold_after + args.hold_for
            for axis in axes:
                axis.axvspan(start, end, color="tab:gray", alpha=0.12)

        fig.suptitle(
            f"RPMRUN_BOTH L={args.left_target:.1f} Hz R={args.right_target:.1f} Hz"
        )
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        png = args.out.with_suffix(".png")
        fig.savefig(png, dpi=130)
        print(f"wrote {png}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())