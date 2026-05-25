#!/usr/bin/env python3
"""Compare candidate algorithms for IS-pin RPM detection across direction.

Reads two sweepraw CSVs (left, right) captured under ±100% sine, computes per-window
metrics, and checks which metric reliably distinguishes:
  - LEFT motor in FWD vs REV (left should be silent in REV)
  - RIGHT motor in FWD vs REV (right rotates both directions)
"""
import csv
import sys
import math
from pathlib import Path
from collections import defaultdict

import numpy as np

def load(path):
    """Return dict {win_idx: {duty, samples}}."""
    wins = defaultdict(lambda: {"samples": []})
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            idx = int(row[0]); duty = float(row[2]); val = int(row[4])
            wins[idx]["duty"] = duty
            wins[idx]["samples"].append(val)
    for w in wins.values():
        w["samples"] = np.array(w["samples"], dtype=np.float64)
    return wins

def zc_freq(samples, sps=10000.0, min_pkpk=120):
    """Replicate firmware zc_freq_hz: sub-window pkpk gating then ZC count."""
    n = len(samples)
    sub = 128
    crossings = 0
    valid_subs = 0
    for i in range(0, n - sub, sub):
        s = samples[i:i+sub]
        pkpk = s.max() - s.min()
        if pkpk < min_pkpk:
            continue
        valid_subs += 1
        mid = (s.max() + s.min()) / 2
        sign = s[0] >= mid
        for v in s[1:]:
            new_sign = v >= mid
            if new_sign != sign:
                crossings += 1
                sign = new_sign
    if valid_subs == 0:
        return 0.0
    dur = (valid_subs * sub) / sps
    return crossings / (2 * dur)

def metrics(samples, baseline):
    s = samples - baseline
    return dict(
        n        = len(samples),
        pkpk     = samples.max() - samples.min(),
        std      = float(np.std(samples)),
        mean_off = float(np.mean(samples) - baseline),
        abs_mean = float(np.mean(np.abs(s))),
        zc_hz    = zc_freq(samples),
    )

def bin_by_duty(wins):
    """Bucket windows into duty bands.
       Return list of (duty_lo, duty_hi, [metric_dict, ...])"""
    bands = {
        "REV high  (-100..-70)": (-100, -70),
        "REV mid   (-70..-30)":  (-70, -30),
        "REV low   (-30..-10)":  (-30, -10),
        "ZERO      (-10..+10)":  (-10, 10),
        "FWD low   (+10..+30)":  (10, 30),
        "FWD mid   (+30..+70)":  (30, 70),
        "FWD high  (+70..+100)": (70, 100),
    }
    out = {label: [] for label in bands}
    for w in wins.values():
        d = w["duty"]
        for label, (lo, hi) in bands.items():
            if lo <= d < hi:
                out[label].append(w)
                break
    return out

def summarize(side, wins, baseline):
    print(f"\n{'='*70}\n{side}  (baseline={baseline:.1f})\n{'='*70}")
    print(f"{'band':<26} {'N':>3} {'pkpk':>7} {'std':>7} {'mean_off':>9} {'abs_mean':>9} {'zc_hz':>7}")
    bins = bin_by_duty(wins)
    for label, ws in bins.items():
        if not ws: continue
        ms = [metrics(w["samples"], baseline) for w in ws]
        avg = lambda k: np.mean([m[k] for m in ms])
        print(f"{label:<26} {len(ms):>3} "
              f"{avg('pkpk'):>7.0f} "
              f"{avg('std'):>7.1f} "
              f"{avg('mean_off'):>+9.1f} "
              f"{avg('abs_mean'):>9.1f} "
              f"{avg('zc_hz'):>7.1f}")

# ---- main
left_csv  = sys.argv[1]
right_csv = sys.argv[2]
bl_L = 997.1
bl_R = 2027.2

wins_L = load(left_csv)
wins_R = load(right_csv)

summarize("LEFT  motor (REV should be silent — chip disconnected)", wins_L, bl_L)
summarize("RIGHT motor (both directions)",                          wins_R, bl_R)
