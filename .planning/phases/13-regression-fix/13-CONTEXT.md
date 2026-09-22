# Phase 13: Regression Fix — Load Gate / PI Windup

**Date:** 2026-05-27
**Status:** Discussed — ready for planning

## Phase Boundary

After Phase 11 (IS-Pin Load & Stall Detection), the RPM closed-loop regulator
exhibited severe regression: wheels jerk constantly, sometimes spin in the
opposite direction, PI integral saturates at both limits (+3.0 ↔ -1.0).
Offline spectral analysis looks correct — the bug is in the **real-time
interaction** between the new load gate and the PI controller.

Phase 13 diagnoses and fixes this regression, then validates the fix with
blackbox captures and field testing.

## Root Cause Analysis

### Mechanism

```
Operator releases throttle (100% → 0%)
        ↓
Motor decelerates → generator/back-EMF effect → IS-pin current SPIKES
        ↓
Load gate fires: ratio > 1.5 & quality < 10.0 → INVALID (HIGH_LOAD)
        ↓
DR holds LAST valid RPM (~900 Hz!) — motor was at full speed
        ↓
PI sees: target=0, meas=900 → error = -900 Hz
        ↓
Integral winds NEGATIVE to saturation (-1.0) → NEGATIVE duty
        ↓
Motor REVERSES → even more IS current → gate keeps firing
        ↓
When gate eventually clears → PI overshoots due to saturated integral
        ↓
Overshoot triggers gate again → PERMANENT OSCILLATION
```

### Why Phase 11 Made It Worse

| | Before Phase 11 | After Phase 11 |
|---|---|---|
| Invalid reasons | Signal quality only (PEAK_LOW, QUALITY_LOW) | **+ DC current level (HIGH_LOAD)** |
| Max consecutive invalid | 1–2 windows (isolated) | **18+ windows (sustained)** |
| Invalid cause | Transient signal issue | **Persistent DC level (deceleration = seconds!)** |
| DR stale-hold duration | ~200 ms → PI recovers fast | **~2 seconds → PI winds to saturation** |
| PI integral range | Normal operating range | **+3.0 ↔ -1.0 (both limits)** |

**Key insight:** Before Phase 11, spectral results were invalidated only by
signal-quality issues (PEAK_LOW, QUALITY_LOW, NO_BAND). These are transient —
they affect 1–2 windows, DR holds briefly, PI recovers. After Phase 11, the
load gate adds a **DC-current-based** invalidation that persists for the
**entire deceleration period** (seconds). DR holds the last valid RPM for far
too long, PI winds up to saturation, and the system enters permanent oscillation.

Anti-stall ramp (also Phase 11) compounds the problem: it ADDS duty on top of
PI during HIGH_LOAD, making the overshoot even worse.

### Evidence

**Blackbox session_0012** (`artifacts/blackbox/session_0012.csv`):
- 72 duty oscillation events (>15% change in 40 ms)
- Duty swings: `100%→60%`, `60%→100%`, `0%→-37%` — all at **zero throttle**
- PI integral: `+3.000` ↔ `-1.000` (saturation limits)
- 0 latch resets — not a BTS7960 thermal issue

**Simulation models** (`scripts/artifacts/phase13_*.png`):
- `phase13_before_after.png` — 18× increase in consecutive invalid windows
- `phase13_root_cause_model.png` — full oscillation cycle reproduced
- `phase13_regression_analysis.png` — blackbox data + PI model

## Canonical Refs

- `firmware/src/modes/mode_standalone.c` — DMA ISR `on_adc_pair_done()`, tick function
- `firmware/src/app/rpm_spectral_estimator.c` — `biba_rpm_spectral_apply_load_gate()`
- `firmware/include/biba_config.h` — `BIBA_RPM_LOAD_*` constants
- `artifacts/blackbox/session_0012.csv` — regression evidence
- `scripts/artifacts/phase13_before_after.png` — before/after comparison model
- `scripts/artifacts/phase13_root_cause_model.png` — oscillation loop model
- `.planning/phases/11-is-pin-load-stall-detection/11-CONTEXT.md` — Phase 11 design decisions

