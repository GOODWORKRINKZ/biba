---
phase: 01-core-drive
plan: 05
subsystem: verification
tags: [build, hardware, smoke-test]
autonomous: false
---

# Phase 1 Plan 05: Build + Hardware Verify — PASSED

**Build:** `pio run -e rpico_rp2040_standalone` → exit 0 ✅  
**Tests:** `pio test -e native_test` → 39/39 PASS ✅ (from Plan 01-03)  
**Flash:** `pio run -e rpico_rp2040_standalone --target upload` → exit 0 ✅  
**Hardware smoke:** Robot drives. Ramp active. SSR fires on arm. ✅

## Hardware Findings (2026-05-14)

### FINDING-01: Backup pip causes motor jerk at high speed — KNOWN ARCH CONSTRAINT

**Observed:** On speed mode 3, reverse pip causes wheel to brake abruptly then resume.  
**Root cause:** BiBa has no dedicated buzzer. Motor PWM pins double as audio output.  
When `s_audio_mode=true`, `biba_hal_bts7960_drive()` is blocked — traction drops to zero for the pip duration.  
**At low speed:** pip ≪ inertia, barely noticeable.  
**At high speed:** jerk is significant and feels like a bug.  
**Status:** BACKLOG — options for next milestone:
- Option A: Suppress pip if `|out| > 0.5` (speed threshold gating)
- Option B: Shorten `biba_melody_backup_pip` to < 80ms
- Option C: Accept (safety semantics — pip physically slows robot on reverse)

### FINDING-02: Trim gesture worked, but 5-second hold is non-obvious

**Gesture:** ALL 4 stick axes (CH1–CH4) above 90% simultaneously, held 5 s, while DISARMED.  
This means: right stick max up+right, left stick max up+right at the same time.  
**Confirmed working** once gesture was performed correctly.  
**Status:** Consider reducing `BIBA_TRIM_CONFIRM_HOLD_MS` from 5000 → 3000 in next phase.

### FINDING-03: Robot does not drive straight — motor mismatch

**Observed:** Robot drifts due to motor/driver characteristic differences.  
**Mitigation:** Trim mode (FINDING-02) is the intended fix — it works.  
**Status:** Working as designed. Document trim gesture in README for operators.

## Phase 1 Completion

All 5 plans executed, hardware verified. Phase 1 is COMPLETE.

| Plan | Title | Status |
|------|-------|--------|
| 01-01 | SpeedRamp C port | ✅ DONE |
| 01-02 | SSR HAL | ✅ DONE |
| 01-03 | TDD tests (8/8 GREEN) | ✅ DONE |
| 01-04 | mode_standalone.c integration | ✅ DONE |
| 01-05 | Build + human verify | ✅ DONE |

## Commits (rp2040-port branch)

```
964fdf1  feat(01-01): add ramp.h, biba_config.h RAMP constants
368c507  feat(01-01): implement biba_ramp_update in ramp.c
391e55d  feat(01-02): add SSR HAL — target.h, biba_hal.h, biba_hal.c, biba_hal_rp2040.c
93a5b99  feat(01-03): add test_ramp suite (8/8), fix native_test build
5fe770e  feat(01-04): wire ramp+SSR into mode_standalone.c
```
