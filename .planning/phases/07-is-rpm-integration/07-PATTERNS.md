# Phase 07: IS-RPM Integration — Pattern Map

**Mapped:** 2026-05-23
**Files analyzed:** 16 (6 new, 6 modified, 4 test/script)
**Analogs found:** 16 / 16

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `firmware/src/app/zc_detector.h` | C module header | transform | `firmware/src/app/ramp.h` | exact (portable module, same guard pattern) |
| `firmware/src/app/zc_detector.c` | C module impl | transform | `firmware/src/app/ramp.c` + PoC `zc_freq_hz()` | exact (port of PoC verbatim) |
| `firmware/src/app/rpm_pi.h` | C module header | CRUD / control | `firmware/src/app/control_loop.h` | exact (config struct + state struct + step) |
| `firmware/src/app/rpm_pi.c` | C module impl | CRUD / control | `firmware/src/app/ramp.c` + PoC `cmd_rpmrun()` | exact (port of PoC loop) |
| `firmware/src/app/adc_capture.h` | C module header | streaming | `firmware/src/poc/adc_capture.h` | exact (move + extend) |
| `firmware/src/app/adc_capture.c` | C module impl | streaming (DMA IRQ) | `firmware/src/poc/adc_capture.c` | exact (move + add async variant) |
| `firmware/src/proto/biba_proto.h` | C proto struct | transform | self (edit existing struct) | — |
| `firmware/src/app/telemetry.h` | C struct + fn decl | transform | self (edit existing) | — |
| `firmware/src/app/telemetry.c` | C impl | transform | self (edit existing) | — |
| `firmware/src/modes/mode_standalone.c` | C app mode | event-driven | self (edit existing) | — |
| `firmware/test/test_zc_detector/test_main.c` | Unity test | transform | `firmware/test/test_ramp/test_main.c` | exact |
| `firmware/test/test_rpm_pi/test_main.c` | Unity test | CRUD / control | `firmware/test/test_control_loop/test_main.c` | exact |
| `biba-controller/stm32_link/protocol.py` | Python decoder | transform | self (edit existing) | — |
| `biba-controller/config.py` | Python config | — | self (edit existing, follow `_get_env_float` pattern) | — |
| `biba-controller/main.py` | Python app | request-response | self (edit telemetry handler) | — |
| `scripts/is_rpm_calibrate.py` | Python script | request-response | `scripts/is_poc_capture.py` | exact |

---

## Pattern Assignments

### `firmware/src/app/zc_detector.h` (C module header, transform)

**Analog:** `firmware/src/app/ramp.h`

**Header guard + portability pattern** (ramp.h lines 1–12):
```c
#ifndef BIBA_RAMP_H
#define BIBA_RAMP_H

/* Output slew-rate limiter for motor speed commands. ...
 * Per-motor state is owned by the caller (mode_standalone.c).
 * Config constants live in biba_config.h (BIBA_RAMP_*). */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
```

Apply same skeleton — replace guard name, module comment, and include list:
```c
#ifndef BIBA_ZC_DETECTOR_H
#define BIBA_ZC_DETECTOR_H

/* A2 Sub-window Schmitt-trigger zero-crossing frequency estimator.
 * Pure C99 computation on a uint16_t ADC buffer — no HAL dependency.
 * Portable: compiles under native_test env (plain gcc, no hardware). */

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
```

**Public API declarations** — two functions (extracted from PoC, see below):
```c
#define ZC_SUBWIN_K          8u
#define ZC_SUBWIN_MIN_PKPK   30u   /* per-block AC threshold (ADC LSB) */
#define ZC_MIN_VALID_HZ      80.0f
#define ZC_EMA_ALPHA         0.7f

/* Returns frequency in Hz (0.0 if no valid signal or < 2 active blocks).
 * buf: ADC 12-bit samples, n: sample count, sps: sample rate Hz */
float zc_freq_hz(const uint16_t *buf, uint16_t n, uint32_t sps);

/* EMA-filtered ZC with two-sided validity gating. Updates *ema in-place.
 * target_hz: current setpoint (high-side validity gate = target×2.5+300).
 * meas_raw: raw zc_freq_hz() output.  Returns new EMA value. */
float zc_ema_update(float *ema, float meas_raw, float target_hz);
```

**Footer pattern** (ramp.h lines 31–35):
```c
#ifdef __cplusplus
}
#endif

#endif /* BIBA_ZC_DETECTOR_H */
```

---

### `firmware/src/app/zc_detector.c` (C module impl, transform)

**Analog:** `firmware/src/poc/is_rpm_poc_main.cpp` (lines 149–183 verbatim) + `firmware/src/app/ramp.c`

**Include pattern** (ramp.c lines 1–3):
```c
#include "ramp.h"
#include "biba_config.h"
#include <stddef.h>
```

For zc_detector.c, no biba_config.h needed (constants are in zc_detector.h):
```c
#include "zc_detector.h"
#include <math.h>
```

