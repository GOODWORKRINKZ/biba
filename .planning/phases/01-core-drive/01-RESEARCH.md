# Phase 1: Core Drive — Research

**Researched:** 2026-05-14
**Domain:** Embedded C firmware — RP2040 motor ramping + SSR GPIO HAL
**Confidence:** HIGH (all findings verified directly from codebase sources)

---

## Summary

Phase 1 has six of its eight in-scope requirements already implemented in the RP2040 port branch (CRSF receive, BTS7960 PWM, differential mix, arming logic, failsafe poll, CRSF ping). Two gaps remain: output ramping (MOTOR-03) and SSR control (implied by SAFE-03 and the D-09/D-13 decisions). Both are small, self-contained additions.

The ramp port is a near-mechanical translation of the 43-line Python `SpeedRamp.update()` algorithm into a C struct + two functions. The SSR HAL follows an identical pattern to the four existing BTS7960 EN-pin GPIOs already in `biba_hal_rp2040.c`. Integration into `mode_standalone.c` has three well-defined insertion points.

**Primary recommendation:** Port `SpeedRamp` to `firmware/src/app/ramp.c` first (pure, testable), add HAL SSR functions second (trivial GPIO), then wire both into `mode_standalone.c` in a single, reviewable diff. No build-system changes needed.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-00a:** Toolchain — earlephilhower arduino-pico (pico-sdk access, good library support)
- **D-00b:** No third-party CRSF/IMU libs — port existing `firmware/src/drivers/crsf.c` with pico-sdk primitives
- **D-00c:** HAL shim pattern — new files per peripheral, `build_src_filter` selects target; no `#ifdef RPICO` in shared `src/`
- **D-00d:** LittleFS for calibration/trim persistence (Phase 2+)
- **D-00e:** Failsafe on hardware alarm ISR deferred to Phase 2 when I2C is added
- **D-01:** Port full Python `SpeedRamp` to C (`firmware/src/app/ramp.c` / `ramp.h`)
- **D-02:** Defaults: `BIBA_RAMP_ACCEL_RATE = 2.0f`, `BIBA_RAMP_DECEL_RATE = 2.0f`, `BIBA_RAMP_REVERSE_DECEL_RATE = 0.5f`, `BIBA_RAMP_ZERO_HOLD_MS = 150u` — all in `biba_config.h` with `#ifndef` guards
- **D-03:** Ramp applied **post-mix** to `left_out` / `right_out` in `mode_standalone_tick()`
- **D-04:** On disarm or failsafe edge: **hard reset** ramp state (`ramp_reset()` → `current = 0, hold = 0`)
- **D-05:** Ramp always runs. **No bypass** when current limiter is clamping.
- **D-06:** Phase 1 failsafe: **poll-based** in `mode_standalone_tick()`. No change to existing failsafe.c.
- **D-07:** Hardware alarm ISR upgrade deferred to Phase 2.
- **D-08:** Failsafe timeout: `BIBA_CRSF_TIMEOUT_MS = 500` — no change.
- **D-09:** `BIBA_PIN_SSR_GPIO = 16` in `firmware/targets/RPICO_RP2040/target.h`
- **D-10:** SSR follows arm state: `armed=true` → HIGH, `armed=false` OR failsafe → LOW
- **D-11:** EN pins stay **HIGH** always after boot. SSR handles full power disconnection.
- **D-12:** No delay between SSR ON and PWM enable.
- **D-13:** `biba_hal_ssr_init()` + `biba_hal_ssr_set(bool)` in HAL; init called from `biba_hal_init()`; boots GP16 LOW.

### Agent's Discretion

- Internal ramp struct field naming in C (follow Python `SpeedRamp` naming where possible)
- SSR state update placement in `mode_standalone_tick()` — update SSR immediately after `armed` bool is computed, before motor drive section

### Deferred Ideas (OUT OF SCOPE)

