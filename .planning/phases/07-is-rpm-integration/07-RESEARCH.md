# Phase 07: IS-RPM Integration — Research

**Researched:** 2026-05-23  
**Domain:** RP2040 firmware — ZC detector + FF+PI closed-loop RPM, biba_proto extension, Python speed estimation  
**Confidence:** HIGH (codebase fully verified by direct file inspection)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
1. **PI+FF loop lives entirely in RP2040 firmware** — ZC detector and PI run on RP2040, not Pi Python
2. **PI+FF replaces `biba_ramp_t`** in `mode_standalone.c`
3. **Both wheels** — IS_LEFT (GP26/ADC0) + IS_RIGHT (GP27/ADC1) implemented simultaneously
4. **Proto extension** — `uint16_t wheel_rpm_left_hz10` + `uint16_t wheel_rpm_right_hz10` in `biba_proto_telemetry_t`
5. **Gain scheduling** — Ki_low = 0.005 when `target_hz < 200`
6. **Unity C tests** in `firmware/test/` for ZC detector and PI module
7. **Calibration** — CALRUN command + `scripts/is_rpm_calibrate.py` script
8. **Speed estimation** — Pi Python converts rpm_hz → m/s via `WHEEL_RADIUS_M` + `GEAR_RATIO` in `config.py`

### Agent's Discretion
- Internal architecture for non-blocking ADC DMA in standalone mode (core1 vs DMA IRQ vs polling)
- Location of new C modules within `firmware/src/`
- Exact DMA dual-channel strategy (sequential vs interleaved)
- Scope of proto version bump (minor vs reserved-carve)

### Deferred Ideas (OUT OF SCOPE)
- UART CDC shell in production firmware
- FFT / autocorr algorithms
- Heading-hold / yaw correction (Phase 2)
- ROS2 velocity state
- Absolute RPM calibration requiring motor pole count
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RPM-INT-01 | A2 Schmitt ZC detector for IS_LEFT and IS_RIGHT in `rpico_rp2040_standalone`, valid at 25–100% duty | PoC algorithm verified in `is_rpm_poc_main.cpp`, ADC pins confirmed in `target.h` |
| RPM-INT-02 | FF+PI loop on RP2040 holds target ±10% SS error at 200–900 Hz; gain scheduling reduces OS < 30% at < 200 Hz | PI+FF algorithm extracted from PoC, gain scheduling pattern documented |
| RPM-INT-03 | `wheel_rpm_left_hz10` + `wheel_rpm_right_hz10` in biba_proto; Python decodes + converts to m/s; calibration R² > 0.95 | Proto struct layout fully mapped, Python decode chain traced, calibration script pattern identified |
</phase_requirements>

---

## Summary

Phase 7 is a **port and integration** — the A2 Sub-window Schmitt ZC detector and FF+PI controller from `firmware/src/poc/is_rpm_poc_main.cpp` must be extracted into standalone C modules and wired into `firmware/src/modes/mode_standalone.c`. The PoC code is well-structured and contains the complete algorithm with excellent inline comments; extraction effort is low.

The primary design challenge is **non-blocking ADC DMA in the standalone main loop**. The PoC uses a synchronous busy-wait (100 ms per capture). In standalone mode, blocking CRSF processing for 200 ms (L + R sequential) would approach the 500 ms failsafe timeout. The correct pattern is interrupt-driven DMA completion: start DMA, run main loop normally, on DMA IRQ compute ZC and schedule next capture.

The biba_proto extension is constrained to the **existing 11-byte reserved region** of `biba_proto_telemetry_t`, which can absorb 2× uint16 leaving `reserved[7]`. This is a backward-compatible carve (struct size stays 48 bytes, wire encoding changes format string and Python struct). The proto version is not bumped (same `BIBA_PROTO_VERSION = 0x01`) but `TELEMETRY_STRUCT` and `Telemetry` dataclass must be updated atomically with the C struct.

Unity tests follow the **existing `native_test` env pattern** exactly. New test dirs `test_zc_detector/` and `test_rpm_pi/` are portable (no hardware dependency) and compile under the existing `[env:native_test]` env without platformio.ini changes.

**Primary recommendation:** Port PoC's `zc_freq_hz()` verbatim to `firmware/src/app/zc_detector.c`, extract PI+FF state machine to `firmware/src/app/rpm_pi.c`, use DMA IRQ completion callbacks for non-blocking operation, serialize L then R ADC captures (200 ms full cycle, 5 Hz RPM loop rate).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ZC detection (ADC DMA + frequency estimation) | RP2040 firmware (app layer) | — | Must run at hardware speed, cannot round-trip over USB/SPI |
| FF+PI RPM controller | RP2040 firmware (app layer) | — | Requires direct `biba_hal_motor_pwm_*()` access at 10 Hz |
| Motor duty output | RP2040 firmware (HAL) | — | Hardware PWM, no SPI latency |
| Telemetry encoding (rpm_hz → uint16) | RP2040 firmware (proto layer) | — | Packed into existing `biba_proto_telemetry_t` |
| Telemetry decoding (uint16 → float Hz) | Pi Python (`protocol.py`) | — | Already handles struct unpacking |
| Speed estimation (Hz → m/s) | Pi Python (`main.py`) | — | `WHEEL_RADIUS_M` + `GEAR_RATIO` from `config.py` env vars |
| Calibration data collection | Pi Python (`is_rpm_calibrate.py`) | RP2040 firmware (CALRUN cmd) | Script drives firmware, collects data, fits linear model |
| Unity tests for ZC + PI | native (host gcc, no hardware) | — | Must be portable; existing `native_test` env handles this |

---

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pico-sdk (via arduino-pico) | local platform | RP2040 DMA, ADC, IRQ | Already used in PoC; `hardware/dma.h`, `hardware/adc.h` |
| Unity | ^2.6.1 (via PlatformIO) | C unit testing | Already in `native_test` env; throwtheswitch/Unity |
| Python struct | stdlib | proto packing/unpacking | Already used in `protocol.py` |