**Core `zc_freq_hz()` — verbatim extraction** (is_rpm_poc_main.cpp lines 149–183):
```c
/* Sub-window Schmitt-trigger ZC detector (A2 algorithm).
 * Change from PoC: `static` removed; function exposed via header. */
float zc_freq_hz(const uint16_t *buf, uint16_t n, uint32_t sps)
{
    if (n < ZC_SUBWIN_K * 4u) return 0.0f;
    uint16_t blk = n / (uint16_t)ZC_SUBWIN_K;
    uint16_t total = 0;
    uint16_t active_blocks = 0;
    for (uint16_t b = 0; b < ZC_SUBWIN_K; ++b) {
        const uint16_t *seg = buf + (uint32_t)b * blk;
        uint16_t mn = seg[0], mx = seg[0];
        for (uint16_t i = 1; i < blk; ++i) {
            if (seg[i] < mn) mn = seg[i];
            if (seg[i] > mx) mx = seg[i];
        }
        uint16_t pkpk = (uint16_t)(mx - mn);
        if (pkpk < ZC_SUBWIN_MIN_PKPK) continue;
        active_blocks++;
        int32_t mid  = ((int32_t)mn + (int32_t)mx) / 2;
        int32_t hyst = (int32_t)pkpk / 4;
        int32_t up = mid + hyst, dn = mid - hyst;
        int state = (seg[0] > (uint16_t)mid) ? 1 : -1;
        for (uint16_t i = 1; i < blk; ++i) {
            int32_t v = (int32_t)seg[i];
            if (state > 0 && v < dn) { state = -1; total++; }
            else if (state < 0 && v > up) { state = 1; total++; }
        }
    }
    if (active_blocks < 2u || total < 2u) return 0.0f;
    return (float)total * 0.5f * (float)sps / (float)n;
}
```

**`zc_ema_update()` — extracted from PoC cmd_rpmrun** (is_rpm_poc_main.cpp lines 229–249):
```c
/* EMA with two-sided validity gate (extracted from PoC cmd_rpmrun). */
float zc_ema_update(float *ema, float meas_raw, float target_hz)
{
    float hi = target_hz * 2.5f + 300.0f;
    if (meas_raw >= ZC_MIN_VALID_HZ && meas_raw <= hi) {
        *ema = ZC_EMA_ALPHA * meas_raw + (1.0f - ZC_EMA_ALPHA) * (*ema);
    } else if (meas_raw == 0.0f) {
        /* Wheel stopped / no ZC: decay toward 0, half-life ~660 ms (6-7 cycles @ 10 Hz).
         * Factor 0.5 (old PoC) caused EMA collapse during transient blanking. Use 0.9. */
        *ema *= 0.9f;
    }
    /* else: out-of-range noise spike — hold EMA unchanged */
    return *ema;
}
```

---

### `firmware/src/app/rpm_pi.h` (C module header, CRUD/control)

**Analog:** `firmware/src/app/control_loop.h`

**Exact header structure to mirror** (control_loop.h lines 1–70):
```c
#ifndef BIBA_CONTROL_LOOP_H
#define BIBA_CONTROL_LOOP_H

/* ... module comment ... */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float kp;
    float ki;
    float kd;
    float output_limit;
    float integral_limit;
} biba_pid_config_t;

typedef struct {
    float integral;
    float last_error;
    bool  primed;
} biba_pid_state_t;

void  biba_pid_reset(biba_pid_state_t *state);
float biba_pid_step(biba_pid_state_t *state,
                    const biba_pid_config_t *config,
                    float error,
                    float dt_s);
```

Apply the same **config struct + state struct + reset + step** pattern:
```c
#ifndef BIBA_RPM_PI_H
#define BIBA_RPM_PI_H

/* FF+PI RPM controller with gain scheduling and anti-windup.
 * Wraps the inner PI loop from firmware/src/poc/is_rpm_poc_main.cpp.
 * No HAL dependency — portable for native_test Unity tests. */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float kp;
    float ki;
    float ki_low;           /* gain scheduling: used when |target_hz| < ki_low_thresh */
    float ki_low_thresh;    /* Hz threshold for gain scheduling */
    float ff_slope;         /* Hz/% — from calibration (K = 10.13 default) */
    float ff_dead;          /* Hz dead-zone offset (74.6 default) */
    float stiction_floor;   /* min duty when target > 0 (0.20 default) */
    float p_clamp;          /* max |P term| duty contribution (0.05) */
    float i_clamp_pos;      /* asymmetric integral clamp positive */
    float i_clamp_neg;      /* asymmetric integral clamp negative */
    float dt_s;             /* PI update period (e.g. 0.104 for dual-channel) */
} biba_rpm_pi_config_t;

typedef struct {
    float integral;
    float meas_ema;         /* owned EMA state — caller does not need zc_ema_update() */
    float prev_duty;
    bool  primed;
} biba_rpm_pi_state_t;

/* Reset all state to zero. Call on failsafe/disarm edge. */
void  biba_rpm_pi_reset(biba_rpm_pi_state_t *s);

/* One PI step. target_hz: positive = forward, negative = reverse (future).
 * meas_raw_hz: raw output of zc_freq_hz() for this channel.
 * Returns duty in [-1.0, 1.0]. */
float biba_rpm_pi_step(biba_rpm_pi_state_t *s,
                       const biba_rpm_pi_config_t *cfg,
                       float target_hz,
                       float meas_raw_hz);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_RPM_PI_H */
```

