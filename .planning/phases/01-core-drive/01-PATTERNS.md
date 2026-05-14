# Phase 1: Core Drive — Pattern Map

**Mapped:** 2026-05-14
**Files analyzed:** 8 (3 new + 5 modified)
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `firmware/src/app/ramp.c` | app-module (state machine) | transform / stateful | `firmware/src/app/failsafe.c` | exact |
| `firmware/src/app/ramp.h` | app-module header | — | `firmware/src/app/failsafe.h` | exact |
| `firmware/test/test_ramp/test_main.c` | test | — | `firmware/test/test_control_loop/test_main.c` | exact |
| `firmware/include/biba_config.h` | config (modify) | — | existing `#ifndef` guards in same file | exact |
| `firmware/targets/RPICO_RP2040/target.h` | target pin map (modify) | — | existing `BIBA_PIN_*_GPIO` defines in same file | exact |
| `firmware/src/hal/biba_hal.h` | HAL interface (modify) | — | `biba_hal_left_enable` / `biba_hal_right_enable` section in same file | exact |
| `firmware/src/hal/biba_hal.c` | HAL stub — STM32 no-op (modify) | — | `biba_hal_left_enable` / `biba_hal_right_enable` in same file | exact |
| `firmware/src/hal/biba_hal_rp2040.c` | HAL implementation (modify) | GPIO output | EN-pin init loop in same file lines 107-116 | exact |
| `firmware/src/modes/mode_standalone.c` | app mode controller (modify) | control loop | existing arm/disarm edge handlers + motor drive section | exact |

---

## Pattern Assignments

### `firmware/src/app/ramp.h` (new — app-module header)

**Analog:** `firmware/src/app/failsafe.h` (entire file, 40 lines)

**Header guard + extern C + includes pattern** (failsafe.h lines 1-16):
```c
#ifndef BIBA_FAILSAFE_H
#define BIBA_FAILSAFE_H

/* Failsafe helpers shared between standalone and companion modes.
 * ... */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
```

**Struct pattern** (failsafe.h lines 18-24):
```c
typedef struct {
    uint32_t timeout_ms;
    uint32_t last_ok_ms;
    bool     primed;
    bool     active;
} biba_failsafe_t;
```

**Function declarations pattern** (failsafe.h lines 26-38):
```c
/* Initialise the failsafe with a grace period. active=false until tick runs. */
void biba_failsafe_init(biba_failsafe_t *fs, uint32_t timeout_ms);

/* Mark that a fresh frame has just been received at now_ms. */
void biba_failsafe_mark_fresh(biba_failsafe_t *fs, uint32_t now_ms);

/* Advance time without a fresh frame. Updates active flag. Returns true
 * iff the failsafe is currently active (i.e. upstream is silent). */
bool biba_failsafe_tick(biba_failsafe_t *fs, uint32_t now_ms);

/* Query current state without advancing time. */
bool biba_failsafe_is_active(const biba_failsafe_t *fs);
```

**Footer pattern** (failsafe.h lines 38-40):
```c
#ifdef __cplusplus
}
#endif

#endif /* BIBA_FAILSAFE_H */
```

**Translate to ramp.h:**
```c
#ifndef BIBA_RAMP_H
#define BIBA_RAMP_H

/* Output slew-rate limiter for motor speed commands.
 *
 * Port of biba-controller/motors/ramping.py::SpeedRamp.
 * Per-motor state is owned by the caller (mode_standalone.c).
 * Config constants live in biba_config.h (BIBA_RAMP_*). */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float current;           /* _current in Python SpeedRamp */
    float hold_remaining_s;  /* _hold_remaining in Python SpeedRamp */
} biba_ramp_t;

void  biba_ramp_init(biba_ramp_t *r);
void  biba_ramp_reset(biba_ramp_t *r);                     /* D-04: hard reset to zero */
float biba_ramp_update(biba_ramp_t *r, float target, float dt);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_RAMP_H */
```

---