- Hardware alarm ISR upgrade (Phase 2 when I2C added)
- IMU/heading-hold (Phase 2)
- Current-sense calibration (Phase 2)
- Thermal protection (Phase 3)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CRSF-01 | RP2040 receives ELRS/CRSF via UART, interrupt-driven | **ALREADY IMPLEMENTED** — ISR ring buffer in `biba_hal_rp2040.c` (lines 38-49), read in `ingest_crsf()` |
| CRSF-02 | RC_CHANNELS_PACKED decoded; channels mapped to drive commands | **ALREADY IMPLEMENTED** — `biba_crsf_unpack_channels()` + `rc_to_unit()` in `mode_standalone.c` |
| CRSF-03 | CRSF device ping at 5 Hz so ELRS EP01 outputs RC frames | **ALREADY IMPLEMENTED** — `send_crsf_ping()` every 200 ms in `mode_standalone_tick()` |
| MOTOR-01 | BTS7960 PWM at 20 kHz | **ALREADY IMPLEMENTED** — `biba_hal_motor_rp2040.c` PWM slices 1 & 3 |
| MOTOR-02 | Differential mixer | **ALREADY IMPLEMENTED** — `biba_mix_differential()` in `control_loop.c` |
| MOTOR-03 | Output ramping (accel/decel/direction-change/zero-hold) | **NOT YET IMPLEMENTED** — `firmware/src/app/ramp.c` + `ramp.h` to be created |
| SAFE-01 | 500 ms failsafe (motor stop on signal loss ≤ 500 ms) | **ALREADY IMPLEMENTED** — `biba_failsafe_tick()` in `failsafe.c`; timeout = `BIBA_CRSF_TIMEOUT_MS` |
| SAFE-03 | Arming logic (CH5 switch, deadband at neutral) | **ALREADY IMPLEMENTED** — arm_ch threshold, `BIBA_MOTOR_DEADBAND`, `biba_mode_standalone_tick()` |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CRSF receive + decode | HAL (RP2040 UART ISR) | App (mode_standalone ingest) | Hardware UART ISR buffers bytes; app drains and parses frames |
| Differential mix | App (`control_loop.c`) | — | Pure computation, no hardware dependency |
| Output ramping | App (`ramp.c`) | — | Pure stateful computation; state owned per motor in mode_standalone |
| Motor PWM output | HAL (`biba_hal_motor_rp2040.c`) | BTS7960 driver shim | Hardware PWM slices; driver shim applies direction inversion |
| Failsafe timer | App (`failsafe.c`) | — | Poll-based for Phase 1; state machine is standalone |
| SSR power relay | HAL (`biba_hal_rp2040.c`) | — | GPIO output; follows arm state set by mode_standalone |
| Arming logic | App (`mode_standalone.c`) | — | RC channel threshold + deadband; owns arm state |

---

## Standard Stack

### Core (no new dependencies — everything is pico-sdk primitives)

| Library/Module | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| pico-sdk `hardware/gpio.h` | bundled with earlephilhower | GPIO init + set for SSR | Same pattern already used for 4 EN pins in `biba_hal_init()` |
| Unity | ^2.6.1 (already in `native_test`) | Firmware unit test framework | Already configured in `platformio.ini` `[env:native_test]` |

**No new packages required.** GP16 GPIO + soft-float arithmetic are entirely within existing pico-sdk and codebase.

### New Source Files

| File | Location | What it contains |
|------|----------|-----------------|
| `ramp.h` | `firmware/src/app/` | `biba_ramp_t` struct + 3 function declarations |
| `ramp.c` | `firmware/src/app/` | `biba_ramp_init`, `biba_ramp_reset`, `biba_ramp_update` |
| `test_ramp/test_main.c` | `firmware/test/` | Unity-based tests, mirrors `tests/test_ramping.py` |

---

## Architecture Patterns

### SpeedRamp C Port

**Full algorithm verified against `biba-controller/motors/ramping.py`** [VERIFIED: codebase]

The Python `SpeedRamp` has two mutable state fields; three constructor params become config constants:

```c
/* firmware/src/app/ramp.h  [VERIFIED: direct Python translation] */
typedef struct {
    float current;            /* _current in Python SpeedRamp */
    float hold_remaining_s;   /* _hold_remaining in Python SpeedRamp */
} biba_ramp_t;

void  biba_ramp_init(biba_ramp_t *r);
void  biba_ramp_reset(biba_ramp_t *r);                    /* D-04: hard reset */
float biba_ramp_update(biba_ramp_t *r, float target, float dt);
```