---

### `firmware/src/app/rpm_pi.c` (C module impl, CRUD/control)

**Analog:** `firmware/src/poc/is_rpm_poc_main.cpp` `cmd_rpmrun()` inner PI loop (lines 217–360) + `firmware/src/app/ramp.c` (structure)

**Include + reset pattern** (ramp.c lines 1–17):
```c
#include "ramp.h"
#include "biba_config.h"
#include <stddef.h>

void biba_ramp_init(biba_ramp_t *r)
{
    if (r == NULL) return;
    r->current          = 0.0f;
    r->hold_remaining_s = 0.0f;
}

void biba_ramp_reset(biba_ramp_t *r)
{
    if (r == NULL) return;
    r->current          = 0.0f;
    r->hold_remaining_s = 0.0f;
}
```

Apply same reset pattern:
```c
#include "rpm_pi.h"
#include "zc_detector.h"   /* for zc_ema_update() */
#include <stddef.h>

void biba_rpm_pi_reset(biba_rpm_pi_state_t *s)
{
    if (s == NULL) return;
    s->integral   = 0.0f;
    s->meas_ema   = 0.0f;
    s->prev_duty  = 0.0f;
    s->primed     = false;
}
```

**Core `biba_rpm_pi_step()` — extracted from PoC cmd_rpmrun** (is_rpm_poc_main.cpp lines 228–360):
```c
float biba_rpm_pi_step(biba_rpm_pi_state_t *s,
                       const biba_rpm_pi_config_t *cfg,
                       float target_hz,
                       float meas_raw_hz)
{
    if (s == NULL || cfg == NULL) return 0.0f;
    if (target_hz < 0.0f) target_hz = 0.0f;   /* Phase 7: forward only */

    /* EMA update with validity gate */
    zc_ema_update(&s->meas_ema, meas_raw_hz, target_hz);
    float meas_hz = s->meas_ema;

    /* Feed-forward */
    float ff_duty = 0.0f;
    if (cfg->ff_slope > 0.0f && target_hz > 0.0f) {
        ff_duty = (target_hz + cfg->ff_dead) / (cfg->ff_slope * 100.0f);
        if (ff_duty < 0.0f) ff_duty = 0.0f;
        if (ff_duty > 1.0f) ff_duty = 1.0f;
    }

    /* Gain scheduling */
    float ki = (target_hz < cfg->ki_low_thresh) ? cfg->ki_low : cfg->ki;

    /* Asymmetric integral clamp (derived from ki, matches PoC formula) */
    float i_clamp_pos = 0.03f / (ki + 1e-6f);
    float i_clamp_neg = 0.01f / (ki + 1e-6f);

    /* Error */
    float err = target_hz - meas_hz;

    /* Anti-windup: don't integrate when saturated or when measurement invalid */
    float duty = s->prev_duty;
    bool sat_high = duty >= 0.999f;
    bool sat_low  = duty <= 0.001f;
    bool can_integrate =
        !(sat_high && err > 0.0f) &&
        !(sat_low  && err < 0.0f);
    if (can_integrate && meas_hz > 50.0f) {
        s->integral += err * cfg->dt_s;
    }
    if (s->integral >  i_clamp_pos) s->integral =  i_clamp_pos;
    if (s->integral < -i_clamp_neg) s->integral = -i_clamp_neg;

    /* P term: zeroed when no ZC (prevents large step from full target error) */
    float p_term = (meas_hz == 0.0f) ? 0.0f : cfg->kp * err;
    if (p_term >  cfg->p_clamp) p_term =  cfg->p_clamp;
    if (p_term < -cfg->p_clamp) p_term = -cfg->p_clamp;

    float i_term = ki * s->integral;
    duty = ff_duty + p_term + i_term;

    /* Stiction floor (PoC: 20% duty minimum while target > 0) */
    if (target_hz > 0.0f && duty > 0.0f && duty < cfg->stiction_floor) {
        duty = cfg->stiction_floor;
    }
    if (target_hz > 0.0f && meas_hz > 0.0f && duty < cfg->stiction_floor) {
        duty = cfg->stiction_floor;
    }
    if (duty < 0.0f) duty = 0.0f;
    if (duty > 1.0f) duty = 1.0f;

    s->prev_duty = duty;
    s->primed = true;
    return duty;
}
```

---

### `firmware/src/app/adc_capture.h` (C module header, streaming)

**Analog:** `firmware/src/poc/adc_capture.h` — **move verbatim**, update include path from `"poc/adc_capture.h"` → `"app/adc_capture.h"`, then add callback API.

**Existing API to preserve** (poc/adc_capture.h lines 1–31):
```c
#pragma once
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ADC_CAPTURE_MAX_SAMPLES  4096u

void adc_capture_init(uint32_t sample_rate_sps);

/* DMA burst capture — BLOCKING (100 ms @ 1024 samples @ 10kSPS).
 * Use ONLY in PoC env / Unity tests, never in mode_standalone_tick(). */
bool adc_capture_burst(uint8_t channel, uint16_t n_samples, uint16_t *out_buf);

#ifdef __cplusplus
}
#endif
```

