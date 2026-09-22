#!/usr/bin/env python3
"""ODrive velocity-PI step test (for interactive tuning over USB CDC).

Generates a velocity step on one axis, samples the velocity estimate and
Iq, and reports rise time / overshoot / steady-state error so vel_gain and
vel_integrator_gain can be tuned without the Pico.

Usage:
    python3 scripts/odrive_pid_step.py /dev/ttyACM0 --axis 0 \
        --gain 0.02 --integ 0.0 --vel 2.0
"""
import argparse
import sys
import time

import serial


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("port")
    p.add_argument("--axis", type=int, default=0, choices=(0, 1))
    p.add_argument("--gain", type=float, default=None, help="set vel_gain")
    p.add_argument("--integ", type=float, default=None,
                   help="set vel_integrator_gain")
    p.add_argument("--vel", type=float, default=2.0, help="step target rev/s")
    p.add_argument("--hold", type=float, default=1.5, help="hold time at step")
    p.add_argument("--settle", type=float, default=0.4,
                   help="settle time at zero after step")
    args = p.parse_args()

    ax = f"axis{args.axis}"
    ser = serial.Serial(args.port, 115200, timeout=0.2)
    time.sleep(0.2)
    ser.read_all()

    def w(cmd):
        ser.write(cmd.encode() + b"\n")
        time.sleep(0.008)

    def r(cmd):
        ser.write(cmd.encode() + b"\n")
        time.sleep(0.004)
        line = ser.readline().strip()
        try:
            return float(line)
        except (ValueError, AttributeError):
            return None

    # Apply gains if requested.
    if args.gain is not None:
        w(f"w {ax}.controller.config.vel_gain {args.gain}")
    if args.integ is not None:
        w(f"w {ax}.controller.config.vel_integrator_gain {args.integ}")

    vg = r(f"r {ax}.controller.config.vel_gain")
    vi = r(f"r {ax}.controller.config.vel_integrator_gain")
    print(f"[{ax}] vel_gain={vg} vel_integrator_gain={vi}", flush=True)

    # Arm.
    w(f"w {ax}.requested_state 8")
    time.sleep(0.6)
    st = r(f"r {ax}.current_state")
    print(f"[{ax}] current_state={st}", flush=True)
    if st != 8:
        print("!! failed to enter CLOSED_LOOP_CONTROL (8)", flush=True)
        w(f"w {ax}.requested_state 1")
        return 1

    # Zero setpoint, settle.
    w(f"w {ax}.controller.input_vel 0")
    time.sleep(0.5)

    target = args.vel
    rec = []   # (t_s, vel, iq)
    t0 = time.time()

    def sample():
        v = r(f"r {ax}.encoder.vel_estimate")
        i = r(f"r {ax}.motor.current_control.Iq_measured")
        rec.append((time.time() - t0, v, i))

    # Pre-step baseline (0.2 s).
    while time.time() - t0 < 0.2:
        sample()
        time.sleep(0.025)

    # Step on.
    w(f"w {ax}.controller.input_vel {target}")
    while time.time() - t0 < 0.2 + args.hold:
        sample()
        time.sleep(0.025)

    # Step off.
    w(f"w {ax}.controller.input_vel 0")
    while time.time() - t0 < 0.2 + args.hold + args.settle:
        sample()
        time.sleep(0.025)

    # Disarm.
    w(f"w {ax}.requested_state 1")
    time.sleep(0.3)

    # ---- Analysis -------------------------------------------------------
    ts = [x[0] for x in rec]
    vs = [x[1] for x in rec if x[1] is not None]
    vs_all = [x[1] if x[1] is not None else 0.0 for x in rec]
    iqs = [x[2] for x in rec if x[2] is not None]

    # Split at the step-on instant (0.2 s mark).
    pre = [v for (t, v) in zip(ts, vs_all) if t < 0.2]
    post = [(t, v) for (t, v) in zip(ts, vs_all) if t >= 0.2]

    base = sum(pre) / len(pre) if pre else 0.0
    peak = max(v for _, v in post)
    overshoot = (peak - target) / target * 100.0 if target else 0.0

    # Rise time 10% -> 90% of target.
    lo, hi = 0.1 * target, 0.9 * target
    t_lo = t_hi = None
    for t, v in post:
        if t_lo is None and v >= lo:
            t_lo = t - 0.2
        if t_hi is None and v >= hi:
            t_hi = t - 0.2
    rise = (t_hi - t_lo) if (t_lo is not None and t_hi is not None) else None

    # Steady state = mean over last 0.4 s of the hold.
    tail = [(t, v) for (t, v) in post if t >= 0.2 + args.hold - 0.4]
    ss = sum(v for _, v in tail) / len(tail) if tail else None
    sse = (target - ss) if ss is not None else None

    print("-" * 48, flush=True)
    print(f"target       : {target:+.3f} rev/s", flush=True)
    print(f"baseline     : {base:+.3f} rev/s", flush=True)
    print(f"peak         : {peak:+.3f} rev/s", flush=True)
    print(f"overshoot    : {overshoot:+.1f} %", flush=True)
    print(f"rise 10-90%%  : {rise*1000 if rise is not None else float('nan'):.0f} ms", flush=True)
    print(f"steady-state : {ss if ss is not None else float('nan'):+.3f} rev/s", flush=True)
    print(f"SS error     : {sse if sse is not None else float('nan'):+.3f} rev/s", flush=True)
    if iqs:
        print(f"Iq peak      : {max(iqs):.2f} A", flush=True)
    print("-" * 48, flush=True)

    ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
