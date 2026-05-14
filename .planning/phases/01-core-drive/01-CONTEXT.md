# Phase 1: Core Drive - Context

**Gathered:** 2025-07-14
**Status:** Ready for planning

<domain>
## Phase Boundary

RP2040 receives CRSF from ELRS receiver and drives both BTS7960 channels (left + right motor)
with reliable failsafe. Includes arming logic, output ramping, and SSR-based power relay control.

Out of scope: IMU/heading-hold (Phase 2), current-sense calibration (Phase 2), thermal protection (Phase 3).

</domain>

<decisions>
## Implementation Decisions

### Carrying Forward (already decided, not re-discussed)
- **D-00a:** Toolchain — earlephilhower arduino-pico (pico-sdk access, good library support)
- **D-00b:** No third-party CRSF/IMU libs — port existing `firmware/src/drivers/crsf.c` with pico-sdk primitives
- **D-00c:** HAL shim pattern — new files per peripheral (`biba_hal_motor_rp2040.c`, etc.), `build_src_filter` selects target; no `#ifdef RPICO` in shared `src/`
- **D-00d:** LittleFS for calibration/trim persistence (Phase 2+)
- **D-00e:** Failsafe on hardware alarm ISR deferred to Phase 2 when I2C is added (see D-04 below)

### Output Ramping (MOTOR-03)
- **D-01:** Port full Python `SpeedRamp` algorithm to C (`firmware/src/app/ramp.c` / `ramp.h`).
  Algorithm: separate accel/decel rates, zero-hold before direction reversal, per-motor state.
- **D-02:** Defaults match `biba-controller/config.py` exactly:
  `BIBA_RAMP_ACCEL_RATE = 2.0f` u/s, `BIBA_RAMP_DECEL_RATE = 2.0f` u/s,
  `BIBA_RAMP_REVERSE_DECEL_RATE = 0.5f` u/s, `BIBA_RAMP_ZERO_HOLD_MS = 150u`.
  All values live in `biba_config.h` with `#ifndef` guards for per-target override.
- **D-03:** Ramp applied **post-mix** to `left_out` / `right_out` in `mode_standalone_tick()`,
  same placement as Python `mix_and_ramp()`.
- **D-04:** On disarm or failsafe edge: **hard reset** ramp state to zero (`ramp_reset()` → `_current = 0`).
  No gradual decel — matches Python "emergency stop" path.
- **D-05:** Ramp always runs. **No bypass** when current limiter is clamping.

### Failsafe Architecture (SAFE-01, SAFE-02)
- **D-06:** Phase 1 failsafe: **poll-based** in `mode_standalone_tick()`. Existing `biba_failsafe_tick()`
  called each main loop iteration. Acceptable because Phase 1 has no blocking I2C.
- **D-07:** Hardware alarm ISR upgrade deferred to Phase 2 when I2C (BMI160/LSM6DS3) is added.
  At that point: pico-sdk `hardware_alarm` on core0, alarm reset on each good CRSF frame,
  ISR calls `biba_hal_motor_pwm_stop()` directly on timeout.
- **D-08:** Failsafe timeout: `BIBA_CRSF_TIMEOUT_MS = 500` (already in `biba_config.h`). No change.

### SSR (Solid-State Relay) — BTS7960 Power Control
- **D-09:** Add `BIBA_PIN_SSR_GPIO = GP16` to `firmware/targets/RPICO_RP2040/target.h`.
  GP16 is the first free pin after the SBC SPI interface (GP10-GP14).
- **D-10:** SSR follows arm state: `armed=true` → SSR HIGH (power ON to BTS7960),
  `armed=false` OR failsafe active → SSR LOW (power cut). This enables remote thermal reset:
  disarm via RC → BTS7960 loses power → driver cools from thermal protection → arm → power restored.
- **D-11:** EN pins (L_REN, L_LEN, R_REN, R_LEN) stay **HIGH** at all times after boot.
  The SSR handles full power disconnection; EN pins provide no additional benefit on disarm.
  PWM duty = 0 when disarmed (existing behavior, no change needed).
- **D-12:** **No delay** between SSR ON and PWM enable. SSR relay switches < 1 ms. User chose
  instant enable on arm.
- **D-13:** SSR HAL: add `biba_hal_ssr_set(bool enabled)` to `biba_hal.h` + `biba_hal_rp2040.c`.
  Add `biba_hal_ssr_init()` call in `biba_hal_init()` — drives GP16 LOW at boot (safe default).

### CRSF Startup & Failsafe Priming
- **D-14:** Failsafe stays **default-active** until the first valid RC_CHANNELS frame is received.
  `biba_failsafe_init()` sets `primed = false`; first `biba_failsafe_mark_fresh()` primes it.
  No boot-delay, no frame-count threshold. Existing behavior — no change needed.