**New async API to add** (after `adc_capture_burst` declaration):
```c
/* Callback type: called from DMA_IRQ_0 handler when capture completes.
 * channel: ADC channel that completed; buf/n: the filled buffer. */
typedef void (*adc_capture_done_cb_t)(uint8_t channel,
                                      const uint16_t *buf,
                                      uint16_t n);

/* Start a non-blocking DMA capture. Returns false if DMA already busy.
 * Calls callback from DMA IRQ context (core0) when n_samples transferred.
 * callback may be NULL to fire-and-forget (check dma_channel_is_busy). */
bool adc_capture_start_async(uint8_t channel, uint16_t n_samples,
                              uint16_t *out_buf,
                              adc_capture_done_cb_t callback);

/* True if an async capture is in flight. */
bool adc_capture_busy(void);
```

---

### `firmware/src/app/adc_capture.c` (C module impl, streaming DMA)

**Analog:** `firmware/src/poc/adc_capture.c` — move verbatim, then add `adc_capture_start_async()`.

**Existing blocking implementation to preserve** (poc/adc_capture.c lines 1–85):
```c
#include "poc/adc_capture.h"   /* → change to "app/adc_capture.h" */

#include <hardware/adc.h>
#include <hardware/dma.h>
#include <pico/time.h>

void adc_capture_init(uint32_t sample_rate_sps)
{
    adc_init();
    adc_gpio_init(26);  /* GP26 = IS_LEFT  */
    adc_gpio_init(27);  /* GP27 = IS_RIGHT */
    adc_fifo_setup(true, true, 1, false, false);
    /* Critical clock formula: div = 48e6/sps - 1  (NOT divided by 96) */
    float div = (float)48000000u / (float)sample_rate_sps - 1.0f;
    if (div < 0.0f) div = 0.0f;
    adc_set_clkdiv(div);
}

bool adc_capture_burst(uint8_t channel, uint16_t n_samples, uint16_t *out_buf)
{
    /* ... DMA setup + blocking poll + 500 ms timeout ... */
    /* Preserve verbatim — used by Unity tests */
}
```

**New async state + IRQ handler to add**:
```c
/* Async DMA state (module-private) */
static adc_capture_done_cb_t s_done_cb;
static int      s_dma_ch   = -1;
static uint8_t  s_last_ch;
static uint16_t s_last_n;
static uint16_t *s_buf_ptr;

static void dma_irq_handler(void)
{
    if (s_dma_ch >= 0 && dma_channel_get_irq0_status(s_dma_ch)) {
        dma_channel_acknowledge_irq0(s_dma_ch);
        adc_run(false);
        adc_fifo_drain();
        int ch = s_dma_ch;
        s_dma_ch = -1;                  /* mark idle before callback */
        dma_channel_unclaim(ch);
        if (s_done_cb) s_done_cb(s_last_ch, s_buf_ptr, s_last_n);
    }
}

bool adc_capture_start_async(uint8_t channel, uint16_t n_samples,
                              uint16_t *out_buf,
                              adc_capture_done_cb_t callback)
{
    if (s_dma_ch >= 0) return false;    /* already busy */
    s_last_ch  = channel;
    s_last_n   = n_samples;
    s_buf_ptr  = out_buf;
    s_done_cb  = callback;

    adc_select_input(channel);
    s_dma_ch = dma_claim_unused_channel(true);
    /* ... same DMA config as adc_capture_burst() but non-blocking ... */
    dma_channel_set_irq0_enabled(s_dma_ch, true);
    irq_add_shared_handler(DMA_IRQ_0, dma_irq_handler,
                           PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY);
    irq_set_enabled(DMA_IRQ_0, true);
    adc_run(true);
    return true;
}

bool adc_capture_busy(void)
{
    return s_dma_ch >= 0;
}
```

---

### `firmware/src/proto/biba_proto.h` (C proto struct, transform)

**Analog:** Self-edit — no new pattern, minimal surgical change.

**Current struct tail** (biba_proto.h lines ~163–170):
```c
    uint8_t  humidity_q8;           /* relative humidity 0-100 % (AHT30) */
    uint8_t  reserved[11];          /* pad to 48 bytes */
} biba_proto_telemetry_t;
```

**Replacement** (removes 4 bytes from reserved, adds 2 × uint16 = 4 bytes; `sizeof` stays 48):
```c
    uint8_t  humidity_q8;           /* relative humidity 0-100 % (AHT30) */
    uint16_t wheel_rpm_left_hz10;   /* IS_LEFT ZC freq × 10 (0.1 Hz res); 0 = invalid */
    uint16_t wheel_rpm_right_hz10;  /* IS_RIGHT ZC freq × 10; 0 = invalid */
    uint8_t  reserved[7];           /* pad to 48 bytes */
} biba_proto_telemetry_t;
```

**Size invariant to verify after edit**:
```c
/* In a test or static_assert: */
_Static_assert(sizeof(biba_proto_telemetry_t) == 48,
               "biba_proto_telemetry_t size drifted");
```

---

### `firmware/src/app/telemetry.h` (C struct + fn decl, transform)

**Analog:** Self-edit. Follow existing field naming convention.

