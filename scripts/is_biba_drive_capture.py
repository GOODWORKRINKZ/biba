#!/usr/bin/env python3
"""
is_biba_drive_capture.py — BiBa standalone firmware drive diagnostic capture.

Connects to the RP2040 debug mode, arms the robot (wheels must be in the air!),
runs a command sequence, captures DRIVE_DATA telemetry to CSV, and optionally
plots all channels.

DRIVE_DATA format (firmware):
  t_ms, thr, str, mix_L, mix_R, tgt_L_hz, tgt_R_hz,
        meas_L_hz, meas_R_hz, duty_L, duty_R, int_L, int_R, freqdet_L_hz, freqdet_R_hz,
        spec_L_hz, spec_R_hz, spec_q_L, spec_q_R, spec_peak_L, spec_peak_R

Usage examples:
  # Built-in profile: hold throttle=30%, sweep steering 0→50→-50→0
  python3 is_biba_drive_capture.py --port /dev/ttyACM0 --profile steer-step

  # Custom: fixed throttle 40%, steer ramp 0→80% over 15s, then back
  python3 is_biba_drive_capture.py --port /dev/ttyACM0 --profile steer-ramp --thr 40 --duration 20

  # Pivot test: zero throttle, steer sweep -100 → +100
  python3 is_biba_drive_capture.py --port /dev/ttyACM0 --profile pivot

  # CSV script file: rows of  t_s,thr_pct,str_pct
  python3 is_biba_drive_capture.py --port /dev/ttyACM0 --script seq.csv

Built-in profiles:
  steer-step   thr=<--thr>, steer 0→50→-50→0  (5s each step)
  steer-ramp   thr=<--thr>, steer ramps 0→100→-100→0 over <duration>s
  pivot        thr=0, steer 0→100→0→-100→0 (3s each)
  straight     thr=<--thr>, steer=0 for <duration>s
  thr-sine     throttle oscillates as sine: center=<--thr>, amp=<--thr>*0.5, period=<--period>s
  fullsine     bidirectional: center=0, amp=<--thr> (default 100), range -thr..+thr, period=<--period>s

Safety: the script sends DISARM+DBGOFF on KeyboardInterrupt or any error.
"""

import argparse
import csv
import math
import sys
import time
import os
from pathlib import Path
from datetime import datetime

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed — run: pip install pyserial")

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# ---------------------------------------------------------------------------
COLUMNS = [
    "t_ms", "thr", "str",
    "mix_L", "mix_R",
    "tgt_L_hz", "tgt_R_hz",
    "meas_L_hz", "meas_R_hz",
    "duty_L", "duty_R",
    "int_L", "int_R",
    "freqdet_L_hz", "freqdet_R_hz",
    "spec_L_hz", "spec_R_hz",
    "spec_q_L", "spec_q_R",
    "spec_peak_L", "spec_peak_R",
    "spec_cand_L", "spec_cand_R",
    "spec_reason_L", "spec_reason_R",
    "zc_blocks_L", "zc_blocks_R",
    "zc_cross_L", "zc_cross_R",
    "zc_pkpk_L", "zc_pkpk_R",
    "zc_std_L", "zc_std_R",
]


# ---------------------------------------------------------------------------
# Built-in command profiles  (list of (t_s, thr_pct, str_pct))
# ---------------------------------------------------------------------------
def profile_steer_step(thr: int, duration: float):
    """Hold throttle, step steering: 0→50→-50→0."""
    step = max(1.0, duration / 4.0)
    return [
        (0.0,        thr,  0),
        (step,       thr,  50),
        (step * 2,   thr, -50),
        (step * 3,   thr,  0),
        (step * 4,   thr,  0),   # end
    ]


def profile_steer_ramp(thr: int, duration: float):
    """Hold throttle, steer ramps 0→100→-100→0."""
    q = duration / 4.0
    points = []
    for i in range(40):
        frac = i / 39.0
        t = frac * duration
        if frac < 0.25:
            s = int(frac / 0.25 * 100)
        elif frac < 0.5:
            s = int((1 - (frac - 0.25) / 0.25) * 100)
        elif frac < 0.75:
            s = -int((frac - 0.5) / 0.25 * 100)
        else:
            s = -int((1 - (frac - 0.75) / 0.25) * 100)
        points.append((t, thr, s))
    points.append((duration, thr, 0))
    return points


def profile_pivot(duration: float):
    """Zero throttle, steer sweep 0→100→0→-100→0."""
    step = max(1.0, duration / 4.0)
    return [
        (0.0,        0,   0),
        (step,       0, 100),
        (step * 2,   0,   0),
        (step * 3,   0, -100),
        (step * 4,   0,   0),
    ]