### `firmware/src/app/ramp.c` (new — app-module state machine)

**Analog:** `firmware/src/app/failsafe.c` (entire file, 44 lines)

**Includes + null-guard pattern** (failsafe.c lines 1-9):
```c
#include "failsafe.h"

#include <string.h>

void biba_failsafe_init(biba_failsafe_t *fs, uint32_t timeout_ms)
{
    if (fs == NULL) return;
    fs->timeout_ms = timeout_ms;
    ...
}
```

**Init function pattern** (failsafe.c lines 6-12 — clears all state fields):
```c
void biba_failsafe_init(biba_failsafe_t *fs, uint32_t timeout_ms)
{
    if (fs == NULL) return;
    fs->timeout_ms = timeout_ms;
    fs->last_ok_ms = 0;
    fs->primed = false;
    fs->active = true;  /* default-active until we see at least one frame */
}
```

**Translate to ramp_init / ramp_reset:**
```c
#include "ramp.h"

void biba_ramp_init(biba_ramp_t *r)
{
    if (r == NULL) return;
    r->current = 0.0f;
    r->hold_remaining_s = 0.0f;
}

void biba_ramp_reset(biba_ramp_t *r)   /* D-04: emergency stop */
{
    if (r == NULL) return;
    r->current = 0.0f;
    r->hold_remaining_s = 0.0f;
}
```

**Core update function** — direct C translation of `SpeedRamp.update()` from
`biba-controller/motors/ramping.py` lines 80-138 (verified in RESEARCH.md):
```c
float biba_ramp_update(biba_ramp_t *r, float target, float dt)
{
    if (r == NULL || dt <= 0.0f) return r ? r->current : 0.0f;

    /* Clamp target to [-1, 1] */
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

    float abs_target  = target    < 0.0f ? -target    : target;
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

> **Pitfall — Python `_decel_toward_zero()` helper:** The Python implementation
> calls a separate `_decel_toward_zero()` helper which sets `_hold_remaining`
> when it reaches zero. The C translation inlines this branch — behaviour is
> identical. Do not re-introduce a helper function; the inline form is clearer
> in C because `bool` is not implicitly available.

> **Pitfall — `dt=0` guard:** The Python `if dt <= 0.0` returns early. The C
> version must guard on `dt <= 0.0f` (float). The loop timer in
> `mode_standalone_tick()` can produce `dt = 0` on the very first tick when
> `now == s_last_tick_ms`.

---

### `firmware/test/test_ramp/test_main.c` (new — Unity tests)

**Analog:** `firmware/test/test_control_loop/test_main.c`

**Includes pattern** (test_control_loop/test_main.c lines 1-8):
```c
#include <math.h>
#include <stdint.h>
#include <string.h>