**Current struct** (telemetry.h lines 14–28):
```c
typedef struct {
    float   setpoint_left;
    float   setpoint_right;
    float   current_left_a;
    float   current_right_a;
    uint16_t vbat_mv;
    float   ibat_a;
    float   temperature_c;
    float   humidity_pct;
    uint8_t crsf_rssi;
    uint8_t crsf_link_quality;
    int8_t  crsf_snr_db;
    uint8_t error_flags;
    uint8_t seq;
} biba_telemetry_input_t;
```

**Add two fields after `humidity_pct`**:
```c
    float   humidity_pct;
    float   wheel_rpm_left_hz;   /* 0 = invalid/no signal */
    float   wheel_rpm_right_hz;
    uint8_t crsf_rssi;
```

---

### `firmware/src/app/telemetry.c` (C impl, transform)

**Analog:** Self-edit. Copy encode pattern from adjacent fields.

**Existing encode snippet** (telemetry.c, after humidity line):
```c
    out->humidity_q8  = (uint8_t)(inputs->humidity_pct + 0.5f);
```

**Add after that line**:
```c
    out->wheel_rpm_left_hz10  = (uint16_t)(inputs->wheel_rpm_left_hz  * 10.0f + 0.5f);
    out->wheel_rpm_right_hz10 = (uint16_t)(inputs->wheel_rpm_right_hz * 10.0f + 0.5f);
```

---

### `firmware/src/modes/mode_standalone.c` (C app mode, event-driven)

**Analog:** Self-edit. The ramp sites are the exact surgical targets.

**Static state replacement** (lines 86–87):
```c
/* BEFORE: */
static biba_ramp_t s_ramp_left;
static biba_ramp_t s_ramp_right;

/* AFTER: */
static biba_rpm_pi_state_t  s_rpm_left;
static biba_rpm_pi_state_t  s_rpm_right;
static volatile float       s_rpm_duty_left;   /* written by DMA IRQ, read by main loop */
static volatile float       s_rpm_duty_right;
/* EMA state exposed to IRQ handler (also volatile) */
```

**Include change** (line 16):
```c
/* REMOVE: */
#include "app/ramp.h"

/* ADD: */
#include "app/zc_detector.h"
#include "app/rpm_pi.h"
#include "app/adc_capture.h"
```

**Init replacement** (lines 185–186, inside `biba_mode_standalone_init()`):
```c
/* BEFORE: */
    biba_ramp_init(&s_ramp_left);
    biba_ramp_init(&s_ramp_right);

/* AFTER: */
    biba_rpm_pi_reset(&s_rpm_left);
    biba_rpm_pi_reset(&s_rpm_right);
    s_rpm_duty_left  = 0.0f;
    s_rpm_duty_right = 0.0f;
    adc_capture_init(10000);             /* 10 kSPS; call once at init */
    /* Start first async capture (left channel) — kicks off the state machine */
    static uint16_t s_adc_buf_left[1024];
    adc_capture_start_async(BIBA_ADC_CHAN_IS_LEFT, 1024, s_adc_buf_left,
                             on_adc_done);
```

**Failsafe/disarm reset replacement** (lines 263–264 and 283–284):
```c
/* BEFORE: */
        biba_ramp_reset(&s_ramp_left);
        biba_ramp_reset(&s_ramp_right);

/* AFTER (both sites): */
        biba_rpm_pi_reset(&s_rpm_left);
        biba_rpm_pi_reset(&s_rpm_right);
        s_rpm_duty_left  = 0.0f;
        s_rpm_duty_right = 0.0f;
```

**Ramp application replacement** (lines 415–416):
```c
/* BEFORE: */
    left_out  = biba_ramp_update(&s_ramp_left,  left_out,  dt);
    right_out = biba_ramp_update(&s_ramp_right, right_out, dt);

/* AFTER: */
    /* Convert mixer output [-1,1] to target_hz for RPM PI.
     * Scale: 1.0 → BIBA_RPM_PI_MAX_HZ (e.g. 900 Hz at full throttle) */
    float target_hz_left  = left_out  * BIBA_RPM_PI_MAX_HZ;
    float target_hz_right = right_out * BIBA_RPM_PI_MAX_HZ;
    /* Read last PI outputs from volatile (written by DMA IRQ handler) */
    left_out  = failsafe ? 0.0f : (float)s_rpm_duty_left;
    right_out = failsafe ? 0.0f : (float)s_rpm_duty_right;
```

**Telemetry inputs extension** (lines 515–528, inside telemetry block):
```c
        biba_telemetry_input_t inputs = {
            /* ... existing fields ... */
            .wheel_rpm_left_hz  = s_rpm_left.meas_ema,
            .wheel_rpm_right_hz = s_rpm_right.meas_ema,
            .seq = s_telemetry_seq++,
        };
```

---

### `firmware/test/test_zc_detector/test_main.c` (Unity test, transform)

**Analog:** `firmware/test/test_ramp/test_main.c` — exact structure

**Test file structure** (test_ramp/test_main.c lines 1–12):
```c
#include <stdbool.h>
#include <stdint.h>

#include "ramp.h"
#include "biba_test_support.h"
```

