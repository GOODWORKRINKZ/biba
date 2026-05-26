---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: in-progress
last_updated: "2026-05-27T00:00:00.000Z"
progress:
  total_phases: 10
  completed_phases: 10
  total_plans: 27
  completed_plans: 27
  percent: 100
---

# Project State

**Project:** BiBa
**Milestone:** RP2040 Port
**Phase:** Phase 10 — Goertzel Dual-Window Search
**Status:** COMPLETE — all 3 waves executed, 84/84 tests pass
**Last updated:** 2026-05-26

## Current Phase

All phases complete. Milestone RP2040 Port — DONE (Phase 9 DR fallback added).

## Completed Phases

- Phase 1: Core Drive — complete
- Phase 3: Field Ready — complete
- Phase 4: Thermal Hardening & ESC Architecture — complete (UAT passed 2026-05-19)
- Phase 5: Current Sensing & ADC Architecture — complete (2026-05-22)
- Phase 6: IS-Signal RPM Proof-of-Concept — complete (2026-05-23)
- Phase 7: IS-RPM Integration — complete (2026-05-25)

## Notes

Phase 4 field validation confirmed: large heatsink installed + one driver replaced → thermal within limits throughout run.
Center of mass shifted closer to geometric center → handling improved significantly.
All 10 UAT acceptance criteria passed. 04-UAT.md status=complete.

Phase 5 (Current Sensing & ADC Architecture) complete 2026-05-22: ADS1115+AHT30 drivers, per-wheel current sense, VBAT/IBAT, temp/hum telemetry, protocol extended, all tests green.

Phase 7 (IS-RPM Integration) complete 2026-05-25: ZC detector + async ADC capture + RPM PI controller wired into mode_standalone.c. Both wheels run closed-loop RPM. wheel_rpm_hz telemetry live. BTS7960 latch auto-recovery via IS signal detector — empirically validated against stall capture data (LATCH_IS_RAW_MIN=3500, cooldown 20 windows). Field tested and confirmed.

Phase 2 (Stabilization & Sensing) remains deferred — no directory yet, may follow after Phase 6.

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
