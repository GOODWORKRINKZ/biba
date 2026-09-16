#!/usr/bin/env python3
"""Poll an ODrive over ASCII and log the last values before a hang.

Purpose: catch the moment the ODrive dies while driving.  Polls vbus,
errors, state, setpoints and currents at ~15 Hz and prints a rolling table.
When the ODrive stops answering, the loop keeps running and the last good
row remains visible so the failure condition is captured.
"""
import serial
import sys
import time


def flt(b):
    try:
        return float(b.strip())
    except (ValueError, AttributeError):
        return None


def main(port):
    s = serial.Serial(port, 115200, timeout=0.20)
    # Flush any partial line
    s.write(b'\n')
    time.sleep(0.3)
    s.read_all()

    def q(cmd):
        s.write(cmd.encode() + b'\n')
        return flt(s.readline())

    def f(x, w=9, p=3):
        return ("%*.*f" % (w, p, x)) if x is not None else (" " * w)

    hdr = ("t_s | vbus(V) | st0 st1 | axerr0 axerr1 | mterr0 mterr1 | "
           "cmd0 cmd1 (r/s) | vel0 vel1 (r/s) | iq0 iq1 (A) | ibus(A)")
    print(hdr, flush=True)
    t0 = time.time()
    stall = 0
    while True:
        t = time.time() - t0
        vbus = q('r vbus_voltage')
        st0 = q('r axis0.current_state')
        st1 = q('r axis1.current_state')
        ae0 = q('r axis0.error')
        ae1 = q('r axis1.error')
        me0 = q('r axis0.motor.error')
        me1 = q('r axis1.motor.error')
        c0 = q('r axis0.controller.input_vel')
        c1 = q('r axis1.controller.input_vel')
        v0 = q('r axis0.encoder.vel_estimate')
        v1 = q('r axis1.encoder.vel_estimate')
        i0 = q('r axis0.motor.current_control.Iq_measured')
        i1 = q('r axis1.motor.current_control.Iq_measured')
        ib = q('r ibus')

        if vbus is None:
            stall += 1
            print("%5.1f | <no reply #%d> (ODrive unresponsive / hung)"
                  % (t, stall), flush=True)
            if stall >= 5:
                print(">>> ODrive stopped answering after %.1f s. "
                      "Last good row above." % t, flush=True)
                break
        else:
            stall = 0
            print("%5.1f | %s | %s %s | %s %s | %s %s | %s %s | %s %s | "
                  "%s %s | %s" % (
                      t,
                      f(vbus, 7, 2),
                      f(st0, 3, 0), f(st1, 3, 0),
                      f(ae0, 7, 0), f(ae1, 7, 0),
                      f(me0, 7, 0), f(me1, 7, 0),
                      f(c0), f(c1),
                      f(v0), f(v1),
                      f(i0, 6, 2), f(i1, 6, 2),
                      f(ib, 6, 2)),
                  flush=True)
        time.sleep(0.02)


if __name__ == '__main__':
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0'
    main(port)