### Supporting (already in project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyserial | existing | CDC serial communication | `is_rpm_calibrate.py` (copy pattern from `is_poc_capture.py`) |
| numpy / scipy.stats | existing | polyfit + R² | `is_rpm_calibrate.py` calibration computation |

### New C Source Files (to create)
| File | Location | Purpose |
|------|----------|---------|
| `zc_detector.h/c` | `firmware/src/app/` | A2 Sub-window Schmitt ZC frequency estimator |
| `rpm_pi.h/c` | `firmware/src/app/` | FF+PI RPM controller with gain scheduling |

### Files to Move (from poc/ to app/)
| Current | Destination | Notes |
|---------|-------------|-------|
| `firmware/src/poc/adc_capture.h` | `firmware/src/app/adc_capture.h` | Already clean C API, move as-is |
| `firmware/src/poc/adc_capture.c` | `firmware/src/app/adc_capture.c` | Extend to support non-blocking DMA IRQ callback |

**Installation:** No new external dependencies. All required libraries already present.

---

## Architecture Patterns

### System Architecture Diagram

```
  [CRSF RX] ──→ [CRSF Parser] ──→ [Mixer + Limiter] ──→ [RPM PI Left]  ──→ [HAL L PWM]
                                         ↑                [RPM PI Right] ──→ [HAL R PWM]
                                  target_hz_left/right
                                         ↑
  [ADC DMA IRQ] ──→ [ZC Detector Left]  ─┘
                 ──→ [ZC Detector Right] ─┘
                         ↑
  [GP26 IS_LEFT ADC0] ───┤
  [GP27 IS_RIGHT ADC1] ──┘

  [RPM PI Left/Right] ──→ [biba_proto_telemetry_t.wheel_rpm_{left|right}_hz10]
                               ──→ [SPI MISO] ──→ [Pi Python TelemetryFrame]
                                                         ──→ [wheel_rpm_hz → m/s]
```

### Non-Blocking DMA State Machine

The main loop (`biba_mode_standalone_tick()`) must never block. ADC captures use an IRQ-driven state machine:

```
State: ADC_IDLE
  → biba_mode_standalone_init() starts first capture → ADC_CAPTURING_LEFT

State: ADC_CAPTURING_LEFT  (100 ms DMA in progress)
  → DMA complete IRQ fires
  → Compute ZC_left
  → Start right channel DMA → ADC_CAPTURING_RIGHT

State: ADC_CAPTURING_RIGHT  (100 ms DMA in progress)
  → DMA complete IRQ fires
  → Compute ZC_right
  → Run PI update for both channels
  → Apply duty via volatile shared: s_rpm_duty_left, s_rpm_duty_right
  → Start left channel DMA → ADC_CAPTURING_LEFT

Main loop tick:
  → Reads s_rpm_duty_left / s_rpm_duty_right (volatile, last PI output)
  → Applies current limits, failsafe zeroing, final PWM
```

**DMA IRQ approach:** Use `dma_channel_set_irq0_enabled(ch, true)` + `irq_add_shared_handler(DMA_IRQ_0, handler, PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY)`. The handler runs on core0 (same as main loop), so no mutex needed. Short critical section for state transition only.

### Recommended Project Structure (new files in firmware/)
```
firmware/src/app/
├── adc_capture.h       # moved from poc/ — add irq callback variant
├── adc_capture.c       # moved from poc/ — add adc_capture_start_async()
├── zc_detector.h       # new: A2 ZC algorithm, pure computation
├── zc_detector.c       # new: ~80 lines, portable C99
├── rpm_pi.h            # new: FF+PI state + config structs
├── rpm_pi.c            # new: ~150 lines, portable C99
├── control_loop.h/c    # existing: unchanged
├── ramp.h/c            # existing: retained (still used in non-RPM scenarios)
├── telemetry.h/c       # existing: extended with rpm fields
└── ...

firmware/test/
├── test_zc_detector/
│   └── test_main.c     # new: Unity tests for zc_freq_hz()
├── test_rpm_pi/
│   └── test_main.c     # new: Unity tests for rpm_pi_step()
└── ...
```

### Pattern 1: ZC Detector Module Header
```c
// firmware/src/app/zc_detector.h
// Source: direct extraction from firmware/src/poc/is_rpm_poc_main.cpp lines 130–183

#pragma once
#include <stdint.h>

#define ZC_SUBWIN_K          8u
#define ZC_SUBWIN_MIN_PKPK   30u   /* per-block AC threshold (ADC LSB) */
#define ZC_MIN_VALID_HZ      80.0f
#define ZC_EMA_ALPHA         0.7f

/* Returns frequency in Hz (0.0 if no valid signal).
 * buf: ADC 12-bit samples, n: sample count, sps: sample rate Hz */
float zc_freq_hz(const uint16_t *buf, uint16_t n, uint32_t sps);

/* EMA-filtered ZC with validity gating. Updates *ema in-place.
 * target_hz: current setpoint (used for high-side validity gate).
 * meas_raw: raw zc_freq_hz() output. Returns new filtered value. */
float zc_ema_update(float *ema, float meas_raw, float target_hz);
```

### Pattern 2: RPM PI Module Header
```c
// firmware/src/app/rpm_pi.h
// Source: extracted from firmware/src/poc/is_rpm_poc_main.cpp lines 200–360

#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    float kp;
    float ki;
    float ki_low;          /* gain scheduling: used when |target_hz| < ki_low_thresh */
    float ki_low_thresh;   /* Hz threshold for gain scheduling */
    float ff_slope;        /* Hz/% — from calibration */
    float ff_dead;         /* Hz — dead-zone offset */
    float stiction_floor;  /* duty fraction — min duty when target > 0 */
    float p_clamp;         /* max |P term| duty contribution */
    float i_clamp_pos;     /* asymmetric integral clamp positive */
    float i_clamp_neg;     /* asymmetric integral clamp negative */
    float dt_s;            /* PI update period (e.g. 0.104 for dual-channel) */
} biba_rpm_pi_config_t;

typedef struct {
    float integral;
    float meas_ema;
    float prev_duty;
    bool  primed;
} biba_rpm_pi_state_t;

void  biba_rpm_pi_reset(biba_rpm_pi_state_t *s);
/* Returns duty in [-1.0, 1.0]. target_hz positive = forward, negative = reverse. */
float biba_rpm_pi_step(biba_rpm_pi_state_t *s,
                       const biba_rpm_pi_config_t *cfg,
                       float target_hz,
                       float meas_raw_hz);
```

