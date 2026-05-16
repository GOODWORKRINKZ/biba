---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-05-16T17:02:55.604Z"
progress:
  total_phases: 3
  completed_phases: 1
  total_plans: 8
  completed_plans: 6
  percent: 75
---

# Project State

**Project:** BiBa
**Milestone:** RP2040 Port
**Phase:** 1
**Status:** Executing Phase 03
**Last updated:** 2026-05-14

## Current Phase

Phase 1: Core Drive

## Completed Phases

(none)

## Notes

RP2040 port at ~50% — ELRS/CRSF + motor control base exists in `rp2040-port` branch. Needs IMU, current sense, trim port.
ESC thermal fix in progress (hardware): BTS7960 крепление на металлическую пластину для теплоотвода.
Field test conducted 2026-05-09 — primary issue confirmed as ESC thermal mode.

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