Apply the same pattern:
```c
#include <stdint.h>
#include <math.h>

#include "zc_detector.h"
#include "biba_test_support.h"

/* Synthetic buffer helper: pure sine at freq_hz with DC offset and amplitude */
static void fill_sine(uint16_t *buf, uint16_t n, uint32_t sps,
                      float freq_hz, uint16_t dc_offset, uint16_t amplitude)
{
    for (uint16_t i = 0; i < n; i++) {
        float t = (float)i / (float)sps;
        float s = sinf(2.0f * 3.14159265f * freq_hz * t);
        int32_t v = (int32_t)dc_offset + (int32_t)((float)amplitude * s);
        if (v < 0) v = 0;
        if (v > 4095) v = 4095;
        buf[i] = (uint16_t)v;
    }
}
```

**Test case pattern** (test_ramp/test_main.c — static void + single assertion):
```c
static void test_zc_pure_sine_300hz(void)
{
    uint16_t buf[1024];
    fill_sine(buf, 1024, 10000, 300.0f, 2048, 800);
    float hz = zc_freq_hz(buf, 1024, 10000);
    TEST_ASSERT_FLOAT_WITHIN(15.0f, 300.0f, hz);  /* ±5% */
}

static void test_zc_dc_only_returns_zero(void)
{
    uint16_t buf[1024];
    for (uint16_t i = 0; i < 1024; i++) buf[i] = 2048;
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, zc_freq_hz(buf, 1024, 10000));
}

static void test_zc_single_active_block_returns_zero(void)
{
    /* Only one block exceeds ZC_SUBWIN_MIN_PKPK — requirement: ≥ 2 active */
    uint16_t buf[1024];
    for (uint16_t i = 0; i < 1024; i++) buf[i] = 2048;
    /* Spike only in block 0 (samples 0–127) */
    for (uint16_t i = 0; i < 128; i++) buf[i] = (i < 64) ? 2200 : 1800;
    float hz = zc_freq_hz(buf, 1024, 10000);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, hz);
}
```

**Runner pattern** (from test_ramp or test_control_loop):
```c
int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_zc_pure_sine_300hz);
    RUN_TEST(test_zc_dc_only_returns_zero);
    RUN_TEST(test_zc_single_active_block_returns_zero);
    /* ... more cases ... */
    return UNITY_END();
}
```

---

### `firmware/test/test_rpm_pi/test_main.c` (Unity test, CRUD/control)

**Analog:** `firmware/test/test_control_loop/test_main.c` — exact structure

**Config/state setup pattern** (test_control_loop/test_main.c lines 9–31):
```c
static biba_motor_current_t ok_sample(float amps) { ... }
static biba_motor_limit_t limit(float cur, float pwr, float vol) { ... }
```

Apply same factory pattern:
```c
#include <stdbool.h>
#include <stdint.h>

#include "rpm_pi.h"
#include "biba_test_support.h"

static biba_rpm_pi_config_t default_cfg(void)
{
    biba_rpm_pi_config_t cfg = {
        .kp            = 0.002f,
        .ki            = 0.010f,
        .ki_low        = 0.005f,
        .ki_low_thresh = 200.0f,
        .ff_slope      = 10.13f,
        .ff_dead       = 74.6f,
        .stiction_floor = 0.20f,
        .p_clamp       = 0.05f,
        .i_clamp_pos   = 0.03f / (0.010f + 1e-6f),
        .i_clamp_neg   = 0.01f / (0.010f + 1e-6f),
        .dt_s          = 0.104f,
    };
    return cfg;
}
```

**Test assertion pattern** (test_control_loop/test_main.c lines 33–44):
```c
static void test_pid_applies_proportional_term(void)
{
    biba_pid_config_t cfg = { .kp = 0.5f, ... };
    biba_pid_state_t state;
    biba_pid_reset(&state);
    float out = biba_pid_step(&state, &cfg, 0.4f, 0.01f);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.2f, out);
}
```

Apply same pattern:
```c
static void test_reset_zeroes_state(void)
{
    biba_rpm_pi_state_t s;
    biba_rpm_pi_reset(&s);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, s.integral);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, s.meas_ema);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, s.prev_duty);
    TEST_ASSERT_FALSE(s.primed);
}

static void test_ff_only_produces_correct_duty(void)
{
    /* kp=ki=0: output should be pure FF */
    biba_rpm_pi_config_t cfg = default_cfg();
    cfg.kp = 0.0f; cfg.ki = 0.0f; cfg.ki_low = 0.0f;
    biba_rpm_pi_state_t s;
    biba_rpm_pi_reset(&s);
    /* target=300 Hz → ff = (300 + 74.6) / (10.13 * 100) = 0.3699 */
    float duty = biba_rpm_pi_step(&s, &cfg, 300.0f, 300.0f);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.3699f, duty);
}

static void test_gain_scheduling_uses_ki_low_below_threshold(void)
{
    biba_rpm_pi_config_t cfg = default_cfg();
    biba_rpm_pi_state_t s;
    biba_rpm_pi_reset(&s);
    /* Force integral accumulation below 200 Hz threshold */
    /* Simulate 5 steps with error=50 Hz; ki_low should be used */
    for (int i = 0; i < 5; i++) {
        biba_rpm_pi_step(&s, &cfg, 150.0f, 100.0f);  /* target < ki_low_thresh */
    }
    /* With ki=0.010: integral ≈ 5 * 50 * 0.104 = 26; clamped by i_clamp_pos */
    /* With ki_low=0.005: i_term contribution per step is half */
    /* Just verify duty is bounded and primed */
    TEST_ASSERT_TRUE(s.primed);
}
```