def profile_straight(thr: int, duration: float):
    return [(0.0, thr, 0), (duration, thr, 0)]


def profile_thr_sine(thr: int, duration: float, period: float = 4.0):
    """Throttle sine wave — tests PI tracking. center=thr, amp=thr//2, period=period."""
    amp = max(5, thr // 2)
    center = thr
    step = 0.1          # waypoint every 100 ms (firmware outputs ~10 Hz)
    points = []
    t = 0.0
    while t <= duration + 1e-9:
        thr_now = int(round(center + amp * math.sin(2.0 * math.pi * t / period)))
        thr_now = max(0, min(100, thr_now))
        points.append((round(t, 3), thr_now, 0))
        t += step
    return points


def profile_fullsine(thr: int, duration: float, period: float = 4.0):
    """Full bidirectional sine: center=0, amp=thr (default 100). Range: -thr..+thr.
    Tests PI tracking through zero crossing (FWD→REV→FWD)."""
    amp = max(5, thr)
    step = 0.1
    points = []
    t = 0.0
    while t <= duration + 1e-9:
        thr_now = int(round(amp * math.sin(2.0 * math.pi * t / period)))
        thr_now = max(-100, min(100, thr_now))
        points.append((round(t, 3), thr_now, 0))
        t += step
    return points


_g_period: float = 4.0   # overwritten in main() before build_sequence

PROFILES = {
    "steer-step":  lambda thr, dur: profile_steer_step(thr, dur),
    "steer-ramp":  lambda thr, dur: profile_steer_ramp(thr, dur),
    "pivot":       lambda thr, dur: profile_pivot(dur),
    "straight":    lambda thr, dur: profile_straight(thr, dur),
    "thr-sine":    lambda thr, dur: profile_thr_sine(thr, dur, _g_period),
    "fullsine":    lambda thr, dur: profile_fullsine(thr, dur, _g_period),
}


# ---------------------------------------------------------------------------
def build_sequence(profile_name: str, script_path: str | None,
                   thr: int, duration: float):
    if script_path:
        seq = []
        with open(script_path) as f:
            for row in csv.reader(f):
                if not row or row[0].startswith("#"):
                    continue
                seq.append((float(row[0]), int(row[1]), int(row[2])))
        return seq
    fn = PROFILES.get(profile_name)
    if fn is None:
        sys.exit(f"Unknown profile '{profile_name}'. "
                 f"Valid: {', '.join(PROFILES)}")
    return fn(thr, duration)


# ---------------------------------------------------------------------------
class BiBaDebug:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 5.0):
        self.ser = serial.Serial(port, baud, timeout=0.05)
        time.sleep(0.5)          # let USB CDC enumerate
        self.ser.reset_input_buffer()

    def send(self, cmd: str):
        self.ser.write((cmd + "\n").encode())

    def drain(self, timeout_s: float = 0.5) -> list[str]:
        """Read all available lines for up to timeout_s seconds."""
        lines = []
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if line:
                lines.append(line)
        return lines

    def wait_for(self, keyword: str, timeout_s: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            if line:
                print(f"  fw> {line}")
                if keyword in line:
                    return True
        return False

    def enable_debug(self):
        # Reset any leftover state from a previously killed session, then re-enable.
        self.send("DBGOFF")
        time.sleep(0.15)
        self.ser.reset_input_buffer()
        self.send("DBGON")
        if not self.wait_for("DBG mode ON"):
            sys.exit("Firmware did not acknowledge DBGON. "
                     "Is the standalone firmware flashed?")

    def arm(self):
        self.send("ARM")
        if not self.wait_for("DBG armed"):
            sys.exit("Firmware did not acknowledge ARM.")

    def disarm(self):
        self.send("DISARM")
        self.drain(0.3)

    def disable_debug(self):
        self.send("DBGOFF")
        self.drain(0.3)

    def set_inputs(self, thr_pct: int, str_pct: int):
        self.send(f"SET T={thr_pct} S={str_pct}")

    def set_open_loop(self, enabled: bool):
        self.send("OLON" if enabled else "OLOFF")
        keyword = "open-loop ON" if enabled else "open-loop OFF"
        if not self.wait_for(keyword, timeout_s=2.0):
            sys.exit(f"Firmware did not acknowledge {keyword}.")

    def close(self):
        self.ser.close()


# ---------------------------------------------------------------------------
def run_sequence(dbg: BiBaDebug, sequence: list, out_csv: str):
    """Execute the command sequence, capture DRIVE_DATA to CSV."""
    rows = []
    t_seq_start = time.monotonic()

    # Build iterator over (from_time, to_time, thr, str)
    cmds = []
    for i, (t_s, thr, steer) in enumerate(sequence):
        t_end = sequence[i + 1][0] if i + 1 < len(sequence) else t_s + 0.5
        cmds.append((t_s, t_end, thr, steer))

    cmd_idx = 0
    total_duration = sequence[-1][0]

    print(f"\nRunning {len(cmds)} command(s), total {total_duration:.1f} s …")
    print("Press Ctrl-C to abort early.")

    while True:
        elapsed = time.monotonic() - t_seq_start
        if elapsed >= total_duration:
            break

        # Advance to current command
        while cmd_idx + 1 < len(cmds) and elapsed >= cmds[cmd_idx + 1][0]:
            cmd_idx += 1

        _, _, thr, steer = cmds[cmd_idx]
        dbg.set_inputs(thr, steer)

        # Read available DRIVE_DATA lines (~10 Hz from firmware)
        deadline = time.monotonic() + 0.12
        while time.monotonic() < deadline:
            raw = dbg.ser.readline().decode(errors="replace").strip()
            if raw.startswith("DRIVE_DATA "):
                parts = raw[len("DRIVE_DATA "):].split(",")
                if len(parts) in (13, 15, 23, 29, len(COLUMNS)):
                    try:
                        row = [float(p) for p in parts]
                        if len(row) == 13:
                            row.extend([row[7], row[8]])
                        if len(row) == 15:
                            row.extend([0.0] * (len(COLUMNS) - len(row)))
                        if len(row) == 23:
                            row[15:15] = [0.0] * 10
                        if len(row) == 29:
                            row[21:21] = [0.0] * 4
                        # Inject commanded values for easy correlation
                        rows.append(row)
                        print(f"\r  t={row[0]/1000:.1f}s  "
                              f"thr={thr:+d}%  str={steer:+d}%  "
                              f"tgt_L={row[5]:.0f}Hz tgt_R={row[6]:.0f}Hz | "
                              f"meas_L={row[7]:.0f}Hz meas_R={row[8]:.0f}Hz | "
                              f"freqdet_L={row[13]:.0f}Hz freqdet_R={row[14]:.0f}Hz | "
                              f"spec_L={row[15]:.0f}Hz spec_R={row[16]:.0f}Hz | "
                              f"cand_L={row[21]:.0f}Hz cand_R={row[22]:.0f}Hz | "
                              f"reason_L={row[23]:.0f} reason_R={row[24]:.0f} | "
                              f"zc_cross_L={row[27]:.0f} zc_cross_R={row[28]:.0f} | "
                              f"duty_L={row[9]*100:.0f}% duty_R={row[10]*100:.0f}% | "
                              f"int_L={row[11]:.2f} int_R={row[12]:.2f}",
                              end="", flush=True)
                    except ValueError:
                        pass
            elif raw:
                print(f"\n  fw> {raw}")

    print()  # newline after \r progress

    # Write CSV
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    print(f"Saved {len(rows)} rows → {out_csv}")
    return rows


# ---------------------------------------------------------------------------
def plot_data(rows: list, out_csv: str, skip_s: float = 0.0):
    if not HAS_MATPLOTLIB:
        print("matplotlib not installed — skipping plot.")
        return
    import numpy as np
    data = np.array(rows)
    t = data[:, 0] / 1000.0   # ms → s
    if skip_s > 0.0:
        mask = t >= (t[0] + skip_s)
        data = data[mask]
        t = t[mask]

    fig, axes = plt.subplots(5, 1, figsize=(12, 14), sharex=True)
    fig.suptitle(f"BiBa Drive Capture — {Path(out_csv).name}")

    # Row 0 — inputs
    ax = axes[0]
    ax.plot(t, data[:, 1] * 100, label="throttle %")
    ax.plot(t, data[:, 2] * 100, label="steering %")
    ax.set_ylabel("Input %"); ax.legend(); ax.grid(True)

    # Row 1 — LEFT RPM
    ax = axes[1]
    ax.set_title("LEFT motor", loc="left", fontsize=9, pad=2)
    ax.plot(t, data[:, 3] * 100, ":", alpha=0.4, label="mix_L %")
    ax.plot(t, data[:, 5],        label="tgt_L Hz")
    ax.plot(t, data[:, 7], "--",  linewidth=2.0, label="meas_L interpreted Hz")
    if data.shape[1] > 13:
        ax.plot(t, data[:, 13], ":", alpha=0.35, label="freqdet_L ZC Hz")
    if data.shape[1] > 15:
        ax.plot(t, data[:, 15], "-.", alpha=0.75, label="spec_L Hz")
    ax.set_ylabel("Hz / mix %"); ax.legend(); ax.grid(True)

    # Row 2 — LEFT control effort
    ax = axes[2]
    l1, = ax.plot(t, data[:, 9]  * 100, "C0", label="duty_L %")
    ax.set_ylabel("Duty %"); ax.set_ylim(-110, 110); ax.grid(True)
    ax2 = ax.twinx()
    l2, = ax2.plot(t, data[:, 11], "C1:", label="int_L")
    ax2.set_ylabel("Integrator")
    ax.legend(handles=[l1, l2], loc="upper left")

    # Row 3 — RIGHT RPM
    ax = axes[3]
    ax.set_title("RIGHT motor", loc="left", fontsize=9, pad=2)
    ax.plot(t, data[:, 4] * 100, ":", alpha=0.4, label="mix_R %")
    ax.plot(t, data[:, 6],        label="tgt_R Hz")
    ax.plot(t, data[:, 8], "--",  linewidth=2.0, label="meas_R interpreted Hz")
    if data.shape[1] > 14:
        ax.plot(t, data[:, 14], ":", alpha=0.35, label="freqdet_R ZC Hz")
    if data.shape[1] > 16:
        ax.plot(t, data[:, 16], "-.", alpha=0.75, label="spec_R Hz")
    ax.set_ylabel("Hz / mix %"); ax.legend(); ax.grid(True)

    # Row 4 — RIGHT control effort
    ax = axes[4]
    l1, = ax.plot(t, data[:, 10] * 100, "C0", label="duty_R %")
    ax.set_ylabel("Duty %"); ax.set_ylim(-110, 110); ax.grid(True)
    ax2 = ax.twinx()
    l2, = ax2.plot(t, data[:, 12], "C1:", label="int_R")
    ax2.set_ylabel("Integrator")
    ax.legend(handles=[l1, l2], loc="upper left")
    ax.set_xlabel("Time (s)")

    plt.tight_layout()
    png = out_csv.replace(".csv", ".png")
    plt.savefig(png, dpi=120)
    print(f"Plot saved → {png}")
    plt.show()


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--profile", default="steer-step",
                        choices=list(PROFILES),
                        help="Built-in command profile (default: steer-step)")
    parser.add_argument("--script", help="CSV script file: rows of t_s,thr_pct,str_pct")
    parser.add_argument("--thr", type=int, default=30,
                        help="Base throttle %% for profiles (default: 30)")
    parser.add_argument("--period", type=float, default=4.0,
                        help="Sine period in seconds for thr-sine profile (default: 4.0)")
    parser.add_argument("--duration", type=float, default=20.0,
                        help="Total run duration in seconds (default: 20)")
    parser.add_argument("--no-plot", action="store_true",
                        help="Skip matplotlib plot after capture")
    parser.add_argument("--open-loop", action="store_true",
                        help="Debug mode only: bypass RPM PI and drive mixer duty directly")
    parser.add_argument("--plot-skip", type=float, default=2.0,
                        help="Skip first N seconds in the plot to hide arm transient (default: 2.0)")
    parser.add_argument("--out", help="Output CSV path (default: auto-generated)")
    args = parser.parse_args()

    global _g_period
    _g_period = args.period

    sequence = build_sequence(args.profile, args.script, args.thr, args.duration)
    print(f"Profile '{args.profile}': {len(sequence)} waypoints, "
          f"{sequence[-1][0]:.1f}s, base thr={args.thr}%"
          + (f", period={args.period}s" if args.profile == "thr-sine" else ""))

    # Output path
    out_dir = Path(__file__).parent / "artifacts" / "drive-capture"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = args.out or str(out_dir / f"drive_{args.profile}_{ts}.csv")

    print(f"\nConnecting to {args.port} …")
    dbg = BiBaDebug(args.port, args.baud)

    rows = []
    try:
        print("Enabling debug mode …")
        dbg.enable_debug()

        print("Arming (wheels must be in the air!) …")
        dbg.arm()
        if args.open_loop:
            print("Enabling debug open-loop passthrough …")
            dbg.set_open_loop(True)
        time.sleep(0.3)

        rows = run_sequence(dbg, sequence, out_csv)

    except KeyboardInterrupt:
        print("\nAborted by user.")
    finally:
        print("Disarming + disabling debug mode …")
        dbg.set_inputs(0, 0)
        time.sleep(0.1)
        if args.open_loop:
            dbg.set_open_loop(False)
        dbg.disarm()
        dbg.disable_debug()
        dbg.close()

    if rows and not args.no_plot:
        plot_data(rows, out_csv, skip_s=args.plot_skip)


if __name__ == "__main__":
    main()