`biba_config.h` additions (with `#ifndef` guards):
```c
/* --- Output ramping (MOTOR-03) ----------------------------------------- */
/* Mirror RAMP_* from biba-controller/config.py lines 157-162.             */
#ifndef BIBA_RAMP_ACCEL_RATE
#  define BIBA_RAMP_ACCEL_RATE           2.0f   /* RAMP_ACCEL_RATE        */
#endif
#ifndef BIBA_RAMP_DECEL_RATE
#  define BIBA_RAMP_DECEL_RATE           2.0f   /* RAMP_DECEL_RATE        */
#endif
#ifndef BIBA_RAMP_REVERSE_DECEL_RATE
#  define BIBA_RAMP_REVERSE_DECEL_RATE   0.5f   /* RAMP_REVERSE_DECEL_RATE */
#endif
#ifndef BIBA_RAMP_ZERO_HOLD_MS
#  define BIBA_RAMP_ZERO_HOLD_MS         150u   /* RAMP_ZERO_HOLD_S * 1000 */
#endif
```

**`biba_ramp_update()` algorithm** (C translation of `SpeedRamp.update()`):

```c
/* Source: biba-controller/motors/ramping.py::SpeedRamp.update() */
float biba_ramp_update(biba_ramp_t *r, float target, float dt)
{
    if (dt <= 0.0f) return r->current;

    /* Clamp target */
    if (target >  1.0f) target =  1.0f;
    if (target < -1.0f) target = -1.0f;

    /* Zero-hold: stay at zero until hold timer expires */
    if (r->hold_remaining_s > 0.0f) {
        r->hold_remaining_s -= dt;
        if (r->hold_remaining_s > 0.0f)
            return r->current;   /* still holding at 0.0 */
        r->hold_remaining_s = 0.0f;
    }

    /* Direction change: decel toward zero first, do NOT cross zero */
    if ((r->current > 0.0f && target < 0.0f) ||
        (r->current < 0.0f && target > 0.0f)) {
        float max_step = BIBA_RAMP_REVERSE_DECEL_RATE * dt;
        float abs_cur = r->current < 0.0f ? -r->current : r->current;
        if (abs_cur <= max_step) {
            r->current = 0.0f;
            r->hold_remaining_s = (float)BIBA_RAMP_ZERO_HOLD_MS / 1000.0f;
        } else if (r->current > 0.0f) {
            r->current -= max_step;
        } else {
            r->current += max_step;
        }
        return r->current;
    }

    /* Same sign (or zero→nonzero): accel or decel */
    float diff = target - r->current;
    float abs_diff = diff < 0.0f ? -diff : diff;
    if (abs_diff < 1e-9f) return r->current;

    float abs_target = target < 0.0f ? -target : target;
    float abs_current = r->current < 0.0f ? -r->current : r->current;
    bool accelerating = abs_target > abs_current;
    float rate = accelerating ? BIBA_RAMP_ACCEL_RATE : BIBA_RAMP_DECEL_RATE;
    float max_step = rate * dt;

    if (abs_diff <= max_step) {
        r->current = target;
    } else {
        r->current += diff > 0.0f ? max_step : -max_step;
    }

    if (r->current >  1.0f) r->current =  1.0f;
    if (r->current < -1.0f) r->current = -1.0f;
    return r->current;
}
```

**Key difference from Python**: The Python `_decel_toward_zero()` helper sets `_hold_remaining` when it reaches zero. The C translation inlines this into `biba_ramp_update()`. Behaviour is identical.

### SSR GPIO HAL Pattern

**Verified against existing EN-pin initialization in `biba_hal_rp2040.c` lines 108-117** [VERIFIED: codebase]