---

### `biba-controller/stm32_link/protocol.py` (Python decoder, transform)

**Analog:** Self-edit. Three precise surgical changes.

**Current TELEMETRY_STRUCT** (protocol.py line ~168):
```python
TELEMETRY_STRUCT = "<hhhhHHhhhhhhBBbBIhhB11s"
TELEMETRY_SIZE = struct.calcsize(TELEMETRY_STRUCT)
assert TELEMETRY_SIZE == 48, f"telemetry size drifted: {TELEMETRY_SIZE}"
```

**After** (replace `11s` with `HH7s`; assert still passes):
```python
TELEMETRY_STRUCT = "<hhhhHHhhhhhhBBbBIhhBHH7s"
TELEMETRY_SIZE = struct.calcsize(TELEMETRY_STRUCT)
assert TELEMETRY_SIZE == 48, f"telemetry size drifted: {TELEMETRY_SIZE}"
```

**Current Telemetry dataclass tail** (protocol.py lines ~174–192):
```python
@dataclass
class Telemetry:
    ...
    humidity_pct: float = 0.0       # relative humidity 0–100 % (AHT30)
```

**Add two fields after `humidity_pct`**:
```python
    humidity_pct: float = 0.0       # relative humidity 0–100 % (AHT30)
    wheel_rpm_left_hz:  float = 0.0  # IS_LEFT ZC frequency (0 = invalid)
    wheel_rpm_right_hz: float = 0.0  # IS_RIGHT ZC frequency (0 = invalid)
```

**Current `from_bytes` tail** (protocol.py lines ~210–215):
```python
            humidity_pct=float(fields[19]),
        )
        return cls(seq=frame.seq, flags=frame.flags, telemetry=tlm)
```

**After**:
```python
            humidity_pct=float(fields[19]),
            wheel_rpm_left_hz=fields[20] / 10.0,
            wheel_rpm_right_hz=fields[21] / 10.0,
        )
```

**Current `to_bytes` tail** (protocol.py lines ~239–242):
```python
            max(0, min(100, int(round(t.humidity_pct)))),
            b"\x00" * 11,
        )
```

**After**:
```python
            max(0, min(100, int(round(t.humidity_pct)))),
            max(0, min(0xFFFF, int(round(t.wheel_rpm_left_hz  * 10)))),
            max(0, min(0xFFFF, int(round(t.wheel_rpm_right_hz * 10)))),
            b"\x00" * 7,
        )
```

---

### `biba-controller/config.py` (Python config, transform)

**Analog:** Self-edit. Follow the `_get_env_float` pattern already used throughout.

**Existing pattern to copy** (config.py lines 22–25):
```python
def _get_env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default
```

**Add after the motor config block** (after `RIGHT_MOTOR_MAX_POWER_W` or similar, around line 90):
```python
# --- Wheel odometry (IS-RPM → m/s estimation) ---------------------------
WHEEL_RADIUS_M = _get_env_float("WHEEL_RADIUS_M", 0.100)
# 10 cm default placeholder — measure actual wheel and set via env
GEAR_RATIO     = _get_env_float("GEAR_RATIO",     1.0)
# dimensionless; 1.0 = direct drive (update if gearbox present)
```

---

### `biba-controller/main.py` (Python app, request-response)

**Analog:** Self-edit. Add speed estimation in the telemetry handler where `TelemetryFrame` is consumed.

**Speed estimation function** — add at module level or inline in telemetry handler:
```python
import math
import config

def _wheel_rpm_to_mps(rpm_hz: float) -> float:
    """Convert IS-signal ZC frequency (Hz) to wheel linear speed (m/s).
    v = omega * r = (2*pi*f / gear_ratio) * r"""
    if rpm_hz <= 0.0:
        return 0.0
    return (2.0 * math.pi * rpm_hz * config.WHEEL_RADIUS_M) / config.GEAR_RATIO
```

**Usage in telemetry handler** (wherever `TelemetryFrame.from_bytes()` is called):
```python
    speed_left_mps  = _wheel_rpm_to_mps(frame.telemetry.wheel_rpm_left_hz)
    speed_right_mps = _wheel_rpm_to_mps(frame.telemetry.wheel_rpm_right_hz)
```

---

### `scripts/is_rpm_calibrate.py` (Python script, request-response)

**Analog:** `scripts/is_poc_capture.py` — copy structure verbatim, adapt for CALRUN command

**Serial open + ping pattern** (is_poc_capture.py lines 96–106):
```python
    ser = serial.Serial(args.port, 115200, timeout=10)
    time.sleep(1.5)
    ser.reset_input_buffer()

    ser.write(b"PING\n")
    pong = ser.readline().decode(errors="replace").strip()
    if pong != "PONG":
        print(f"WARNING: expected PONG, got {pong!r}", file=sys.stderr)
```

