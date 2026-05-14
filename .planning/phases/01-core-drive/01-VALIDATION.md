---
phase: 01-core-drive
type: validation
---

# Phase 01 — Validation Architecture

## Test Framework

| Property | Value |
|----------|-------|
| Framework | Unity ^2.6.1 via PlatformIO |
| Config file | `firmware/platformio.ini` `[env:native_test]` |
| Quick run (ramp only) | `cd firmware && pio test -e native_test -f test_ramp` |
| Full firmware suite | `cd firmware && pio test -e native_test` |
| Run from project root | `cd firmware && pio test -e native_test` |

## Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CRSF-01 | Interrupt ring buffer receives CRSF bytes | unit | `pio test -e native_test -f test_crsf` | ✅ `firmware/test/test_crsf/test_main.c` |
| CRSF-02 | RC_CHANNELS_PACKED decodes 16 channels correctly | unit | `pio test -e native_test -f test_crsf` | ✅ `firmware/test/test_crsf/test_main.c` |
| CRSF-03 | CRSF ping: CRC-8 DVB-S2 round-trip | unit | `pio test -e native_test -f test_crsf` | ✅ same |
| MOTOR-01 | 20 kHz PWM (hardware — not testable natively) | manual / hardware | Flash + oscilloscope | N/A |
| MOTOR-02 | Differential mixer output values | unit | `pio test -e native_test -f test_control_loop` | ✅ `firmware/test/test_control_loop/test_main.c` |
| MOTOR-03 | Ramp accel, decel, direction-change, zero-hold, reset | unit | `pio test -e native_test -f test_ramp` | ❌ Wave 0 — create `firmware/test/test_ramp/test_main.c` |
| SAFE-01 | `biba_failsafe_tick()` triggers at 500 ms; primed state | unit | `pio test -e native_test -f test_control_loop` | ✅ existing (failsafe tested in test_control_loop) |
| SAFE-03 | Arm threshold, deadband; EN pins LOW before first RC frame | manual / hardware | Bench test | N/A |

## Wave 0 Gaps

- [ ] `firmware/test/test_ramp/test_main.c` — covers MOTOR-03 (8 test cases, see below)

**Required test cases for `test_ramp/test_main.c`** (mirror `tests/test_ramping.py`):
1. `test_accel_from_zero` — target=1.0, dt=0.02 → result ≈ 0.04 (2.0 × 0.02)
2. `test_decel_toward_lower_target` — start at 1.0, target=0.5, dt=0.02 → result ≈ 0.96 (1.0 − 2.0×0.02)
3. `test_direction_change_decels_toward_zero_first` — at 1.0, target=−1.0, dt=0.02 → result ≈ 0.99 (1.0 − 0.5×0.02); still > 0
4. `test_direction_change_sets_hold_at_zero` — large decel rate to hit 0, then immediately: result = 0.0 (hold active)
5. `test_zero_hold_releases_after_ms` — hold timer counts down; after hold_remaining_s ≤ 0, starts accel in new direction
6. `test_reset_sets_current_zero` — `biba_ramp_reset()` → `r.current == 0.0f`, `r.hold_remaining_s == 0.0f`
7. `test_dt_zero_returns_current` — dt=0.0f → return unchanged current, no state mutation
8. `test_output_clamped_to_unit` — large target, large dt → output ≤ 1.0f

## Sampling Rate

- Per task commit: `cd firmware && pio test -e native_test -f test_ramp`
- Per wave merge: `cd firmware && pio test -e native_test`
- Phase gate: full suite green before `/gsd-verify-work`
