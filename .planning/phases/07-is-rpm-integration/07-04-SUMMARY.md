# Plan 07-04 Summary — FF+PI RPM controller (rpm_pi.h/c)

**Phase**: 07-is-rpm-integration
**Plan**: 07-04
**Status**: Complete
**Branch**: develop
**Commits**: `c203852`, `66ce2f7`

---

## Objective Delivered

Created the portable FF+PI RPM controller module (`firmware/src/app/rpm_pi.h/c`)
ported from the PoC `cmd_rpmrun` inner loop. Implements gain scheduling,
asymmetric anti-windup, stiction floor, and P-clamp. Covered by 6 Unity tests
that pass under both `pio test -e native_test` and the standalone gcc shim.

This delivers the control law that Plan 07-05 will wire into
`mode_standalone.c`. Module is pure portable C99 with no HAL dependency —
EMA filtering is delegated to `zc_ema_update()` from Plan 07-01's
`zc_detector.h`.

---

## Changes

### Production module (commit `c203852`)
- `firmware/src/app/rpm_pi.h`:
  - `biba_rpm_pi_config_t` — 9 floats: `kp`, `ki`, `ki_low`,
    `ki_low_thresh`, `ff_slope`, `ff_dead`, `stiction_floor`, `p_clamp`,
    `dt_s`.
  - `biba_rpm_pi_state_t` — `integral`, `meas_ema`, `prev_duty`, `primed`.
  - `biba_rpm_pi_reset()` / `biba_rpm_pi_step()` declarations.
  - `BIBA_RPM_PI_*` macros for all default tuning constants (mirror PoC
    `RPMRUN_*` defaults).
- `firmware/src/app/rpm_pi.c`:
  - NULL-pointer guard at entry (T-07-04-03 mitigation).
  - Forward-only clamp `if (target_hz < 0) target_hz = 0` (T-07-04-02).
  - FF guard `ff_slope > 0 && target_hz > 0` (T-07-04-04 NaN avoidance).
  - Gain-schedule branch: `ki = (target < ki_low_thresh) ? ki_low : ki`.
  - Asymmetric integral clamp `[-0.01/ki, +0.03/ki]` (favors forward authority).
  - Anti-windup gate: no integration when saturated against the error sign
    OR when `meas_hz <= 50`.
  - P-term zeroed when `meas_hz == 0`; otherwise clamped to `±p_clamp`.
  - Stiction floor snap when `0 < duty < stiction_floor` and `target > 0`.
  - Final duty clamped to `[0, 1]`.

### Unity tests (commit `66ce2f7`)
- `firmware/test/test_rpm_pi/test_main.c` — 6 tests:
  1. `test_reset_zeroes_state` — all 4 state fields zero after reset.
  2. `test_ff_only_duty` — pure FF for target=400 ≈ 0.4685.
  3. `test_gain_scheduling_below_200` — proves `ki_low` branch taken via
     integral exceeding the would-be regular-ki clamp value.
  4. `test_antiwindup_no_growth_at_saturation` — `prev_duty=1.0` + positive
     error → integral unchanged.
  5. `test_p_clamp_limits_p_term` — huge kp clamped to `±p_clamp = 0.05`.
  6. `test_stiction_floor_applied` — tiny ff_duty snaps up to 0.20.
- Runner follows the `test_zc_detector` pattern with the
  `#if defined(BIBA_TEST_STANDALONE)` / Unity `main()` dual entry.

---

## Verification (all gates green)

| Gate | Result |
|------|--------|
| `pio test -e native_test --filter test_rpm_pi` | 6/6 PASS in 0.55 s |
| Full native regression: `pio test -e native_test` | 53/53 PASS (47 prior + 6 new) |
| `grep ki_low_thresh\|zc_ema_update\|i_clamp_pos` in rpm_pi.c | all 3 present |
| `grep biba_rpm_pi_step\|...` in rpm_pi.h | 4 hits |

## Self-Check: PASSED

- All 4 threat mitigations from `<threat_model>` implemented and verifiable:
  - **T-07-04-01** (NaN propagation): accepted; floats don't throw on RP2040.
  - **T-07-04-02** (negative target): `target_hz < 0 → 0` at entry.
  - **T-07-04-03** (NULL pointers): `s == NULL || cfg == NULL → return 0`.
  - **T-07-04-04** (ff_slope=0 div): guarded by `ff_slope > 0 && target_hz > 0`.
- No HAL includes — module is fully portable, confirmed by native_test gcc
  successfully linking against just `rpm_pi.c` + `zc_detector.c`.
- Test `test_gain_scheduling_below_200` is intentionally designed so the
  expected integral (4.68) lies between the two clamp values (3.0 for ki
  vs 6.0 for ki_low), making the branch selection observable without
  needing to instrument the controller.

## Deviations

None.

## Notes for downstream plans

- Plan 07-05 will instantiate two `biba_rpm_pi_state_t` (left, right) and
  one shared `biba_rpm_pi_config_t` in `mode_standalone.c`, calling
  `biba_rpm_pi_step()` from the DMA-IRQ-driven state machine. The
  resulting `duty` is the input to `biba_hal_motor_pwm_left/right()`.
- The `meas_ema` field of `biba_rpm_pi_state_t` doubles as the source of
  truth for the wheel_rpm telemetry field (Plan 07-02 `wheel_rpm_*_hz`
  in `biba_telemetry_input_t`).
- `prev_duty` is stored in `state` rather than `out` so the controller can
  be called from any context without the caller having to track the
  previous output.