```c
/* biba_hal_rp2040.c — add to biba_hal_ssr_init() and call from biba_hal_init() */
void biba_hal_ssr_init(void)
{
    gpio_init(BIBA_PIN_SSR_GPIO);
    gpio_set_dir(BIBA_PIN_SSR_GPIO, GPIO_OUT);
    gpio_put(BIBA_PIN_SSR_GPIO, 0);   /* LOW = SSR off = BTS7960 power off */
}

void biba_hal_ssr_set(bool enabled)
{
    gpio_put(BIBA_PIN_SSR_GPIO, enabled ? 1u : 0u);
}
```

Pattern is byte-for-byte identical to the existing EN pin setup loop — no new pico-sdk APIs needed.

### Integration in `mode_standalone.c`

**Three insertion points** — verified by reading the full tick function [VERIFIED: codebase]:

**Point 1 — `biba_mode_standalone_init()`**: add two ramp states and SSR init. The `biba_hal_ssr_init()` is called from `biba_hal_init()` (called before `biba_mode_standalone_init()`), so at init time SSR is already LOW. The `biba_bts7960_set_enabled(true)` call in `mode_standalone_init()` is correct per D-11 (EN pins HIGH always); SSR is LOW so BTS7960 has no power — safe.

```c
/* In biba_mode_standalone_init() — declare as static in file scope */
static biba_ramp_t s_ramp_left;
static biba_ramp_t s_ramp_right;

/* In biba_mode_standalone_init() body: */
biba_ramp_init(&s_ramp_left);
biba_ramp_init(&s_ramp_right);
```

**Point 2 — Arm/disarm/failsafe edge handlers in `mode_standalone_tick()`**: hard reset ramps and update SSR. The exact locations verified:

```c
/* --- FAILSAFE RISING EDGE (already exists) --- */
if (failsafe && !s_last_failsafe) {
    biba_melody_player_start(&s_player, &biba_melody_failsafe);
    biba_ramp_reset(&s_ramp_left);   /* D-04: hard reset on failsafe edge */
    biba_ramp_reset(&s_ramp_right);
}
s_last_failsafe = failsafe;

/* --- DISARM EDGE (already exists) --- */
if (!armed && s_armed) {
    /* ... existing disarm log + melody ... */
    biba_ramp_reset(&s_ramp_left);   /* D-04: hard reset on disarm edge */
    biba_ramp_reset(&s_ramp_right);
}
s_armed = armed;
biba_hal_ssr_set(armed);            /* D-10: SSR follows arm state */
```

**Point 3 — Post-mix pre-drive section in `mode_standalone_tick()`**: apply ramp after the `if (armed)` block, before melody/drive:

```c
/* --- After the if (armed) { ... } block --- */
/* D-03: Apply ramp post-mix. Ramp always runs; hard-reset on disarm/failsafe
 * ensures it starts from 0 when next armed. */
left_out  = biba_ramp_update(&s_ramp_left,  left_out,  dt);
right_out = biba_ramp_update(&s_ramp_right, right_out, dt);

/* --- Existing melody / drive code continues unchanged --- */
```

**Why these three points are correct and safe**:
- Failsafe edge reset fires before `s_last_failsafe` is updated → guaranteed on rising edge only
- Disarm edge reset fires inside the `!armed && s_armed` branch → only on transition
- `biba_hal_ssr_set(armed)` after `s_armed = armed` captures the fully-resolved armed state
- Ramp applied after `if (armed)` means both `left_out=0`/`right_out=0` (disarmed path) and the computed values (armed path) pass through the ramp — no special case needed
- `going_reverse` check (which uses `left_out`/`right_out`) comes AFTER the ramp application point, so it correctly uses the ramped output

### Anti-Patterns to Avoid