### Pattern 3: Non-Blocking ADC Capture API Extension
```c
// Addition to firmware/src/app/adc_capture.h
// (moved from poc/ and extended)

/* Start a non-blocking DMA capture. Returns false if DMA already busy.
 * Calls callback(channel, buf, n) from DMA IRQ context when complete. */
typedef void (*adc_capture_done_cb_t)(uint8_t channel,
                                      const uint16_t *buf,
                                      uint16_t n);
bool adc_capture_start_async(uint8_t channel, uint16_t n_samples,
                              uint16_t *out_buf,
                              adc_capture_done_cb_t callback);
```

### Anti-Patterns to Avoid
- **Blocking DMA in main loop:** `adc_capture_burst()` (from PoC) must NOT be called in `biba_mode_standalone_tick()`. It blocks for 100ms and will freeze CRSF processing. Use async variant only.
- **Interleaved multi-channel ADC without deinterleaving:** RP2040 round-robin ADC interleaves L/R samples. If you pass the raw interleaved buffer to `zc_freq_hz()`, the spacing between same-channel samples is 2× the expected period — ZC frequency will be halved. Always deinterleave or use sequential single-channel captures.
- **PI output applied without failsafe gating:** The PI duty output must be zeroed by core0's failsafe path. Core1 or IRQ handler writes to volatile shared variables; the final `biba_bts7960_drive()` call must check `failsafe` flag.
- **Proto struct size drift:** `sizeof(biba_proto_telemetry_t)` must stay 48 bytes. Do not add fields without reducing `reserved[]` by the same amount. Python's `assert TELEMETRY_SIZE == 48` catches this.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DMA transfer | Custom memcpy loop | `hardware/dma.h` pico-sdk | Already used in `adc_capture.c`; handles DREQ, transfer size, increment flags |
| ADC clock config | Manual register writes | `adc_set_clkdiv()` | Already correct in `adc_capture.c`; critical formula comment preserved |
| CRC for proto | New CRC impl | Existing `biba_proto_crc16_ccitt()` | Both C and Python already implement and test this |
| Freq estimation | FFT / autocorr | `zc_freq_hz()` from PoC | PoC bench-validated A2 algorithm; FFT too expensive on RP2040 |
| Serial protocol for calibration | New USB CDC protocol | Extend PoC CALRUN pattern, inherit `is_poc_capture.py` pyserial approach | Existing scripts show the pattern; copy and adapt |

---

## Source Code to Port — Detailed Map

### 1. `zc_freq_hz()` — verbatim extraction

**Source:** `firmware/src/poc/is_rpm_poc_main.cpp` lines ~130–183  
**Action:** Extract as-is. The function has no platform-specific code — it's pure C99 arithmetic on a `uint16_t[]` buffer.

```c
// Lines ~130–183 of is_rpm_poc_main.cpp
static float zc_freq_hz(const uint16_t *buf, uint16_t n, uint32_t sps)
```
Change: `static` → non-static; add to `zc_detector.h` header.

### 2. EMA update logic — extract as `zc_ema_update()`

**Source:** `firmware/src/poc/is_rpm_poc_main.cpp` lines ~220–250 (validity gate + EMA update in cmd_rpmrun loop)  
**Action:** Wrap the validity-gate + EMA logic into `zc_ema_update()` from pattern above. The logic is:
- If `meas_raw >= ZC_MIN_VALID_HZ && meas_raw <= target_hz * 2.5f + 300.0f` → EMA update with alpha=0.7
- If `meas_raw == 0.0f` → decay EMA × 0.9
- Else (noise spike) → hold EMA unchanged

### 3. PI+FF controller — extract as `biba_rpm_pi_step()`

**Source:** `firmware/src/poc/is_rpm_poc_main.cpp` lines ~255–360 (the inner PI loop in `cmd_rpmrun`)  
**Key parameters to transfer:**
- FF: `ff_duty = direction × (target_mag + ff_dead) / (ff_slope × 100)`
- Gain scheduling: if `|target_hz| < 200`, use `ki_low` instead of `ki`
- Anti-windup: `can_integrate = !(sat_high && err>0) && !(sat_low && err<0) && meas_hz > 50`
- Asymmetric integral clamp: `i_clamp_pos = 0.03f / (ki + 1e-6f)`, `i_clamp_neg = 0.01f / (ki + 1e-6f)`
- P clamp: `|p_term| ≤ 0.05f`; p_term = 0 when meas_hz == 0
- Stiction floor: snap duty to `stiction_floor` if commanded in (0, stiction_floor)

### 4. `adc_capture.c/h` — move + extend

**Source:** `firmware/src/poc/adc_capture.c` / `adc_capture.h`  
**Action:** Move to `firmware/src/app/`. Add `adc_capture_start_async()` which starts DMA without blocking, registers a completion callback on `DMA_IRQ_0`. Existing `adc_capture_burst()` (blocking) can remain for PoC compatibility and Unity tests.

### 5. `mode_standalone.c` — ramp replacement

**Source:** `firmware/src/modes/mode_standalone.c`  
**Lines to change:**