- **D-15:** CRSF device ping interval: **200 ms (5 Hz)**, always running (even after priming).
  ELRS EP01 requires pings to begin outputting RC frames; continuous pings also serve as heartbeat.

### Agent's Discretion
- Internal ramp data structure field naming in C (e.g., `current_output` vs `current`) — follow
  the Python `SpeedRamp` naming where possible for readability.
- SSR state update placement in `mode_standalone_tick()` — update SSR immediately after the
  `armed` bool is computed, before the motor drive section.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Python reference implementation
- `biba-controller/motors/ramping.py` — `SpeedRamp` class: full algorithm to port (accel/decel/zero-hold/direction-change)
- `biba-controller/config.py` lines 158-165 — `RAMP_ACCEL_RATE`, `RAMP_DECEL_RATE`, `RAMP_REVERSE_DECEL_RATE`, `RAMP_ZERO_HOLD_S` default values

### Firmware — existing code to extend
- `firmware/src/modes/mode_standalone.c` — main standalone tick; ramp + SSR to be wired in here
- `firmware/src/app/failsafe.c` / `failsafe.h` — existing failsafe state machine (do not break)
- `firmware/src/drivers/bts7960.c` / `bts7960.h` — BTS7960 enable/drive abstraction
- `firmware/src/hal/biba_hal_rp2040.c` — HAL implementation; add `biba_hal_ssr_init/set` here
- `firmware/include/biba_config.h` — all `BIBA_*` tuning knobs; add ramp + SSR constants here
- `firmware/targets/RPICO_RP2040/target.h` — pin map; add `BIBA_PIN_SSR_GPIO GP16` here

### Requirements
- `.planning/REQUIREMENTS.md` — MOTOR-03 (ramping), SAFE-01 (500ms failsafe), SAFE-02 (ISR — deferred to Phase 2)

### Pin map
- `docs/wiring.md` — wiring reference for BTS7960 + CRSF + RP2040

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `biba_failsafe_t` + `biba_failsafe_tick()` in `failsafe.c` — complete, poll-based, no changes needed
- `biba_mix_differential()` in `control_loop.c` — differential mixer, stable
- `biba_hal_motor_pwm_init()` in `biba_hal_motor_rp2040.c` — 20 kHz HW PWM on slices 1/3; EN pins already driven LOW at boot (line 109-117)
- `rc_to_unit()` in `mode_standalone.c` — CRSF 172..1811 → -1..+1 float, correct and complete
- `biba_bts7960_drive(left, right)` — final output call; ramp output feeds directly here

### Established Patterns
- All new `biba_hal_*` functions: implement in `biba_hal_rp2040.c`, declare in `biba_hal.h`, stub in `biba_hal.c` (debug/native build)
- All new tuning constants: add to `biba_config.h` with `#ifndef` guard + comment mirroring Python config name
- New app modules (`ramp.c`): follow the `biba_` prefix convention, pure functions where possible (state passed by pointer)

### Integration Points
- New `biba_ramp_t` state structs: declare as `static` locals in `mode_standalone.c` (two instances: one per motor, initialized in `biba_mode_standalone_init()`)
- `biba_hal_ssr_set(armed)` call: immediately after `s_armed = armed` assignment in `mode_standalone_tick()`
- Ramp output replaces direct `left_out`/`right_out` before the `biba_bts7960_drive()` call

</code_context>

<specifics>
## Specific Ideas

- SSR primary use case: **remote thermal reset** — disarm → SSR cuts BTS7960 power → driver cools and exits
  thermal protection → arm → power restored. This avoids physical reboot of the robot.
- Ramp zero-hold (150 ms) is critical for BTS7960 longevity: prevents rapid direction reversals
  under load which stress the H-bridge output stage.
- The heading-hold PID in `mode_standalone.c` has `ki = 0` intentionally — no IMU data yet.
  Do not change this in Phase 1. It's a stub, not a bug.

</specifics>

<deferred>
## Deferred Ideas

- **Hardware alarm ISR failsafe (SAFE-02):** Upgrade to core0 hardware alarm ISR when I2C (IMU) is added in Phase 2. Architecture: alarm reset on each good CRSF frame, ISR calls `biba_hal_motor_pwm_stop()` directly on timeout.
- **SSR overtemp gate (THERM-01):** Overtemp signal → SSR OFF is Phase 3. Phase 1 SSR follows arm state only.
- **CRSF telemetry uplink:** `(void)tlm;` comment in `mode_standalone.c` line ~460. Follow-up patch, not Phase 1.
- **LittleFS / trim persistence:** Phase 2+ per D-00d.

</deferred>

---

*Phase: 1-Core Drive*
*Context gathered: 2025-07-14*
