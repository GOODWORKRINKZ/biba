#!/usr/bin/env python3
"""Analyse an ODrive velocity step-response CSV (odrive_step_response.py).

For each step in the left-wheel command, computes rise time (10%->90%),
overshoot %, and steady-state error %.  Prints a compact summary.
"""
import csv
import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else
                Path(__file__).resolve().parent / "artifacts" / "odrive-step" / "step.csv")
    rows = list(csv.DictReader(open(path)))
    t = [float(r['t_s']) for r in rows]
    cmd = [float(r['cmdL'] or 0) for r in rows]
    vel = [float(r['velL'] or 0) for r in rows]

    # Find steps: |d(cmd)/dt| crossing a threshold (command jumps)
    steps = []
    for i in range(1, len(rows)):
        if abs(cmd[i] - cmd[i - 1]) > 1.5 and abs(cmd[i]) > 1.0:
            # direction of the step
            steps.append((i, cmd[i - 1], cmd[i]))
    if not steps:
        print("no clean steps found (need |cmdL| jumps > 1.5 to |cmdL|>1.0)")
        return 1

    print("step  from->to   rise10-90   overshoot%   ss_err%")
    shown = 0
    for idx, frm, to in steps:
        if shown >= 6:
            break
        # work on the segment until the next big command change
        end = idx + 1
        while end < len(rows) and abs(cmd[end] - cmd[idx]) < 1.0:
            end += 1
        seg_t = t[idx:end]
        seg_v = vel[idx:end]
        if len(seg_v) < 5:
            continue
        v0 = seg_v[0]
        vf = to  # target velocity
        # rise time: 10% -> 90% of (vf - v0)
        lo, hi = v0 + 0.1 * (vf - v0), v0 + 0.9 * (vf - v0)
        t_lo = t_hi = None
        for ti, vi in zip(seg_t, seg_v):
            if t_lo is None and (vi - v0) * (vf - v0) >= 0.1 * abs(vf - v0):
                t_lo = ti
            if (vi - v0) * (vf - v0) >= 0.9 * abs(vf - v0):
                t_hi = ti
                break
        rise = (t_hi - t_lo) if (t_lo is not None and t_hi is not None) else float('nan')
        # overshoot relative to final command
        vmax = max(seg_v, key=lambda v: v * (1 if vf - v0 > 0 else -1))
        over = (vmax - vf) / abs(vf) * 100 if vf != 0 else 0
        # steady-state error: mean of last 20% of segment
        n = max(3, len(seg_v) // 5)
        vss = sum(seg_v[-n:]) / n
        ss = (vss - vf) / abs(vf) * 100 if vf != 0 else 0
        print("%4d  %5.1f->%5.1f   %7.3f s   %8.1f   %7.1f" %
              (idx, frm, to, rise, over, ss))
        shown += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