- **Don't apply ramp inside `if (armed)` block**: Then the ramp freezes when disarmed. The disarm/failsafe reset already zeroes the state; calling ramp_update(0,dt) from state=0 is correct no-op behavior.
- **Don't reset ramp on every disarmed tick**: Reset only on the **edge** (transition from armed to disarmed). Resetting every disarmed tick would also work but is redundant.
- **Don't add deadband inside `biba_ramp_update()`**: The deadband is already enforced by the `control_active` check in `mode_standalone_tick()` and by `BIBA_MOTOR_DEADBAND`. Adding a second deadband to the ramp would cause inconsistency when current-limited outputs are near zero.
- **Don't use `uint32_t hold_remaining_ms` with integer arithmetic**: The `dt` passed to `biba_ramp_update()` is already a float. Using `hold_remaining_s` (float) exactly mirrors Python and avoids a float→int→float cast introducing rounding.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GPIO OUTPUT drive | Any abstraction beyond gpio_put | `gpio_init()` + `gpio_set_dir()` + `gpio_put()` directly | Already the pattern for all 6 GPIO outputs in `biba_hal_init()` |
| Unit test assertions | Custom assert macros | `biba_test_support.h` Unity macros (already exists) | Codebase already has a standalone Unity shim for gcc builds |
| Float rate-of-change limiter | Home-grown slew | `biba_ramp_update()` | Algorithm is non-trivial: zero-hold, separate direction-change rate, no-overshoot — already proven in Python production use |

---

## Build System — No Changes Required

[VERIFIED: platformio.ini `rp2040_src_filter` and `common.build_src_filter`]

**`firmware/src/app/ramp.c` is auto-included by both build environments:**

| Env | Filter rule | Effect on `src/app/ramp.c` |
|-----|-------------|---------------------------|
| `rpico_rp2040_standalone` | `+<*>` then `-<hal/biba_hal.c>`, `-<hal/biba_hal_motor.c>`, `-<hal/biba_hal_debug.c>`, `-<main.c>` | **Included** — `src/app/` not excluded |
| `native_test` | `+<*>` then `-<hal/>`, `-<drivers/>` (except crsf.c), `-<modes/>`, `-<main.c>`, `-<app/telemetry.c>` | **Included** — `src/app/ramp.c` not in any exclusion |

**New test directory** `firmware/test/test_ramp/` is auto-discovered by PlatformIO. No `test_ignore` entry in `[env:native_test]` covers it. **Zero platformio.ini changes needed.**

For `biba_hal_ssr_init()` / `biba_hal_ssr_set()` in `biba_hal.h`:
- RP2040 build: implement in `biba_hal_rp2040.c`
- STM32 builds: add no-op stubs to `biba_hal.c` (same convention as any HAL function not available on a given target)
- Native_test: HAL dir excluded entirely — no stubs needed for `ramp.c` tests

---

## Common Pitfalls

### Pitfall 1: `dt = 0` on the first tick

**What goes wrong:** `s_last_tick_ms` is set to `biba_hal_now_ms()` in `biba_mode_standalone_init()`. If the first tick executes within the same millisecond as init, `now - s_last_tick_ms = 0`, giving `dt = 0.0f`. The Python `SpeedRamp.update()` explicitly returns `self._current` when `dt <= 0.0`. The C port **must** guard this with `if (dt <= 0.0f) return r->current;` as the first line.

**Why it happens:** RP2040 `to_ms_since_boot()` has 1 ms resolution; microsecond sub-tick gaps truncate to 0.

**How to avoid:** Guard is included in the algorithm above. Test coverage: add `test_dt_zero_returns_current` to `test_ramp/test_main.c`.

### Pitfall 2: Ramp advance blocked during melody playback

**What goes wrong:** If `biba_ramp_update()` is placed inside the `if (!s_player.active)` block (alongside the drive call), the ramp state freezes while a melody plays (1-3 seconds). When melody ends, motors jump to the current commanded value instead of ramping from wherever they were.

**How to avoid:** Place both ramp calls **before** the `if (!s_player.active)` check. The ramp always advances; it is the `biba_bts7960_drive()` call that is conditioned on melody state, not the ramp.

### Pitfall 3: `going_reverse` uses stale pre-ramp `left_out`/`right_out`

**What goes wrong:** If ramp is applied after the `going_reverse` check, the backup-pip logic sees pre-ramp values. At the start of a reversal, `left_out`/`right_out` are negative (commanded), but the ramp output is still positive (decelerating toward zero). The `going_reverse` flag would fire prematurely.

**How to avoid:** Apply both ramp calls before the `going_reverse` check. The architecture diagram above shows the correct ordering. The `going_reverse` check is inside the melody block which comes after the post-mix area — so the natural placement (right after the `if (armed)` block) is already correct.