## Locked Decisions

### D-1: Root cause is confirmed

**D-1.1:** The regression is caused by the load gate (`BIBA_FEATURE_RPM_LOAD_GATE`)
creating **sustained** (multi-second) invalid spectral windows during
deceleration, which the PI+DR chain cannot tolerate.

**D-1.2:** The anti-stall ramp (`BIBA_FEATURE_RPM_ANTI_STALL`) amplifies the
problem by adding duty on top of an already-saturated PI.

**D-1.3:** This is NOT a BTS7960 thermal latch issue (0 latch resets in
session_0012). Not an ADC capture regression. Not a CRSF/PWM driver regression.

### D-2: Fix approach — three-tier defence

**D-2.1 (Immediate — safety gate):** Add a **deceleration bypass** to the load
gate. If commanded duty magnitude is below a threshold AND the previous RPM was
above a minimum, the motor is coasting/decelerating, not stalling. In this
state, bypass the load gate (force `valid = true`).

```
IF |duty| < DECEL_DUTY_THRESH AND prev_rpm_hz > DECEL_RPM_MIN:
    → bypass load gate (motor is coasting, not stalling)
```

**D-2.2 (Robustness):** Raise `BIBA_RPM_LOAD_QUALITY_MAX` from `10.0` to `15.0`.
The current threshold of 10.0 was chosen from a 3-window test (win3, win18,
win14 in softhold dataset). In continuous driving, quality drops below 10
during normal transients (acceleration, deceleration), causing false positives.
15.0 provides headroom.

**D-2.3 (Defence in depth):** Add **PI integral reset on gate edge**. When the
load gate transitions from not-fired to fired, reset the PI integral for that
channel. This prevents the integral from winding up during sustained invalid
periods. Trade-off: brief loss of integral memory on true stall events, but
stall recovery is handled by anti-stall ramp anyway.

### D-3: Validation

**D-3.1:** After fix, blackbox captures must show:
- 0 duty oscillation events at zero throttle
- PI integral staying within normal range (not saturating)
- No negative duty at zero throttle

**D-3.2:** Field test: drive → release → verify smooth deceleration without
jerking or reverse rotation.

**D-3.3:** All 88 existing tests must continue to pass.

### D-4: What NOT to do

**D-4.1:** Do NOT remove the load gate entirely — it correctly catches true
stall events (win3, win18 in softhold). The gate logic is correct for its
intended purpose; the issue is its interaction with the PI during deceleration.

**D-4.2:** Do NOT reduce PI integral limit (3.0 → 1.0) as the primary fix. The
current limit is needed for sustained hill-climbing torque. Reducing it masks
the symptom but doesn't fix the root cause.

**D-4.3:** Do NOT switch to absolute-threshold-only gate. The ratio gate
provides valuable cross-channel context.

## Deferred Ideas

- **IS-pin current characterisation during deceleration:** Oscilloscope capture
  of IS-pin voltage during throttle release → calibrate `DECEL_DUTY_THRESH` and
  `DECEL_RPM_MIN` from real measurements. Defer to a follow-up hardware phase.
- **Goertzel execution time profiling:** GPIO-toggle measurement of
  `on_adc_pair_done` duration. The ~200 ms estimate should be verified on real
  hardware. Not blocking — the ISR latency was unchanged from Phase 10.
- **PI dt mismatch:** `BIBA_RPM_PI_DT_S = 0.104s` but effective ISR period is
  variable (200+ ms with Goertzel, ~51 ms without). Consider adaptive dt based
  on actual ISR interval. Defer to tuning phase.

## Next Steps

1. `/gsd-plan-phase 13` — create implementation plan from these decisions
2. Implement D-2.1, D-2.2, D-2.3 in firmware
3. Blackbox validation capture
4. Field smoke test
