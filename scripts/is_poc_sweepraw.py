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
import math
import sys
import time
from pathlib import Path

import serial


def _parse_single_windows(ser, timeout_s: float) -> tuple[list[dict], float | None]:
    """Read SWEEPRAW_START … SWEEPRAW_END; return (windows, baseline)."""
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
            for tok in line.split():
                if tok.startswith("baseline_adc="):
                    baseline = float(tok.split("=", 1)[1])
            print(line)
            continue
        if line.startswith("SWEEPRAW_WIN"):
            parts = line.split()
            current_meta = {"idx": int(parts[1]), "t_ms": int(parts[2]),
                            "duty": float(parts[3])}
            continue
        if line.startswith("SWEEPRAW_END"):
            print(line)
            break
        if line.startswith("SWEEPRAW_ABORT") or line.startswith("ERROR"):
            print(line, file=sys.stderr)
            break
        if line.startswith("ERR"):
            print(line, file=sys.stderr)
            break
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
    return windows, baseline


def _parse_both_windows(ser, timeout_s: float) -> tuple[list[dict], list[dict], float | None, float | None]:
    """Read SWEEPRAW2_START … SWEEPRAW2_END; return (left_wins, right_wins, bl_l, bl_r)."""
    wins_l: list[dict] = []
    wins_r: list[dict] = []
    current_meta = None
    current_chan: str | None = None
    bl_l = bl_r = None
    deadline = time.time() + timeout_s
    in_dump = False
    while time.time() < deadline:
        line_b = ser.readline()
        if not line_b:
            continue
        line = line_b.decode(errors="replace").strip()
        if not line:
            continue
        if line.startswith("SWEEPRAW2_START"):
            in_dump = True
            for tok in line.split():
                if tok.startswith("bl_L="):
                    bl_l = float(tok.split("=", 1)[1])
                elif tok.startswith("bl_R="):
                    bl_r = float(tok.split("=", 1)[1])
                elif tok.startswith("vbat="):
                    _vbat_raw = int(tok.split("=", 1)[1])
                elif tok.startswith("ibat="):
                    _ibat_raw = int(tok.split("=", 1)[1])
            print(line)
            continue
        if line.startswith("SWEEPRAW2_WIN"):
            # SWEEPRAW2_WIN <idx> <t_ms> <duty_pct> <L|R> [vbat ibat]
            parts = line.split()
            current_chan = parts[4] if len(parts) >= 5 else "L"
            current_meta = {"idx": int(parts[1]), "t_ms": int(parts[2]),
                            "duty": float(parts[3])}
            # vbat/ibat from START line (one pair per capture) or from WIN line (per-window, new format)
            if current_chan == "L" and len(parts) >= 7:
                current_meta["vbat_raw"] = int(parts[5])
                current_meta["ibat_raw"] = int(parts[6])
            else:
                current_meta["vbat_raw"] = _vbat_raw if _vbat_raw is not None else float("nan")
                current_meta["ibat_raw"] = _ibat_raw if _ibat_raw is not None else float("nan")
            continue
        if line.startswith("SWEEPRAW2_END"):
            print(line)
            break
        if line.startswith("SWEEPRAW2_ABORT") or line.startswith("ERROR"):
            print(line, file=sys.stderr)
            break
        if in_dump and current_meta is not None and "," in line:
            try:
                vals = [int(v) for v in line.split(",")]
            except ValueError:
                continue
            current_meta["samples"] = vals
            if current_chan == "L":
                wins_l.append(current_meta)
            else:
                wins_r.append(current_meta)
            if current_meta["idx"] % 5 == 0:
                print(f"  win {current_meta['idx']:2d}  chan={current_chan}  "
                      f"t={current_meta['t_ms']:5d}ms  duty={current_meta['duty']:+6.1f}%")
            current_meta = None
    return wins_l, wins_r, bl_l, bl_r


