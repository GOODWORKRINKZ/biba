#!/usr/bin/env python3
"""ODrive velocity step-response logger (for PI tuning).

Polls axis0/axis1 velocity command and estimate at ~25-30 Hz over ASCII
and streams a live table + CSV so a throttle step can be analysed
(rise time, overshoot, oscillation, steady-state error).

Usage:
    python3 scripts/odrive_step_response.py /dev/ttyACM0 --duration 20
"""
import argparse
import csv
import sys
import time
from pathlib import Path

import serial


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("port")
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "artifacts"
                   / "odrive-step" / "step.csv")
    args = p.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    ser = serial.Serial(args.port, 115200, timeout=0.15)
    time.sleep(0.2)
    ser.write(b'\n')
    time.sleep(0.3)
    ser.read_all()

    def flt(cmd):
        ser.write(cmd.encode() + b'\n')
        r = ser.readline().strip()
        try:
            return float(r)
        except (ValueError, AttributeError):
            return None

    hdr = ("t_s,cmdL,cmdR,velL,velR,iqL,iqR")
    print(hdr.replace(",", " | "), flush=True)
    t0 = time.time()
    rows = []
    # Cap the poll rate (~25 Hz) so we don't flood the ODrive USB-CDC and
    # starve its 8 kHz control loop (CONTROL_DEADLINE_MISSED observed when
    # polling unthrottled at ~280 Hz).
    TARGET_PERIOD = 1.0 / 25.0
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(hdr.split(","))
        while time.time() - t0 < args.duration:
            row_t0 = time.time()
            t = row_t0 - t0
            cL = flt('r axis0.controller.input_vel')
            cR = flt('r axis1.controller.input_vel')
            vL = flt('r axis0.encoder.vel_estimate')
            vR = flt('r axis1.encoder.vel_estimate')
            iL = flt('r axis0.motor.current_control.Iq_measured')
            iR = flt('r axis1.motor.current_control.Iq_measured')
            row = [t, cL, cR, vL, vR, iL, iR]
            rows.append(row)
            w.writerow(row)
            fh.flush()
            def f(x, wdt=8, pr=3):
                return ("%*.*f" % (wdt, pr, x)) if x is not None else " " * wdt
            print("%6.2f | %s %s | %s %s | %s %s" % (
                t, f(cL), f(cR), f(vL), f(vR), f(iL, 6, 2), f(iR, 6, 2)),
                flush=True)
            elapsed = time.time() - row_t0
            if elapsed < TARGET_PERIOD:
                time.sleep(TARGET_PERIOD - elapsed)
    print("saved ->", args.out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