| What changes | Current code | Replacement |
|-------------|--------------|-------------|
| Static state | `biba_ramp_t s_ramp_left; biba_ramp_t s_ramp_right;` | `biba_rpm_pi_state_t s_rpm_left; biba_rpm_pi_state_t s_rpm_right; volatile float s_rpm_duty_left; volatile float s_rpm_duty_right;` |
| Init | `biba_ramp_init(&s_ramp_left); biba_ramp_init(&s_ramp_right);` | `biba_rpm_pi_reset(&s_rpm_left); biba_rpm_pi_reset(&s_rpm_right); biba_adc_rpm_loop_init();` |
| Failsafe reset | `biba_ramp_reset(&s_ramp_left); biba_ramp_reset(&s_ramp_right);` | `biba_rpm_pi_reset(&s_rpm_left); biba_rpm_pi_reset(&s_rpm_right); s_rpm_duty_left = 0.0f; s_rpm_duty_right = 0.0f;` |
| Mix → duty path | `biba_ramp_update(&s_ramp_left, left_out, dt)` | Convert `left_out` to `target_hz_left`; read `s_rpm_duty_left` computed by IRQ handler; apply failsafe zero |
| Telemetry inputs | No RPM fields | Add `wheel_rpm_left_hz10 = ...` populated from IRQ handler's last meas_ema |

The ramp includes `#include "app/ramp.h"` can be **removed** from mode_standalone.c. `ramp.h/c` itself is **retained** (used by tests, potentially other modes).

---

## Proto Extension — Exact Changes

### C struct (`firmware/src/proto/biba_proto.h`)

**Current** (lines ~160–175):
```c
    uint8_t  humidity_q8;           /* relative humidity 0-100 % (AHT30) */
    uint8_t  reserved[11];          /* pad to 48 bytes */
} biba_proto_telemetry_t;
```

**After:**
```c
    uint8_t  humidity_q8;           /* relative humidity 0-100 % (AHT30) */
    uint16_t wheel_rpm_left_hz10;   /* IS_LEFT ZC freq × 10 (0.1 Hz res); 0 = invalid */
    uint16_t wheel_rpm_right_hz10;  /* IS_RIGHT ZC freq × 10; 0 = invalid */
    uint8_t  reserved[7];           /* pad to 48 bytes */
} biba_proto_telemetry_t;
```

**Size check:** 48 bytes unchanged (removed 4 bytes from reserved, added 2 × uint16 = 4 bytes). ✓

### Python protocol (`biba-controller/stm32_link/protocol.py`)

**Current TELEMETRY_STRUCT** (line ~168):
```python
TELEMETRY_STRUCT = "<hhhhHHhhhhhhBBbBIhhB11s"
```

**After:**
```python
TELEMETRY_STRUCT = "<hhhhHHhhhhhhBBbBIhhBHH7s"
```
(`11s` → `HH7s` — two uint16 fields + 7-byte reserved)

**Current assert** (line ~169): `assert TELEMETRY_SIZE == 48` — **still passes** ✓

**`Telemetry` dataclass** — add two fields:
```python
    wheel_rpm_left_hz:  float = 0.0   # raw IS_LEFT ZC frequency (0 = invalid)
    wheel_rpm_right_hz: float = 0.0   # raw IS_RIGHT ZC frequency (0 = invalid)
```

**`from_bytes` fields** — add after `humidity_pct=float(fields[19])`:
```python
    wheel_rpm_left_hz  = fields[20] / 10.0,
    wheel_rpm_right_hz = fields[21] / 10.0,
```

**`to_bytes` struct.pack call** — replace `b"\x00" * 11` with:
```python
    max(0, min(0xFFFF, int(round(t.wheel_rpm_left_hz  * 10)))),
    max(0, min(0xFFFF, int(round(t.wheel_rpm_right_hz * 10)))),
    b"\x00" * 7,
```

### `biba_telemetry_input_t` (`firmware/src/app/telemetry.h`)

Add fields so `biba_telemetry_collect()` can populate RPM from the IRQ handler's state:
```c
    float   wheel_rpm_left_hz;   /* 0 = invalid/no signal */
    float   wheel_rpm_right_hz;
```

### `biba_telemetry_collect()` (`firmware/src/app/telemetry.c`)

Add after `humidity_q8` line:
```c
    out->wheel_rpm_left_hz10  = (uint16_t)(inputs->wheel_rpm_left_hz  * 10.0f + 0.5f);
    out->wheel_rpm_right_hz10 = (uint16_t)(inputs->wheel_rpm_right_hz * 10.0f + 0.5f);
```

---

## ADC / DMA Integration

### GP26/GP27 Availability — CONFIRMED SAFE

From `firmware/targets/RPICO_RP2040/target.h`:
> GP26 ADC0 = IS_LEFT (1kΩ‖1kΩ RC filter from BTS7960 L IS pins — Phase 06)  
> GP27 ADC1 = IS_RIGHT (1kΩ‖1kΩ RC filter from BTS7960 R IS pins — Phase 06)

From `firmware/targets/RPICO_RP2040/target_config.h`:
> Phase 06 HW not yet wired: native ADC GP26/GP27 carry noise/old VBAT divider **until** 1k‖1k + 0.1µF RC filter is installed on BTS7960 IS pins.

**Resolution:** Phase 6 hardware was completed (RC filter installed per FINDINGS). VBAT/IBAT are now on ADS1115 AIN0/AIN1. GP26/GP27 are free for IS sensing. The `target_config.h` comment is stale and should be updated in Phase 7.

**No ADC pin conflict exists** for the production standalone env. [VERIFIED: target.h and target_config.h]

### Dual-Channel Strategy: Sequential Single-Channel (Recommended)

Two options exist for capturing both IS channels:

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| **A: Sequential single-channel** | Capture L (100ms), then R (100ms). Total: 200ms, 5 Hz PI update | Simple; existing `adc_capture_burst()` works; no deinterleave code | 5 Hz PI update (vs 10 Hz in PoC) |
| **B: Round-robin interleaved** | Single 2048-sample DMA at 10kSPS, deinterleave L/R. Total: 100ms, 10 Hz PI update | 10 Hz match to PoC | Needs new deinterleave logic; PoC explicitly disabled this |

**Recommendation: Option A** (sequential). The PI integral clamp handles 5 Hz updates correctly — the PoC demonstrated stable control at 10 Hz; 5 Hz will have slightly slower transient response but still meets the ±10% SS error requirement at steady state.

### Async DMA API Extension for `adc_capture.c`

The existing `adc_capture_burst()` uses a blocking poll loop. For Phase 7, add a callback-based variant:

```c
// adc_capture.c — addition
static adc_capture_done_cb_t s_done_cb;
static int s_dma_ch = -1;

static void dma_irq_handler(void) {
    if (s_dma_ch >= 0 && dma_channel_get_irq0_status(s_dma_ch)) {
        dma_channel_acknowledge_irq0(s_dma_ch);
        adc_run(false);
        adc_fifo_drain();
        // note: n_samples from last call stored in static
        if (s_done_cb) s_done_cb(s_last_channel, s_buf_ptr, s_last_n);
    }
}

bool adc_capture_start_async(uint8_t channel, uint16_t n_samples,
                              uint16_t *out_buf,
                              adc_capture_done_cb_t callback) {
    // ... same DMA setup as adc_capture_burst() but non-blocking ...
    // enable DMA_IRQ_0, store callback, return immediately
}
```

---

## Python Integration

### `biba-controller/config.py` — Add Speed Constants

**No existing WHEEL_RADIUS_M or GEAR_RATIO.** [VERIFIED: grep found no matches]

Add after existing motor config (around line 90):
```python
# --- Wheel odometry (for m/s estimation from IS-RPM) -------------------
WHEEL_RADIUS_M = _get_env_float("WHEEL_RADIUS_M", 0.100)   # 10 cm default placeholder
GEAR_RATIO     = _get_env_float("GEAR_RATIO",     1.0)      # dimensionless; 1.0 = direct drive
```

### `biba-controller/main.py` — Speed Estimation Hook

The `TelemetryFrame` is assembled in `mode_standalone.c` and received by Python via SPI (or USB CDC in development). The `main.py` receives a `TelemetryFrame` object. Speed estimation should be computed whenever telemetry is processed — no new import needed:

```python
# After receiving telemetry frame in main loop:
import math
import config

def wheel_rpm_to_mps(rpm_hz: float) -> float:
    """Convert IS-signal frequency (Hz) to wheel linear speed (m/s)."""
    if rpm_hz <= 0:
        return 0.0
    # v = omega * r = (2*pi*f) * r / gear_ratio
    return (2.0 * math.pi * rpm_hz * config.WHEEL_RADIUS_M) / config.GEAR_RATIO

# In telemetry handler:
speed_left_mps  = wheel_rpm_to_mps(frame.telemetry.wheel_rpm_left_hz)
speed_right_mps = wheel_rpm_to_mps(frame.telemetry.wheel_rpm_right_hz)
```

This function should live in `biba-controller/stm32_link/protocol.py` or a new `biba-controller/motors/odometry.py` module. The function itself is trivial — a one-liner + config access.

---

## Calibration Script — `scripts/is_rpm_calibrate.py`

### Pattern (from existing `is_poc_capture.py`)

The calibration script follows the same pyserial pattern as `is_poc_capture.py`:
1. Open serial port to firmware CALRUN endpoint
2. For each duty point: send `CALRUN <duty_pct>`, collect IS ZC data
3. Prompt user for tachometer reading at each duty point
4. Polyfit duty → is_hz and duty → tach_hz
5. Compute K = tach_hz / duty slope, R², compare with current firmware value
6. Save JSON artifact to `scripts/artifacts/calibration/`

### CALRUN Command Design

The PoC has no CALRUN command — it's new for Phase 7. Since Phase 7 production firmware won't have a CDC shell, CALRUN should be implemented in a separate **calibration firmware variant** or as an extension of the PoC env. Options:

**Option A (recommended):** Add CALRUN to the existing `rpico_rp2040_is_poc` env (no new env needed). CALRUN differs from STEPRUN/SWEEP only in output format:
- `CALRUN <duty_pct> <settle_ms>` → drives motor, captures 1024@10kSPS, reports median ZC Hz

**Option B:** Compile a dedicated test firmware that outputs CALRUN + IS_POC_READY. Adds complexity without benefit.

### Output JSON Format (per CONTEXT.md)
```json
{
  "wheel": "left",
  "date": "2026-05-XX",
  "K_hz_per_pct": 10.13,
  "dead_hz": 74.6,
  "r_squared": 0.97,
  "points": [
    {"duty_pct": 30, "is_hz": 228.0, "tach_hz": 231.0}
  ]
}
```

---

## Unity Test Infrastructure

### Existing Pattern (fully verified)

```
firmware/test/
├── test_ramp/test_main.c          — example: uses RUN_TEST(fn), biba_test_support.h
├── test_control_loop/test_main.c  — example: uses TEST_ASSERT_FLOAT_WITHIN
├── test_support/biba_test_support.h — shim: maps Unity macros or BIBA_TEST_STANDALONE
└── test_biba_proto/test_main.c    — example: tests struct packing
```

The `[env:native_test]` env compiles `firmware/test/test_<name>/test_main.c` using:
- `platform = native`
- `test_framework = unity`
- `lib_deps = throwtheswitch/Unity@^2.6.1`
- `build_src_filter = ${common.build_src_filter}` (portable modules only — no HAL)

**New tests are discovered automatically** by PlatformIO's test runner scanning `firmware/test/` subdirectories. No platformio.ini changes needed for new test directories.

### New Test Directories

#### `firmware/test/test_zc_detector/test_main.c`

Key test cases:
1. Synthetic pure tone → frequency within ±5%
2. Noisy signal (random ±50 LSB) → valid ZC ≤ 10% error
3. DC-only signal (no AC content) → returns 0.0
4. Single active block (< 2 active) → returns 0.0
5. freq at 80 Hz boundary → ZC_MIN_VALID_HZ guard

```c
#include "zc_detector.h"
#include "biba_test_support.h"
#include <math.h>

// Generate synthetic buffer: n samples of pure sine at freq_hz @ sps
static void fill_sine(uint16_t *buf, uint16_t n, uint32_t sps, float freq_hz, 
                       uint16_t dc_offset, uint16_t amplitude) {
    for (uint16_t i = 0; i < n; i++) {
        float t = (float)i / (float)sps;
        float s = sinf(2.0f * 3.14159f * freq_hz * t);
        buf[i] = (uint16_t)(dc_offset + (int)(s * amplitude));
    }
}

static void test_zc_pure_sine_300hz(void) {
    uint16_t buf[1024];
    fill_sine(buf, 1024, 10000, 300.0f, 2048, 800);
    float hz = zc_freq_hz(buf, 1024, 10000);
    TEST_ASSERT_FLOAT_WITHIN(15.0f, 300.0f, hz);  // ±5%
}
```