### Pitfall 4: `biba_hal_ssr_init()` called after `biba_hal_motor_pwm_init()`

**What goes wrong:** At boot, the PWM slices start at duty=0 (verified: `biba_hal_motor_pwm_init()` sets wrap=0 before mode_standalone calls `biba_bts7960_set_enabled(true)`). If SSR init were somehow delayed and SSR came up HIGH before EN pins are driven and PWM=0 is confirmed, there's a window of undefined state on the BTS7960.

**How to avoid:** `biba_hal_ssr_init()` is called inside `biba_hal_init()` after `biba_hal_motor_pwm_init()` — SSR LOW is set last in the GPIO sequence, guaranteeing the BTS7960 has no power until intentionally armed. **Do not call `biba_hal_ssr_init()` from mode_standalone_init().**

### Pitfall 5: `biba_hal_ssr_set()` called before `s_armed` is updated

**What goes wrong:** If `biba_hal_ssr_set(armed)` is placed before `s_armed = armed`, the SSR uses the new armed state but `s_armed` still reflects the previous tick, causing the arm/disarm edge detection on the next tick to fire with a one-tick delay.

**How to avoid:** Canonical placement: `s_armed = armed; biba_hal_ssr_set(armed);` — exactly as shown in the integration diagram.

---

## Code Examples

### biba_ramp_t initialization

```c
/* Source: direct from Python SpeedRamp.__init__ fields */
void biba_ramp_init(biba_ramp_t *r)
{
    r->current = 0.0f;
    r->hold_remaining_s = 0.0f;
}

void biba_ramp_reset(biba_ramp_t *r)
{
    /* D-04: hard reset — no gradual decel */
    r->current = 0.0f;
    r->hold_remaining_s = 0.0f;
}
```

### target.h addition (RPICO_RP2040)

```c
/* --- SSR (Solid-State Relay) — BTS7960 power control --- */
/* GP16 is the first free pin after the SBC SPI interface (GP10-GP14).    */
/* HIGH = BTS7960 powered; LOW = BTS7960 power cut.                       */
#define BIBA_PIN_SSR_GPIO            16
```

### biba_hal.h declarations

```c
/* --- SSR (Solid-State Relay) -------------------------------------------- */
/* Initialise GP16 (BIBA_PIN_SSR_GPIO) as output, drive LOW (safe default). */
void biba_hal_ssr_init(void);
/* Drive the SSR: enabled=true → HIGH (BTS7960 powered), false → LOW.       */
void biba_hal_ssr_set(bool enabled);
```

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Unity ^2.6.1 via PlatformIO |
| Config file | `firmware/platformio.ini` `[env:native_test]` |
| Quick run (ramp only) | `cd firmware && pio test -e native_test -f test_ramp` |
| Full firmware suite | `cd firmware && pio test -e native_test` |
| Run from project root | `cd firmware && pio test -e native_test` |

### Phase Requirements → Test Map

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

### Wave 0 Gaps

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

### Sampling Rate

- Per task commit: `cd firmware && pio test -e native_test -f test_ramp`
- Per wave merge: `cd firmware && pio test -e native_test`
- Phase gate: full suite green before `/gsd-verify-work`

---

## Security Domain

This is safety-critical embedded firmware, not a web application. OWASP ASVS web categories (V2 auth, V3 sessions, V5 input validation) do not apply. The relevant safety invariants:

| Invariant | Control | Where enforced |
|-----------|---------|---------------|
| No motor output before valid RC frame | `biba_failsafe_t.primed = false` at boot; `active = true` until first `mark_fresh()` | `failsafe.c` — already implemented |
| Motor stops on signal loss ≤ 500 ms | `BIBA_CRSF_TIMEOUT_MS = 500` timeout enforced each tick | `failsafe.c` — already implemented |
| BTS7960 unpowered at boot | `biba_hal_ssr_init()` drives GP16 LOW; PWM = 0 | `biba_hal_rp2040.c` — to be added |
| SSR off on disarm/failsafe edge | `biba_hal_ssr_set(armed)` called each tick after arm state resolved | `mode_standalone.c` — to be wired |
| Ramp never drives from non-zero after disarm | Hard reset on disarm/failsafe edge (D-04) | `ramp.c` reset + wiring in `mode_standalone.c` |