#include "control_loop.h"
#include "failsafe.h"
#include "biba_test_support.h"
```

**Static helper pattern** (test_control_loop/test_main.c lines 10-30 — wrap struct construction):
```c
static biba_motor_current_t ok_sample(float amps)
{
    biba_motor_current_t s = { .current_a = amps, .valid = true };
    return s;
}
```

**Test function pattern** (test_control_loop/test_main.c lines 32-55):
```c
static void test_clamp_unit_bounds(void)
{
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 1.0f, biba_clamp_unit(1.5f));
    TEST_ASSERT_FLOAT_WITHIN(1e-6, -1.0f, biba_clamp_unit(-2.0f));
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.3f, biba_clamp_unit(0.3f));
}
```

**`run_all()` + `main()` pattern** (test_control_loop/test_main.c lines 186-200):
```c
static void run_all(void)
{
    RUN_TEST(test_clamp_unit_bounds);
    RUN_TEST(test_limiter_passes_through_when_below_limits);
    /* ... */
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
```

**Translate to test_ramp/test_main.c — required test cases** (mirror
`tests/test_ramping.py`):

```c
#include <math.h>
#include <stdint.h>

#include "ramp.h"
#include "biba_test_support.h"

static void test_init_starts_at_zero(void) { /* r.current == 0 */ }
static void test_reset_returns_to_zero(void) { /* after update, reset → current = 0 */ }
static void test_accel_toward_positive_target(void) { /* partial step on first tick */ }
static void test_reaches_target_after_enough_ticks(void) { /* eventually == target */ }
static void test_decel_toward_zero(void) { /* slower rate when |target| < |current| */ }
static void test_direction_change_decels_to_zero_first(void) { /* current stays ≥ 0 while decelling from +1 toward -1 */ }
static void test_zero_hold_delays_next_direction(void) { /* hold_remaining_s set after hitting 0 during reversal */ }
static void test_zero_hold_expires_and_resumes(void) { /* after hold_remaining_s ticks, begins accelerating in new dir */ }
static void test_dt_zero_returns_unchanged(void) { /* dt=0 guard */ }
static void test_clamps_target_above_one(void) { /* target > 1.0 clamped to 1.0 */ }
static void test_clamps_target_below_minus_one(void) { /* target < -1.0 clamped to -1.0 */ }
static void test_reverse_decel_rate_used_for_direction_change(void) { /* uses BIBA_RAMP_REVERSE_DECEL_RATE, not DECEL_RATE */ }
```

> **Pitfall — melody-gate ordering test:** `test_ramping.py` verifies that the
> ramp state is a pure function of (target, dt, state). The test file must NOT
> call `biba_hal_*` or `biba_melody_*` — ramp.c has zero HAL dependencies.
> This is the reason ramp.c belongs in `app/` (included by native_test) rather
> than `modes/` (excluded).

---

### `firmware/include/biba_config.h` (modify — add BIBA_RAMP_* constants)

**Analog:** existing `#ifndef` guard pattern in same file (lines 22-30):
```c
/* --- Control loop timing ------------------------------------------------ */

#ifndef BIBA_CONTROL_LOOP_HZ
#  define BIBA_CONTROL_LOOP_HZ         500
#endif
#ifndef BIBA_TELEMETRY_PUBLISH_HZ
#  define BIBA_TELEMETRY_PUBLISH_HZ    200
#endif
```

**Insertion point:** After the `/* --- Motor / PWM ---` section (around line 36),
before `/* --- Current / power limits ---`. Add a new section:

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

---

### `firmware/targets/RPICO_RP2040/target.h` (modify — add BIBA_PIN_SSR_GPIO)

**Analog:** existing `BIBA_PIN_*_GPIO` defines in same file (lines 79-96):
```c
/* --- Motor enables (GPIO OUT) ------------------------------------------ */
/* Left driver: GP4/GP5 (adjacent to GP2/GP3 PWM — all 4 pins together). */
/* Right driver: GP8/GP9 (adjacent to GP6/GP7 PWM — all 4 pins together). */
#define BIBA_PIN_LEFT_REN_GPIO       4
#define BIBA_PIN_LEFT_LEN_GPIO       5
#define BIBA_PIN_RIGHT_REN_GPIO      8
#define BIBA_PIN_RIGHT_LEN_GPIO      9
```

**Insertion point:** After the `BIBA_PIN_MODE_SEL_GPIO 15` line (end of GP0-GP15
block), in the `/* Pin assignment — right side (GP16-GP29) */` section.
GP16 is the first unassigned pin on the right side:

```c
/* --- SSR (Solid-State Relay) — BTS7960 power (D-09) ------------------- */
/* GP16 is the first free pin after the SBC SPI interface (GP10-GP14).    */
#define BIBA_PIN_SSR_GPIO            16
```

> **Note:** Add the corresponding comment to the pin table at the top of
> `target.h` (the ASCII pin map): `GP16 GPIO OUT  SSR (BTS7960 power relay)`
> to keep the table accurate.

---

### `firmware/src/hal/biba_hal.h` (modify — declare SSR HAL functions)

**Analog:** `biba_hal_left_enable` / `biba_hal_right_enable` declarations (lines 46-48):
```c
/* BTS7960 enables, high-level. */
void biba_hal_left_enable(bool enabled);
void biba_hal_right_enable(bool enabled);
```

**Insertion point:** Before `/* --- Motor PWM ---` section (after line 48),
or alternatively after the `biba_hal_spi_slave_poll` declaration and before
the `biba_hal_i2c_write` / closing block. Either location is acceptable;
grouping with the GPIO section (near `biba_hal_left_enable`) is preferred
for readability.

```c
/* --- SSR (Solid-State Relay) — BTS7960 power relay (D-13) -------------- */

/* Initialise SSR GPIO output LOW (BTS7960 power off). Called from
 * biba_hal_init(). On targets without BIBA_PIN_SSR_GPIO this is a no-op. */
void biba_hal_ssr_init(void);

/* Drive the SSR: true = HIGH (BTS7960 powered), false = LOW (power off).
 * Called by mode_standalone on arm/disarm/failsafe edges (D-10). */
void biba_hal_ssr_set(bool enabled);
```

---

### `firmware/src/hal/biba_hal.c` (modify — add STM32 no-op stubs)

**Analog:** `biba_hal_left_enable` and `biba_hal_right_enable` in same file
(approximately lines 193-205):
```c
void biba_hal_left_enable(bool enabled)
{
    GPIO_PinState s = enabled ? GPIO_PIN_SET : GPIO_PIN_RESET;
    HAL_GPIO_WritePin(BIBA_PIN_LEFT_REN_PORT, BIBA_PIN_LEFT_REN_PIN, s);
    HAL_GPIO_WritePin(BIBA_PIN_LEFT_LEN_PORT, BIBA_PIN_LEFT_LEN_PIN, s);
}

void biba_hal_right_enable(bool enabled)
{
    GPIO_PinState s = enabled ? GPIO_PIN_SET : GPIO_PIN_RESET;
    HAL_GPIO_WritePin(BIBA_PIN_RIGHT_REN_PORT, BIBA_PIN_RIGHT_REN_PIN, s);
    HAL_GPIO_WritePin(BIBA_PIN_RIGHT_LEN_PORT, BIBA_PIN_RIGHT_LEN_PIN, s);
}
```

**Insertion point:** After the `biba_hal_right_enable` function body, before
the `biba_hal_adc_sample` section. Add no-op stubs so STM32 link units compile
without `BIBA_PIN_SSR_GPIO` being defined:

```c
/* SSR — no-op on STM32 targets. SSR is RP2040-only; see biba_hal_rp2040.c. */
void biba_hal_ssr_init(void) {}
void biba_hal_ssr_set(bool enabled) { (void)enabled; }
```

> **Why no-op and not `#error`:** All STM32 firmware envs link biba_hal.c.
> Declaring `biba_hal_ssr_init/set` as no-ops lets the STM32 link succeed
> without `BIBA_PIN_SSR_GPIO`. An `#ifdef BIBA_TARGET_RPICO_RP2040` guard
> would also work but violates D-00c ("no `#ifdef RPICO` in shared `src/`").

---

### `firmware/src/hal/biba_hal_rp2040.c` (modify — add RP2040 SSR implementation)

**Analog:** EN-pin init loop in `biba_hal_init()` (lines 107-116):
```c
    /* BTS7960 enables: output, start disabled. */
    const uint en_pins[] = {
        BIBA_PIN_LEFT_REN_GPIO, BIBA_PIN_LEFT_LEN_GPIO,
        BIBA_PIN_RIGHT_REN_GPIO, BIBA_PIN_RIGHT_LEN_GPIO,
    };
    for (unsigned i = 0; i < 4u; i++) {
        gpio_init(en_pins[i]);
        gpio_set_dir(en_pins[i], GPIO_OUT);
        gpio_put(en_pins[i], 0);
    }
```

**New functions to add** (after `biba_hal_init`, before `biba_hal_now_ms`):
```c
/* --- SSR (GP16 GPIO out) ----------------------------------------------- */

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

**Insertion point in `biba_hal_init()`:** Call `biba_hal_ssr_init()` directly
after the EN-pin loop (after line 116), before the `DATA_READY output` block.
The DATA_READY block starts with:
```c
    /* DATA_READY output, start low. */
    gpio_init(BIBA_PIN_DATA_READY_GPIO);
```

Add immediately before that block:
```c
    /* SSR: output, start low (power off, safe default). */
    biba_hal_ssr_init();
```

---

### `firmware/src/modes/mode_standalone.c` (modify — wire ramp + SSR)

**Analog:** existing arm/disarm edge handlers and motor drive section in same file.

#### Insertion Point 1 — file-scope static declarations + `biba_mode_standalone_init()`

**Analog:** existing static state variables (lines 32-106):
```c
static biba_failsafe_t s_crsf_failsafe;
static biba_crsf_link_stats_t s_link;
static uint16_t s_channels[CRSF_RC_CHANNEL_COUNT];
/* ... more statics ... */
static bool s_trim_mode_active;
static float s_saved_motor_trim;
```

**Add after existing static declarations (before `update_rgb_led`):**
```c
/* Output ramping — one state per motor (D-01, D-03) */
static biba_ramp_t s_ramp_left;
static biba_ramp_t s_ramp_right;
```

**Add `#include "app/ramp.h"` to the include block** (line ~20, after `"app/failsafe.h"`):
```c
#include "app/failsafe.h"
#include "app/ramp.h"          /* add this line */
#include "app/telemetry.h"
```

**Analog:** existing `biba_mode_standalone_init()` body (lines 157-164):
```c
void biba_mode_standalone_init(void)
{
    biba_hal_crsf_begin(BIBA_CRSF_BAUD);
    biba_failsafe_init(&s_crsf_failsafe, BIBA_CRSF_TIMEOUT_MS);
    biba_pid_reset(&s_heading_pid);
    s_last_tick_ms = biba_hal_now_ms();
    biba_bts7960_set_enabled(true);

    /* Suppress failsafe melody on the very first tick (no RC lock-in yet). */
    s_last_failsafe = true;

    /* Play startup fanfare through motor coils. */
    biba_melody_player_start(&s_player, &biba_melody_startup);
}
```

**Add two ramp init calls inside `biba_mode_standalone_init()` body**, after
`biba_bts7960_set_enabled(true)`:
```c
    biba_bts7960_set_enabled(true);
    biba_ramp_init(&s_ramp_left);   /* add */
    biba_ramp_init(&s_ramp_right);  /* add */
```

> `biba_hal_ssr_init()` is called from `biba_hal_init()` (which runs before
> `biba_mode_standalone_init()`), so SSR is already LOW on entry here — no
> explicit `biba_hal_ssr_set(false)` needed in init.

---

#### Insertion Point 2 — arm/disarm/failsafe edge handlers

**Analog:** existing edge handlers (lines 237-251):
```c
    /* Failsafe rising edge: play warning (distinct from normal disarm). */
    if (failsafe && !s_last_failsafe) {
        biba_melody_player_start(&s_player, &biba_melody_failsafe);
    }
    s_last_failsafe = failsafe;

    if (armed && !s_armed) {
        printf("[biba] ARMED\r\n");
        biba_melody_player_start(&s_player, &biba_melody_arm);
    } else if (!armed && s_armed) {
        printf("[biba] DISARMED\r\n");
        biba_pid_reset(&s_heading_pid);
        if (!failsafe) {   /* failsafe already started its own melody */
            biba_melody_player_start(&s_player, &biba_melody_disarm);
        }
        /* Exit trim mode on disarm edge (safety) */
        s_trim_mode_active = false;
    }
    s_armed = armed;
```

**Modified section** (insert ramp_reset + SSR calls on edges):
```c
    /* Failsafe rising edge: play warning (distinct from normal disarm). */
    if (failsafe && !s_last_failsafe) {
        biba_melody_player_start(&s_player, &biba_melody_failsafe);
        biba_ramp_reset(&s_ramp_left);       /* D-04: hard reset on failsafe */
        biba_ramp_reset(&s_ramp_right);
        biba_hal_ssr_set(false);             /* D-10: SSR LOW on failsafe */
    }
    s_last_failsafe = failsafe;

    if (armed && !s_armed) {
        printf("[biba] ARMED\r\n");
        biba_melody_player_start(&s_player, &biba_melody_arm);
        biba_hal_ssr_set(true);              /* D-10: SSR HIGH on arm (D-12: no delay) */
    } else if (!armed && s_armed) {
        printf("[biba] DISARMED\r\n");
        biba_pid_reset(&s_heading_pid);
        biba_ramp_reset(&s_ramp_left);       /* D-04: hard reset on disarm */
        biba_ramp_reset(&s_ramp_right);
        biba_hal_ssr_set(false);             /* D-10: SSR LOW on disarm */
        if (!failsafe) {   /* failsafe already started its own melody */
            biba_melody_player_start(&s_player, &biba_melody_disarm);
        }
        /* Exit trim mode on disarm edge (safety) */
        s_trim_mode_active = false;
    }
    s_armed = armed;
```

> **Pitfall — melody-gate ordering (RESEARCH.md):** `biba_hal_ssr_set(false)`
> on failsafe must be called **inside** `if (failsafe && !s_last_failsafe)`,
> i.e., BEFORE `s_last_failsafe = failsafe`. If placed after, the gate fires
> only once on the rising edge — correct. If the SSR call were placed outside
> this block it would run every tick while failsafe is active, wasting cycles
> and re-toggling GPIO unnecessarily.
>
> **Pitfall — double edge on failsafe + disarm:** When failsafe is active,
> `armed` is already false (because `armed = (!failsafe) && ...`). So the
> `!armed && s_armed` disarm edge may also fire on the same tick as the
> failsafe edge. The failsafe branch already calls `ramp_reset` and
> `biba_hal_ssr_set(false)`, so the disarm branch calling them again is
> harmless but redundant. Keep both for clarity.

---

#### Insertion Point 3 — post-mix ramp application + motor drive

**Analog:** existing motor drive section (approximately lines 440-448):
```c
    /* Drive motors only when audio is not occupying the PWM hardware. */
    if (!s_player.active) {
        biba_bts7960_drive(left_out, right_out);
    }
```

**What `left_out` / `right_out` look like before this point** (lines 350-395):
```c
    float left_out = 0.0f, right_out = 0.0f;
    bool left_limited = false, right_limited = false;

    if (armed) {
        biba_mix_output_t mix = biba_mix_differential(throttle, steering);
        /* ... current limits, trim ... */
        left_out  = out.left;
        right_out = out.right;
        /* Apply trim ... */
    }
```

**Modified drive section** — apply ramp post-mix, then drive (D-03, D-05):
```c
    /* Apply output ramping (D-03: post-mix, D-05: always runs). */
    left_out  = biba_ramp_update(&s_ramp_left,  left_out,  dt);
    right_out = biba_ramp_update(&s_ramp_right, right_out, dt);

    /* If actively driving, motors are needed — interrupt melodies. ... */
    bool control_active = armed &&
        ((throttle > BIBA_MOTOR_DEADBAND  || throttle < -BIBA_MOTOR_DEADBAND) || ...
```

> **Pitfall — `going_reverse` uses post-ramp values:** The `going_reverse`
> check at line 407 tests `left_out < -BIBA_MOTOR_DEADBAND`. After ramp is
> inserted, `left_out` and `right_out` are the **ramped** values, which is
> correct — the backup pip should reflect actual motor output, not the
> pre-ramp target. No change needed to the `going_reverse` logic.

> **Pitfall — disarmed ramp target is 0.0f:** When disarmed, `left_out` and
> `right_out` are initialised to `0.0f` (the `if (armed)` block is skipped).
> `biba_ramp_update(..., 0.0f, dt)` will decelerate toward zero, but per D-04
> the ramp state is hard-reset to zero on the disarm edge — so on first tick
> after disarm the ramp is already at zero and `update(0.0f, dt)` returns 0.0f
> immediately. Correct.

---

## Shared Patterns

### NULL-guard on pointer args
**Source:** `firmware/src/app/failsafe.c` lines 6-8
**Apply to:** All functions in `ramp.c` that take `biba_ramp_t *`
```c
if (fs == NULL) return;   /* or: return false / return 0.0f */
```

### `#ifndef` config guard block
**Source:** `firmware/include/biba_config.h` lines 22-30
**Apply to:** All four new `BIBA_RAMP_*` constants in `biba_config.h`
```c
#ifndef BIBA_RAMP_ACCEL_RATE
#  define BIBA_RAMP_ACCEL_RATE  2.0f
#endif
```

### GPIO init/set_dir/put triple
**Source:** `firmware/src/hal/biba_hal_rp2040.c` lines 107-116 (EN-pin loop)
**Apply to:** `biba_hal_ssr_init()` in `biba_hal_rp2040.c`
```c
gpio_init(PIN);
gpio_set_dir(PIN, GPIO_OUT);
gpio_put(PIN, 0);
```

### Test file structure
**Source:** `firmware/test/test_control_loop/test_main.c` lines 186-200
**Apply to:** `firmware/test/test_ramp/test_main.c`
```c
static void run_all(void) {
    RUN_TEST(test_foo);
    /* ... */
}
#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
```

### `extern "C"` wrapper in headers
**Source:** `firmware/src/app/failsafe.h` lines 13-15 and 37-39
**Apply to:** `ramp.h`
```c
#ifdef __cplusplus
extern "C" {
#endif
/* ... declarations ... */
#ifdef __cplusplus
}
#endif
```

---

## Pitfalls Summary (from RESEARCH.md)

| # | File | Pitfall | Mitigation |
|---|------|---------|------------|
| P1 | ramp.c | `dt = 0.0f` on first tick | Guard: `if (dt <= 0.0f) return r->current;` |
| P2 | ramp.c | Direction change — Python uses `_decel_toward_zero()` helper | Inline the helper; set `hold_remaining_s` immediately when `abs_cur <= max_step` |
| P3 | mode_standalone.c | `going_reverse` checks `left_out` — must use post-ramp value | Insert ramp calls BEFORE the `going_reverse` / `control_active` checks |
| P4 | mode_standalone.c | Failsafe + disarm both fire on same tick | Both branches call `ramp_reset` + `ssr_set(false)` — idempotent, harmless |
| P5 | mode_standalone.c | Melody-gate ordering: SSR set inside `!s_last_failsafe` guard | Confirmed: SSR call goes INSIDE `if (failsafe && !s_last_failsafe)`, before `s_last_failsafe = failsafe` |
| P6 | biba_hal.c | `biba_hal_ssr_init/set` linked for all STM32 envs | Add no-op stubs; do NOT use `#ifdef RPICO` (violates D-00c) |
| P7 | biba_config.h | `BIBA_RAMP_ZERO_HOLD_MS` is `uint` literal (`u` suffix) | `150u` not `150` — consistent with other `_MS` defines in the file |
| P8 | ramp.c | `bool` not available without `<stdbool.h>` | Include via `ramp.h` → `#include <stdbool.h>` in the header |

---

## No Analog Found

None — every new/modified file has an exact or role-match analog in the
existing codebase.

---

## Metadata

**Analog search scope:** `firmware/src/app/`, `firmware/src/hal/`,
`firmware/src/modes/`, `firmware/include/`, `firmware/targets/RPICO_RP2040/`,
`firmware/test/test_control_loop/`, `firmware/test/test_crsf/`
**Files read:** 13 source files + platformio.ini
**Pattern extraction date:** 2026-05-14
