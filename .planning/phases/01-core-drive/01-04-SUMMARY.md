---
phase: 01-core-drive
plan: 04
subsystem: motor-control
tags: [integration, ramp, ssr, mode_standalone]
requires: ["01-02", "01-03"]
provides: ["ramp+SSR wired in mode_standalone.c"]
tech-stack:
  added: []
  patterns: [edge-detection, post-mix-ramp]
key-files:
  modified:
    - firmware/src/modes/mode_standalone.c
key-decisions:
  - "Edit D: ramp placed outside if(armed){} block — disarmed output=0 → ramp decelerates to 0 naturally, but resets on arm/disarm edges guarantee hard zero (D-04)"
  - "Edit C: biba_hal_ssr_set immediately after s_armed=armed — one-liner, no separate if-block needed (Pitfall 5)"
  - "Edit A: biba_hal_ssr_set(false) in failsafe block is belt-and-suspenders — Edit C already covers it on the next line, but explicit cut is safer against future refactors (D-10)"
requirements-completed:
  - MOTOR-03
  - SAFE-03
duration: 5 min
completed: 2026-05-14T00:00:00Z
---

# Phase 1 Plan 04: Integration Summary

Wired `biba_ramp_t` state machines and `biba_hal_ssr_set` into `mode_standalone.c`. Four edits applied — the control loop now has slew-rate limiting and SSR arm/disarm logic.

**Duration:** ~5 min | **Tasks:** 2 | **Files modified:** 1

**Next:** Wave 4 Plan 01-05 (Build + human verify checkpoint)

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Include ramp.h, declare s_ramp_left/right, add ramp_init calls in init | `5fe770e` |
| 2 | 4 edits in tick(): failsafe reset, disarm reset, SSR arm, ramp update | `5fe770e` |

## Edits Applied

| Edit | Location | Code Added |
|------|----------|------------|
| includes | after `#include "app/failsafe.h"` | `#include "app/ramp.h"` |
| statics | after `static bool s_last_failsafe;` | `static biba_ramp_t s_ramp_left; static biba_ramp_t s_ramp_right;` |
| init | after `s_last_failsafe = true;` | `biba_ramp_init(&s_ramp_left); biba_ramp_init(&s_ramp_right);` |
| A | inside `if (failsafe && !s_last_failsafe)` | `biba_ramp_reset` ×2 + `biba_hal_ssr_set(false)` |
| B | inside `} else if (!armed && s_armed)` | `biba_ramp_reset` ×2 |
| C | after `s_armed = armed;` | `biba_hal_ssr_set(armed);` |
| D | after trim block, before `control_active` | `left_out = biba_ramp_update(...); right_out = biba_ramp_update(...);` |

## Verified Ordering (line numbers in 5fe770e)

```
L248:  biba_hal_ssr_set(false)   [Edit A, failsafe edge]
L266:  s_armed = armed           [existing]
L267:  biba_hal_ssr_set(armed)   [Edit C]
L409:  left_out = biba_ramp_update(...)   [Edit D]
L410:  right_out = biba_ramp_update(...)  [Edit D]
L414:  bool control_active = ...  [existing]
L467:  biba_bts7960_drive(...)   [existing]
```

## Self-Check: PASSED

- [x] 2x `biba_ramp_update` (exactly)
- [x] 4x `biba_ramp_reset` (exactly — 2 per edge)
- [x] 2x `biba_hal_ssr_set` (exactly — 1 failsafe, 1 after s_armed)
- [x] SSR call after s_armed assignment (L267 > L266)
- [x] ramp_update before control_active (L409 < L414)
- [x] ramp_update before bts7960_drive (L409 < L467)