def _write_csv(path: Path, windows: list[dict]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["win_idx", "t_ms", "duty_pct", "sample_idx", "adc_raw", "vbat_raw", "ibat_raw"])
        for win in windows:
            for i, v in enumerate(win["samples"]):
                w.writerow([win["idx"], win["t_ms"], f"{win['duty']:.2f}", i, v,
                            win.get("vbat_raw", float("nan")),
                            win.get("ibat_raw", float("nan"))])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--shape", choices=["SIN", "TRAP"], default="TRAP")
    ap.add_argument("--amp", type=int, default=35)
    ap.add_argument("--period", type=int, default=4000)
    ap.add_argument("--n-windows", type=int, default=None,
                    help="Number of windows (overrides --duration if both given).")
    ap.add_argument("--duration", type=float, default=None,
                    help="Capture duration in seconds. Computes n_windows automatically "
                         "(each window = 1024 samples @ 10 kSPS = ~0.1024 s).")
    ap.add_argument("--motor", choices=["left", "right", "both"], default="left",
                    help="Motor(s) to drive: left, right, or both simultaneously.")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-analyze", action="store_true")
    args = ap.parse_args()

    # Resolve n_windows from --duration if not explicitly set
    _WINDOW_DURATION_S = 1024 / 10000  # 0.1024 s per window at 10 kSPS
    if args.n_windows is None and args.duration is not None:
        args.n_windows = max(1, int(math.ceil(args.duration / _WINDOW_DURATION_S)))
    elif args.n_windows is None:
        args.n_windows = 25  # default

    stamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"_{args.tag}" if args.tag else ""
    base_name = (f"sweepraw_{args.shape}_amp{args.amp}"
                 f"_per{args.period}_n{args.n_windows}_{stamp}{suffix}")

    out_dir = (Path(__file__).resolve().parent / "artifacts" / "is-sweepraw")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.out is not None:
        # treat as explicit output path (single-motor) or stem (both)
        if args.motor == "both":
            out_l = args.out.parent / (args.out.stem + "_left.csv")
            out_r = args.out.parent / (args.out.stem + "_right.csv")
        else:
            out_l = args.out
            out_r = args.out
    else:
        if args.motor == "both":
            out_l = out_dir / (base_name + "_left.csv")
            out_r = out_dir / (base_name + "_right.csv")
        else:
            out_l = out_dir / (base_name + f"_{args.motor}.csv")
            out_r = out_l

    # Streaming mode: data arrives window-by-window during capture.
    # Each window ≈ 0.1024 s capture + ~0.05 s USB transfer; add 60 s slack.
    timeout_s = args.n_windows * 0.2 + 60.0

    print(f"opening {args.port} @ {args.baud}  motor={args.motor}")
    with serial.Serial(args.port, args.baud, timeout=5.0) as ser:
        time.sleep(2.0)
        ser.reset_input_buffer()
        ser.write(b"PING\n")
        time.sleep(0.2)
        resp = ser.read_all().decode(errors="replace")
        if "PONG" not in resp:
            print(f"no PONG: {resp!r}", file=sys.stderr)
            return 1

        # Re-arm in case a prior STOP disarmed the bridge.
        ser.write(b"ARM\n")
        ser.readline()

        if args.motor == "both":
            fw_cmd = (f"SWEEPRAW_BOTH {args.shape} {args.amp} "
                      f"{args.period} {args.n_windows}\n")
        elif args.motor == "right":
            fw_cmd = (f"SWEEPRAW_R {args.shape} {args.amp} "
                      f"{args.period} {args.n_windows}\n")
        else:
            fw_cmd = (f"SWEEPRAW {args.shape} {args.amp} "
                      f"{args.period} {args.n_windows}\n")
        print(f">>> {fw_cmd.strip()}")
        ser.write(fw_cmd.encode())

        if args.motor == "both":
            wins_l, wins_r, bl_l, bl_r = _parse_both_windows(ser, timeout_s)
        else:
            wins_l, baseline = _parse_single_windows(ser, timeout_s)
            wins_r = []

    # --- write CSVs ---
    if args.motor == "both":
        if not wins_l and not wins_r:
            print("no windows captured", file=sys.stderr)
            return 3
        if wins_l:
            _write_csv(out_l, wins_l)
            print(f"wrote {len(wins_l)} LEFT  windows → {out_l}  bl_L={bl_l:.1f}")
        if wins_r:
            _write_csv(out_r, wins_r)
            print(f"wrote {len(wins_r)} RIGHT windows → {out_r}  bl_R={bl_r:.1f}")
    else:
        if not wins_l:
            print("no windows captured", file=sys.stderr)
            return 3
        _write_csv(out_l, wins_l)
        n_samp = len(wins_l[0]["samples"]) if wins_l else 0
        print(f"wrote {len(wins_l)} windows × {n_samp} samples → {out_l}")
        if baseline is not None:
            print(f"baseline_adc={baseline:.1f}")

    if args.no_analyze:
        return 0

    # --- run offline algorithm bench on each saved file ---
    import subprocess
    bench = Path(__file__).resolve().parent / "is_sweepraw_analyze.py"
    if not bench.exists():
        print(f"analyzer missing: {bench}", file=sys.stderr)
        return 0
    rc = 0
    for csv_path in ([out_l, out_r] if args.motor == "both" else [out_l]):
        if csv_path.exists():
            print(f"\n--- analyzing {csv_path.name} ---")
            rc |= subprocess.call([sys.executable, str(bench), str(csv_path)])
    return rc


if __name__ == "__main__":
    sys.exit(main())
