---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: idle
last_updated: "2026-05-19T11:00:00.000Z"
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 12
  completed_plans: 12
  percent: 100
---

# Project State

**Project:** BiBa
**Milestone:** RP2040 Port
**Phase:** —
**Status:** All active phases complete. Phase 5 added — ready to plan.
**Last updated:** 2026-05-19

## Current Phase

None — Phase 4 UAT passed 2026-05-19.

## Completed Phases

- Phase 1: Core Drive — complete
- Phase 3: Field Ready — complete
- Phase 4: Thermal Hardening & ESC Architecture — complete (UAT passed 2026-05-19)

## Notes

Phase 4 field validation confirmed: large heatsink installed + one driver replaced → thermal within limits throughout run.
Center of mass shifted closer to geometric center → handling improved significantly.
All 10 UAT acceptance criteria passed. 04-UAT.md status=complete.

Phase 2 (Stabilization & Sensing) has no directory yet — may follow after Phase 5.
Phase 5 (Current Sensing & ADC Architecture) added 2026-05-19 — scope: BTS7960 IS pins, ADS1115 I2C ADC, battery/per-wheel current, temp/hum telemetry.

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