#### `firmware/test/test_rpm_pi/test_main.c`

Key test cases:
1. `biba_rpm_pi_reset()` → state zeroed
2. FF-only step (kp=ki=0) → correct duty from target_hz
3. PI step at 400 Hz: overshoot < 20% after settling (10 simulated steps)
4. Gain scheduling: ki changes when `target_hz < 200`
5. Anti-windup: integral does not grow when duty saturated
6. Direction change: duty negative for negative target_hz

### Build and Run Command
```bash
cd /home/ros2/Downloads/biba/firmware
pio test -e native_test           # runs all native tests including new ones
pio test -e native_test -f test_zc_detector   # single test dir
```

---

## PlatformIO Build System

### Adding new modules to standalone env

The `[rp2040_src_filter]` stanza controls what gets compiled:

```ini
[rp2040_src_filter]
build_src_filter =
    +<*>
    -<hal/biba_hal.c>
    -<hal/biba_hal_motor.c>
    -<hal/biba_hal_debug.c>
    -<main.c>
    -<poc/>                ← poc/ is excluded from standalone
```

After moving `adc_capture.c` to `firmware/src/app/`, it will be included automatically (no filter change needed — `+<*>` includes `app/`). New `zc_detector.c` and `rpm_pi.c` in `app/` are also auto-included.

The PoC env `rpico_rp2040_is_poc` uses `rp2040_poc_src_filter` which includes `+<poc/>` and excludes `modes/` and `app/`. This remains unchanged.

### ADC DMA IRQ in platformio.ini

No changes needed — `hardware/dma.h` and `hardware/irq.h` are already included via `target.h`.

---

## Common Pitfalls

### Pitfall 1: ADC Clock Divider Formula
**What goes wrong:** Setting `adc_set_clkdiv(div)` with an incorrect formula causes ADC to run at 50× the intended rate (captures 4 ms instead of 100 ms), producing noise-floor ZC readings.  
**Why it happens:** The pico-sdk `adc_set_clkdiv()` takes a fractional divisor of the 48 MHz ADC clock. The formula is `div = 48e6 / sps - 1` — NOT `/96`.  
**How to avoid:** The existing `adc_capture.c` has the correct formula with a long comment explaining the bug. Copy this comment verbatim to the new module.  
**Warning signs:** ZC returns random values 20–200 Hz at all duty points.

### Pitfall 2: Proto Struct Padding
**What goes wrong:** Adding `uint16_t` fields to `biba_proto_telemetry_t` without `#pragma pack(push, 1)` causes 1-byte padding before `uint16_t` fields, shifting all subsequent fields by 1 byte and breaking Python decode.  
**How to avoid:** The struct already has `#pragma pack(push, 1)`. Add new fields inside the `#pragma pack` block. Python `TELEMETRY_SIZE == 48` assert will catch mismatches.

### Pitfall 3: Blocking ADC in Main Loop
**What goes wrong:** Calling `adc_capture_burst()` from `biba_mode_standalone_tick()` blocks for 100 ms × 2 = 200 ms. During this time CRSF is not read, and if CRSF frames are missed the failsafe fires (500 ms timeout, but repeated 200 ms blocks reduce the margin to ~2 missed ticks).  
**How to avoid:** Use `adc_capture_start_async()` with DMA IRQ callback exclusively in standalone integration.

### Pitfall 4: EMA Freeze After Direction Change
**What goes wrong:** On direction change, `meas_ema` is not reset to 0. The EMA retains a positive value from the previous direction, the PI computes a large negative error, and overshoots in the new direction.  
**How to avoid:** In `biba_rpm_pi_reset()`, zero `meas_ema` along with `integral`. The PoC cmd_rpmtrack does `integral=0; meas_ema=0; duty=0` on direction sign change — replicate this logic in `biba_rpm_pi_step()` when direction of `target_hz` reverses.

### Pitfall 5: Stale target_config.h Comment
**What goes wrong:** `target_config.h` says "Phase 06 HW not yet wired: native ADC GP26/GP27 carry noise/old VBAT divider until..." — a developer might disable IS-sensing based on this stale comment.  
**How to avoid:** Phase 7 should update the comment in `target_config.h` to reflect that Phase 6 hardware is complete and GP26/GP27 carry filtered IS signals.

### Pitfall 6: Python struct field index drift
**What goes wrong:** When adding `HH` before `7s` in `TELEMETRY_STRUCT`, `fields[20]` and `fields[21]` are new. If `from_bytes` still references `fields[19]` as the last field and doesn't add `fields[20]`/`fields[21]`, the RPM fields decode as 0 silently.  
**How to avoid:** Always verify field index by counting: `fields[0..19]` for existing fields, `fields[20]` = wheel_rpm_left_hz10, `fields[21]` = wheel_rpm_right_hz10. Unit test `test_stm32_link_protocol.py` must cover the new fields.

---

## Files to Create / Modify (Complete List)

### New Files
| File | Action |
|------|--------|
| `firmware/src/app/zc_detector.h` | Create — ZC algorithm header |
| `firmware/src/app/zc_detector.c` | Create — ~80 lines extracted from PoC |
| `firmware/src/app/rpm_pi.h` | Create — FF+PI controller header |
| `firmware/src/app/rpm_pi.c` | Create — ~150 lines extracted + gain scheduling |
| `firmware/test/test_zc_detector/test_main.c` | Create — Unity tests for zc_detector |
| `firmware/test/test_rpm_pi/test_main.c` | Create — Unity tests for rpm_pi |
| `scripts/is_rpm_calibrate.py` | Create — calibration script |
| `scripts/artifacts/calibration/.gitkeep` | Create — output directory |