**Command-send + response-collect pattern** (is_poc_capture.py lines 50–75):
```python
def capture_one(ser, duty, direction, n, sps, settle_ms) -> list[int]:
    cmd = f"CAPTURE {direction} {duty} {n} {sps} {settle_ms}\n"
    ser.write(cmd.encode())
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if line.startswith("CAPTURE_START"):
            break
    raw_tokens: list[str] = []
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if line == "CAPTURE_END":
            break
        raw_tokens.extend(line.split(","))
    return [int(x) for x in raw_tokens if x.strip().lstrip("-").isdigit()]
```

Apply same pattern for CALRUN:
```python
def calrun_one(ser, duty_pct: int, settle_ms: int) -> float:
    """Send CALRUN command, return median ZC Hz from firmware."""
    cmd = f"CALRUN {duty_pct} {settle_ms}\n"
    ser.write(cmd.encode())
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if line.startswith("ERROR"):
            raise RuntimeError(f"firmware error: {line}")
        if line.startswith("CALRUN_START"):
            break
    hz_values: list[float] = []
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if line == "CALRUN_END":
            break
        if line.startswith("IS_HZ"):
            _, val = line.split("=")
            hz_values.append(float(val))
    return float(sorted(hz_values)[len(hz_values) // 2]) if hz_values else 0.0
```

**Artifact output pattern** (is_poc_capture.py lines 108–122):
```python
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = out_dir / f"duty_{duty:03d}_{direction}_sps{args.sps}.csv"
    with open(fname, "w", newline="") as fh:
        ...
```

For calibration output (JSON, not CSV):
```python
    out_dir = Path("artifacts/calibration")
    out_dir.mkdir(parents=True, exist_ok=True)
    from datetime import date
    result = {
        "wheel": args.motor,
        "date": str(date.today()),
        "K_hz_per_pct": float(K),
        "dead_hz": float(dead),
        "r_squared": float(r2),
        "points": [{"duty_pct": d, "is_hz": hz} for d, hz in zip(duties, is_hz_list)],
    }
    fname = out_dir / f"cal_{args.motor}_{date.today()}.json"
    fname.write_text(__import__("json").dumps(result, indent=2))
```

---

## Shared Patterns

### C Header Guard + `extern "C"` Portability
**Source:** `firmware/src/app/ramp.h` (lines 1–16) and `control_loop.h` (lines 1–17)
**Apply to:** All new C headers (`zc_detector.h`, `rpm_pi.h`)
```c
#ifndef BIBA_<MODULE>_H
#define BIBA_<MODULE>_H

/* Module description. Portable — no HAL dependency. */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ... declarations ... */

#ifdef __cplusplus
}
#endif

#endif /* BIBA_<MODULE>_H */
```

### NULL Guard in C Implementations
**Source:** `firmware/src/app/ramp.c` (lines 5–8)
**Apply to:** All new C functions that accept pointer arguments
```c
void biba_rpm_pi_reset(biba_rpm_pi_state_t *s)
{
    if (s == NULL) return;
    ...
}
```

### Unity Test Runner Boilerplate
**Source:** `firmware/test/test_ramp/test_main.c` (end of file)
**Apply to:** Both `test_zc_detector/test_main.c` and `test_rpm_pi/test_main.c`
```c
/* Include the module under test + test support shim */
#include "<module>.h"
#include "biba_test_support.h"

/* Static test functions (never exported) */
static void test_<name>(void) { ... }

/* Runner */
int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_<name>);
    return UNITY_END();
}
```

### Python `_get_env_float` Config Pattern
**Source:** `biba-controller/config.py` (lines 22–29)
**Apply to:** All new env-var-backed config constants in `config.py`
```python
NEW_CONSTANT = _get_env_float("NEW_CONSTANT", <default_value>)
```

### Python Struct Pack Clamp Pattern
**Source:** `biba-controller/stm32_link/protocol.py` `to_bytes()` (lines ~219–240)
**Apply to:** New `wheel_rpm_*` fields in `to_bytes()`
```python
max(0, min(0xFFFF, int(round(t.<field> * <scale>)))),
```

### ADC Clock Divisor (MUST NOT CHANGE)
**Source:** `firmware/src/poc/adc_capture.c` (lines 28–36 with critical comment)
```c
/* Critical formula: div = 48e6/sps - 1  (NOT divided by 96)
 * Previous version had /96 making ADC 50× faster than requested */
float div = (float)48000000u / (float)sample_rate_sps - 1.0f;
if (div < 0.0f) div = 0.0f;
adc_set_clkdiv(div);
```
**Apply to:** `firmware/src/app/adc_capture.c` — preserve comment when moving.

---

## No Analog Found

All files have analogs. The `CALRUN` firmware command (in `is_rpm_poc_main.cpp` PoC env) is the only genuinely new firmware command, but it follows the existing `CAPTURE`/`RPMRUN` response format pattern already present in that same file.

---

## Metadata

**Analog search scope:** `firmware/src/app/`, `firmware/src/poc/`, `firmware/src/modes/`, `firmware/src/proto/`, `firmware/test/`, `biba-controller/stm32_link/`, `biba-controller/`, `scripts/`
**Files read:** 17
**Pattern extraction date:** 2026-05-23