No network interface, no parsing of untrusted input, no flash writes in Phase 1 — attack surface is zero beyond physical RC link.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PlatformIO | Build + test | ✓ | local install | — |
| `pio test -e native_test` (gcc native) | MOTOR-03 unit tests | ✓ | confirmed by existing test_crsf + test_control_loop in repo | — |
| RP2040 hardware (Pico/YD-RP2040) | MOTOR-01, SAFE-03 hardware verify | [ASSUMED] present on bench | — | Defer hardware tests to flash step |
| ELRS EP01 receiver | CRSF-03 hardware verify | [ASSUMED] present | — | Can test CRSF ping frame construction in native test |

---

## Open Questions (RESOLVED)

1. **`biba_hal_ssr_set(false)` vs no-call during melody playback**
   - What we know: Melody blocks `biba_bts7960_drive()`, not PWM duty (PWM is already 0 when disarmed)
   - What's unclear: If a melody fires during the arm→disarm transition, the SSR is driven LOW immediately by the disarm edge handler — before melody completes. This is correct (safety) but means BTS7960 loses power mid-melody.
   - RESOLVED: Accept this — safety first. No change needed. Plan 01-04 Edit A adds explicit `biba_hal_ssr_set(false)` in the failsafe edge block.

2. **`biba_hal.c` (STM32) stubs for SSR**
   - What we know: All other HAL functions in `biba_hal.h` have implementations in both `biba_hal.c` (STM32) and `biba_hal_rp2040.c`. The SSR is RP2040-only for Phase 1.
   - What's unclear: Does any STM32 target build need to compile cleanly with these new declarations?
   - RESOLVED: Add no-op stubs to `biba_hal.c`. Cost: 2 lines. Avoids linker errors if STM32 builds are exercised in CI. Implemented in Plan 01-02 Task 2.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | RP2040 hardware and ELRS EP01 receiver are on the bench for Phase 1 hardware testing | Environment Availability | MOTOR-01, SAFE-03 hardware verification cannot proceed; descope to Phase 2 |

---

## Sources

### Primary (HIGH confidence — verified from codebase)
- `biba-controller/motors/ramping.py` — full `SpeedRamp` algorithm (43 lines)
- `biba-controller/config.py` lines 157-162 — `RAMP_ACCEL_RATE=2.0`, `RAMP_DECEL_RATE=2.0`, `RAMP_REVERSE_DECEL_RATE=0.5`, `RAMP_ZERO_HOLD_S=0.15`
- `firmware/src/hal/biba_hal_rp2040.c` lines 100-115 — exact GPIO init pattern for SSR
- `firmware/src/modes/mode_standalone.c` full tick function — integration points verified
- `firmware/src/app/failsafe.c` — failsafe state machine confirmed, no changes needed
- `firmware/targets/RPICO_RP2040/target.h` — confirmed GP16 is unassigned (first free pin after GP15)
- `firmware/platformio.ini` — `rp2040_src_filter` and `common.build_src_filter` confirmed no changes needed
- `firmware/test/test_control_loop/test_main.c` + `firmware/test/test_crsf/test_main.c` — Unity test pattern confirmed
- `firmware/test/test_support/biba_test_support.h` — `BIBA_TEST_STANDALONE_MAIN` macro and assertion macros confirmed

---

## Metadata

**Confidence breakdown:**

| Area | Level | Reason |
|------|-------|--------|
| SpeedRamp C port | HIGH | Algorithm verified line-by-line from Python source |
| SSR HAL | HIGH | Exact GPIO pattern already in codebase for EN pins |
| Integration points | HIGH | Full tick function read and all three insertion points located precisely |
| Build system | HIGH | Both src_filter chains read; confirmed zero changes needed |
| Test strategy | HIGH | Unity pattern verified from two existing test directories |
| Pitfalls | HIGH | dt=0, ramp-during-melody, going_reverse ordering all verified from code |

**Research date:** 2026-05-14
**Valid until:** 2026-06-14 (codebase is stable; pico-sdk GPIO API is stable)