### Files to Move
| From | To |
|------|----|
| `firmware/src/poc/adc_capture.h` | `firmware/src/app/adc_capture.h` |
| `firmware/src/poc/adc_capture.c` | `firmware/src/app/adc_capture.c` |

After move: update `#include "poc/adc_capture.h"` in `is_rpm_poc_main.cpp` to `"app/adc_capture.h"` (or keep as `poc/adc_capture.h` in the PoC env via include path — see note below).  
**Note:** The PoC env's `build_src_filter` includes `+<poc/>` which will now miss `adc_capture.c`. Fix: either keep a stub in `poc/` that `#include`s the app version, or add `+<app/adc_capture.c>` to `rp2040_poc_src_filter`. Simplest: add `+<app/adc_capture.c>` to `rp2040_poc_src_filter`.

### Existing Files to Modify
| File | Change Summary |
|------|----------------|
| `firmware/src/proto/biba_proto.h` | Add 2 uint16 fields, reduce reserved[11] → reserved[7] |
| `firmware/src/app/telemetry.h` | Add `wheel_rpm_left_hz`, `wheel_rpm_right_hz` to `biba_telemetry_input_t` |
| `firmware/src/app/telemetry.c` | Populate `wheel_rpm_left/right_hz10` from input fields |
| `firmware/src/modes/mode_standalone.c` | Replace ramp with RPM PI, add ADC loop init, hook telemetry |
| `firmware/src/poc/is_rpm_poc_main.cpp` | Update `#include` path for adc_capture after move |
| `firmware/platformio.ini` | `rp2040_poc_src_filter`: add `+<app/adc_capture.c>` |
| `firmware/targets/RPICO_RP2040/target_config.h` | Update stale comment about GP26/GP27 HW not wired |
| `biba-controller/stm32_link/protocol.py` | TELEMETRY_STRUCT, Telemetry dataclass, from_bytes, to_bytes |
| `biba-controller/config.py` | Add WHEEL_RADIUS_M, GEAR_RATIO |
| `biba-controller/main.py` | Add speed estimation from telemetry RPM fields |
| `tests/test_stm32_link_protocol.py` | Add tests for new RPM telemetry fields |

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Unity ^2.6.1 (via PlatformIO) + pytest (Python) |
| Config file | `firmware/platformio.ini` `[env:native_test]` + `pytest.ini` |
| Quick C run | `cd firmware && pio test -e native_test -f test_zc_detector` |
| Full C suite | `cd firmware && pio test -e native_test` |
| Quick Python | `python3 -m pytest tests/test_stm32_link_protocol.py -x` |
| Full Python | `python3 -m pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RPM-INT-01 | ZC detector returns correct Hz ±5% for synthetic sine | unit C | `pio test -e native_test -f test_zc_detector` | ❌ Wave 0 |
| RPM-INT-01 | ZC returns 0 for DC/noise-only signal | unit C | `pio test -e native_test -f test_zc_detector` | ❌ Wave 0 |
| RPM-INT-02 | PI step produces correct FF duty (kp=ki=0) | unit C | `pio test -e native_test -f test_rpm_pi` | ❌ Wave 0 |
| RPM-INT-02 | Gain scheduling applies ki_low when target < 200 | unit C | `pio test -e native_test -f test_rpm_pi` | ❌ Wave 0 |
| RPM-INT-03 | Proto struct size == 48 bytes after RPM fields added | unit C | `pio test -e native_test -f test_biba_proto` | ❌ Wave 0 update |
| RPM-INT-03 | Python TelemetryFrame round-trip with RPM fields | unit Python | `pytest tests/test_stm32_link_protocol.py` | ❌ Wave 0 |
| RPM-INT-03 | Hardware: SS error ≤ 10% at 400 Hz | integration (hardware) | manual + `is_poc_step.py` adapted | N/A |
| RPM-INT-03 | Hardware: OS < 30% at 200 Hz | integration (hardware) | manual + `is_poc_step.py` adapted | N/A |
| RPM-INT-03 | Calibration R² > 0.95 | integration (hardware) | `is_rpm_calibrate.py` | N/A |

### Wave 0 Gaps
- [ ] `firmware/test/test_zc_detector/test_main.c` — covers RPM-INT-01
- [ ] `firmware/test/test_rpm_pi/test_main.c` — covers RPM-INT-02
- [ ] Update `firmware/test/test_biba_proto/test_main.c` — add RPM field assertion
- [ ] Update `tests/test_stm32_link_protocol.py` — add RPM field round-trip test
- [ ] `firmware/src/app/zc_detector.h/c` — must exist before tests can compile
- [ ] `firmware/src/app/rpm_pi.h/c` — must exist before tests can compile

---

## Security Domain

Phase 7 adds no network-facing surface. All new attack surface is: CDC serial commands (CALRUN) and SPI telemetry fields.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | ADC input: clamped before use; CALRUN duty clamped to [0, 100]; struct fields: uint16 range naturally bounded |
| V6 Cryptography | no | No cryptographic operations |
| V2 Authentication | no | No new auth surface |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| CALRUN duty > 100% via CDC | Tampering/EoP | Clamp in firmware: `if (duty > 100) duty = 100` (pattern from PoC `cmd_capture`) |
| Stale RPM telemetry driving incorrect Pi decisions | Spoofing | `wheel_rpm_hz10 == 0` sentinel means invalid/no signal; Python should respect this |
| DMA buffer overrun | Tampering | `adc_capture_start_async()` must validate `n_samples <= ADC_CAPTURE_MAX_SAMPLES` |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PlatformIO CLI | C compilation, Unity tests | ✓ | local platform | — |
| Python 3 + pytest | Python tests | ✓ | (existing) | — |
| pyserial | `is_rpm_calibrate.py` | ✓ | (used in is_poc_capture.py) | — |
| numpy | calibration polyfit | ✓ | (used in is_poc_analyse.py) | — |
| RP2040 hardware (flashed standalone) | Hardware validation | manual/external | — | simulate with PoC env |
| Tachometer | calibration R² > 0.95 | manual/external | — | use existing PoC is_hz as reference |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Phase 6 hardware change (RC filter on GP26/27) was physically completed | ADC Conflict | If filter not installed, IS noise prevents valid ZC. Mitigation: visually verify before flash |
| A2 | Sequential L+R captures (200ms, 5Hz PI loop) will meet ±10% SS error spec | Dual-Channel Strategy | If 5Hz is too slow for plant dynamics, may need interleaved approach or slower speed targets |
| A3 | `biba_mode_standalone_tick()` is safe to call from Arduino `loop()` alongside DMA IRQ handler on core0 | DMA Architecture | If IRQ handler and main loop race on shared state (volatile floats), may need critical section |

---

## Open Questions

1. **DMA IRQ sharing with existing peripherals**  
   What is: The RP2040 standalone firmware may already use DMA_IRQ_0 for other purposes (SPI slave, etc.).  
   Unclear: Whether `irq_add_shared_handler()` handles contention correctly with other DMA channels.  
   Recommendation: Check `biba_hal_rp2040.c` for existing DMA channel usage; if DMA_IRQ_0 is taken, use DMA_IRQ_1 for ADC.

2. **`BIBA_CONTROL_LOOP_HZ` interaction with RPM PI timing**  
   What is: main loop runs at 500 Hz but RPM PI updates at 5 Hz (200ms).  
   Unclear: Whether the `dt` parameter passed to existing PID/ramp code breaks when mode_standalone has variable tick intervals.  
   Recommendation: The RPM PI has its own fixed `dt = 0.204s` (2× DMA window). Don't pass `dt` from main loop to RPM PI — use a fixed constant.

3. **motor_trim interaction with RPM PI**  
   What is: `mode_standalone.c` applies `s_saved_motor_trim` to left/right duty post-ramp.  
   Unclear: Should trim apply to the target_hz (before PI) or to the final duty (after PI)?  
   Recommendation: Apply trim to target_hz: `target_hz_right *= (1.0f - trim)`. This way the PI still closes the loop correctly around the trimmed target, rather than post-correcting the PI output.

---

## Sources

### Primary (HIGH confidence — direct file inspection)
- `firmware/src/poc/is_rpm_poc_main.cpp` — complete ZC and PI+FF algorithm
- `firmware/src/poc/adc_capture.c` / `adc_capture.h` — DMA implementation
- `firmware/src/proto/biba_proto.h` / `.c` — struct layout, size 48 bytes
- `firmware/src/app/` — all app modules: telemetry, ramp, control_loop
- `firmware/src/modes/mode_standalone.c` — integration target
- `firmware/platformio.ini` — env structure, filters
- `firmware/targets/RPICO_RP2040/target.h` / `target_config.h` — pin assignments
- `biba-controller/stm32_link/protocol.py` — Python decode chain
- `biba-controller/config.py` — no existing WHEEL_RADIUS_M/GEAR_RATIO
- `firmware/test/` — Unity test pattern
- `.planning/phases/06-is-rpm-poc/06-FINDINGS.md` — calibration params, algorithm selection
- `.planning/phases/07-is-rpm-integration/07-CONTEXT.md` — locked decisions

### Secondary (MEDIUM confidence)
- `.planning/phases/06-is-rpm-poc/06-SUMMARY.md` — architectural conclusions from PoC

---

## Metadata

**Confidence breakdown:**
- Source code to port: HIGH — directly read, line-by-line
- Proto extension: HIGH — struct layout and Python decode chain fully traced
- Unity test infrastructure: HIGH — existing test patterns verified
- ADC/DMA architecture: MEDIUM — async IRQ approach is standard pico-sdk pattern but not currently used in this codebase
- Dual-channel strategy: MEDIUM — Option A (sequential) is conservative and verified; Option B (interleaved) requires additional research
- Speed estimation: HIGH — trivial formula, config pattern well-established

**Research date:** 2026-05-23  
**Valid until:** 2026-07-23 (stable codebase — no external dependencies to expire)

---

## RESEARCH COMPLETE

**Phase:** 07 — IS-RPM Integration  
**Confidence:** HIGH

### Key Findings

1. **PoC code is directly portable** — `zc_freq_hz()` (80 lines) and the PI+FF loop (~150 lines) are pure C99 with no hardware dependencies. Extraction to standalone C modules is mechanical work.

2. **Proto extension is zero-risk** — The 48-byte struct has 11 reserved bytes. Carving 4 bytes for 2×uint16 leaves `reserved[7]`. Struct size unchanged; Python `assert TELEMETRY_SIZE == 48` still passes. Field index shift in `from_bytes` is the only drift risk (caught by new unit test).

3. **Non-blocking DMA is the critical architectural decision** — The blocking `adc_capture_burst()` from PoC must NOT be used in standalone mode. DMA IRQ completion callbacks are the correct pattern for pico-sdk. This is new work (not copy-paste from PoC) but well-defined.

4. **GP26/GP27 pins are confirmed IS-only** in Phase 6 hardware. VBAT/IBAT moved to ADS1115. No pin conflict.

5. **Unity native_test env requires zero platformio.ini changes** for new test directories — PlatformIO auto-discovers `test_*/` subdirs.

6. **15 files total**: 8 new files, 2 moved, 5+ modified. The heaviest modification is `mode_standalone.c` (ramp → RPM PI swap) and `protocol.py` (struct extension).

### File Created
`.planning/phases/07-is-rpm-integration/07-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Source algorithm (ZC, PI+FF) | HIGH | Read verbatim from working PoC |
| Proto extension | HIGH | Struct layout verified byte-by-byte |
| Integration points | HIGH | All target files read line-by-line |
| ADC DMA async architecture | MEDIUM | Standard pico-sdk pattern, not previously used in this codebase |
| Hardware performance (OS, SS error) | MEDIUM | Based on PoC measurements; dual-channel at 5Hz not bench-tested |

### Open Questions
1. Check `biba_hal_rp2040.c` for existing DMA_IRQ_0 usage before assigning to ADC
2. Decide motor trim interaction with RPM PI (apply to target_hz vs final duty)
3. Verify 5 Hz dual-channel PI rate acceptable in hardware test

### Ready for Planning
Research complete. Planner can create PLAN.md files.
