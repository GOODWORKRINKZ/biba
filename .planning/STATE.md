---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: in-progress
last_updated: "2026-05-27T20:00:00.000Z"
progress:
  total_phases: 13
  completed_phases: 12
  total_plans: 35
  completed_plans: 35
  percent: 92
---

# Project State

**Project:** BiBa
**Milestone:** RP2040 Port
**Phase:** Phase 13 — Regression Fix (Load Gate / PI Windup)
**Status:** DISCUSSED (CONTEXT.md written; root cause confirmed; ready for planning)
**Last updated:** 2026-05-27

## Current Phase

Phase 13 diagnosed: the load gate (`BIBA_FEATURE_RPM_LOAD_GATE`, Phase 11) creates **sustained** invalid spectral windows during deceleration (18+ consecutive, vs 1-2 before Phase 11). DR holds stale RPM → PI integral winds to saturation (+3.0 ↔ -1.0) → permanent duty oscillation → wheels jerk and reverse.

Three-tier fix agreed: (1) deceleration bypass in load gate, (2) raise LOAD_QUALITY_MAX 10→15, (3) PI integral reset on gate edge.

Blackbox session_0012 confirms: 72 duty oscillation events, PI integral at limits, negative duty at zero throttle. Simulation models at `scripts/artifacts/phase13_*.png`.

## Completed Phases

- Phase 1: Core Drive — complete
- Phase 3: Field Ready — complete
- Phase 4: Thermal Hardening & ESC Architecture — complete (UAT passed 2026-05-19)
- Phase 5: Current Sensing & ADC Architecture — complete (2026-05-22)
- Phase 6: IS-Signal RPM Proof-of-Concept — complete (2026-05-23)
- Phase 7: IS-RPM Integration — complete (2026-05-25)
- Phase 8: Blackbox Recorder — complete
- Phase 9: RPM Estimator Hardening — complete
- Phase 10: Goertzel Dual-Window — complete (84/84 tests)
- Phase 11: IS-Pin Load & Stall Detection — complete (88/88 tests)
- Phase 12: Signal Chain Feature Gating — complete (88/88 tests, 3 plans executed)
- Phase 13: Regression Fix — discussed (root cause confirmed, CONTEXT.md written)

## Notes

Phase 12 delivers 17 `BIBA_FEATURE_*` compile-time toggles:
- RPM chain (7): ZC, SPECTRAL, DUAL_WINDOW, LOAD_GATE, DR, PI, ANTI_STALL
- Safety (2): LATCH_RECOVERY, CURRENT_LIMITER
- Comfort (4): STEERING_DEADBAND, RPM_RAMP, MELODY, REVERSE_PIP
- Drive (3): HEADING_HOLD, SPEED_MODE, MIXER_PROJECTION

Master switch `BIBA_FEATURE_RPM_CLOSED_LOOP` replaces `BIBA_OPEN_LOOP` with backward compat.
Dependency `#error` checks: PI→DR, DUAL_WINDOW→SPECTRAL, LOAD_GATE→SPECTRAL, ANTI_STALL→SPECTRAL.
Open-loop mode (RPM_CLOSED_LOOP=0): -40B RAM, -5.8KB Flash vs default.

Physical smoke test pending — requires robot hardware for field validation.

**2026-05-17**: Phase 4 added to roadmap — Thermal Hardening & ESC Architecture. Synthesizing dialogue.log + forum analysis of BTN7970/BTN8982TA/IFX007T tradeoffs and cooling design strategies. Four implementation plans created: failure analysis, ESC evaluation, thermal design, and 60+ min validation test.

## Key Risks

- Boot pin float: BTS7960 EN pins must be driven LOW as first HAL operation (critical safety)
- Failsafe tick must run from hardware alarm ISR, not main loop (I2C blocking hazard documented)
- RP2040 ADC noise under 20 kHz PWM needs characterization before current sense coefficients are set
- PID gains require re-tuning — Pi Python gains tuned against ~50 Hz asyncio loop with jitter

## Decisions Log

| Decision | Rationale |
|----------|-----------|
| earlephilhower arduino-pico, local platform pin | Reproducibility; mbed incompatible |
| No third-party IMU/CRSF libs | Existing crsf.c + imu.c with pico-sdk direct access — stale libs not worth ABI bridging |
| HAL shim pattern (extend, not ifdef) | New files per peripheral, build_src_filter selects; no #ifdef RPICO in shared src/ |
| LittleFS for calibration/trim | Runtime persistence of PID gains + trim + current-sense offsets |
| Failsafe on core1 / hardware alarm ISR | Safety-critical tick must be independent of blocking I2C/ADC main loop |
