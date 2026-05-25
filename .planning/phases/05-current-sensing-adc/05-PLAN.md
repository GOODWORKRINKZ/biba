# Phase 05: Current Sensing & ADC Architecture — PLAN

**Phase:** 05-current-sensing-adc  
**Created:** 2026-05-19  
**Status:** Ready for execution  
**Req IDs:** ADC-01, ADC-02, ADC-03, ADC-04, TELEM-02

---

## Goal

Переключить 4 IS-пина BTS7960 на ADS1115 (16-bit, I2C), направить выходы 3DR Power Module (Vbat, Ibat) на native RP2040 ADC, добавить AHT30 датчик температуры/влажности на I2C0, и отразить все новые измерения в CRSF-телеметрии.

---

## Architecture Summary

```
BTS7960 ×4 IS pins              ADS1115 (0x48, FSR=±4.096V)
─────────────────               ────────────────────────────
IS_L_fwd ───────────────────── AIN0 (ch0)
IS_L_rev ───────────────────── AIN1 (ch1)          I2C0
IS_R_fwd ───────────────────── AIN2 (ch2)   ──── GP20/GP21
IS_R_rev ───────────────────── AIN3 (ch3)

AHT30 (0x38) ───────────────── same I2C0

3DR Power Module                RP2040 Native ADC (12-bit)
────────────────                ──────────────────────────
VOUT_BAT ──────────────────── GP26 / ADC0  (Vbat)
VOUT_CURR ─────────────────── GP27 / ADC1  (Ibat)
```

**kILIS = 8500, RIS = 1kΩ → amps_per_volt = 8.5 A/V, max ~34.8 A before clip**

---

## Task Waves

### Wave 1 — New drivers + config (independent, run in parallel)

---

#### Task 1 — Create ADS1115 driver

**Files:** `firmware/src/drivers/ads1115.h`, `firmware/src/drivers/ads1115.c`

**API:**
```c
/* ads1115.h */
#ifndef BIBA_ADS1115_H
#define BIBA_ADS1115_H
#include <stdbool.h>
#include <stdint.h>

#define ADS1115_ADDR        0x48u
#define ADS1115_FSR_4096MV  0x02u   /* PGA = 001b → ±4.096 V */
#define ADS1115_FSR_2048MV  0x00u   /* PGA = 010b → ±2.048 V (default) */

bool  ads1115_init(uint8_t addr, uint8_t fsr_setting);
bool  ads1115_read_channel_v(uint8_t addr, uint8_t channel, float *out_v);
#endif
```

**Implementation notes:**
- `ads1115_init()`: write config register (pointer 0x01) with OS=1 (start), MUX for AIN0 vs GND, PGA=001b (±4.096V), MODE=1 (single-shot), DR=100b (128 SPS). Returns true if I2C ACK.
- `ads1115_read_channel_v()`: write config to start single-shot on `channel` (MUX[2:0] = 100b + channel), busy-wait for BUSY bit to clear (poll config register OS bit), read conversion register (pointer 0x00), convert int16 to float: `v = (int16_t)raw * (4.096f / 32768.0f)`
- Use `biba_hal_i2c_write()` and `biba_hal_i2c_read()` (already in HAL)
- `#ifdef BIBA_NATIVE_TEST`: stub implementations that return 0.0f and true (for unit tests)
- ADS1115 config register write: 2-byte address byte (0x01) + 2-byte config word (big-endian)
- Conversion register read: write pointer (0x00), then read 2 bytes → big-endian int16

**MUX encoding for single-ended channels:**
- ch0: MUX=100b → config[14:12] = 0b100
- ch1: MUX=101b → config[14:12] = 0b101
- ch2: MUX=110b → config[14:12] = 0b110
- ch3: MUX=111b → config[14:12] = 0b111

---

#### Task 2 — Create AHT30 driver

**Files:** `firmware/src/drivers/aht30.h`, `firmware/src/drivers/aht30.c`

**API:**
```c
/* aht30.h */
#ifndef BIBA_AHT30_H
#define BIBA_AHT30_H
#include <stdbool.h>
#include <stdint.h>

#define AHT30_ADDR  0x38u

bool aht30_init(void);
bool aht30_read(float *temp_c, float *humidity_pct);
#endif
```

**Implementation notes:**
- `aht30_init()`: send initialization command `{0xBE, 0x08, 0x00}` via `biba_hal_i2c_write(AHT30_ADDR, ...)`. Wait 10 ms. Return true.
- `aht30_read()`:
  1. Send trigger measurement `{0xAC, 0x33, 0x00}` via `biba_hal_i2c_write()`
  2. Wait 80 ms (measurement time per datasheet)
  3. Read 7 bytes via `biba_hal_i2c_write(addr, {0x71}, 1)` then `biba_hal_i2c_read()` of 6 bytes into buf
  4. Check status byte `buf[0]` bit 7 == 0 (not busy)
  5. Humidity: `hum = ((buf[1] << 12) | (buf[2] << 4) | (buf[3] >> 4)) / 1048576.0f * 100.0f`
  6. Temperature: `temp = (((buf[3] & 0x0F) << 16) | (buf[4] << 8) | buf[5]) / 1048576.0f * 200.0f - 50.0f`
- `#ifdef BIBA_NATIVE_TEST`: stubs return 25.0°C / 50.0% and true

---

#### Task 3 — Update target.h: ADC channel reallocation

**File:** `firmware/targets/RPICO_RP2040/target.h`

**Changes:**
- Remove: `BIBA_ADC_CHAN_LEFT_R_IS 1U`, `BIBA_ADC_CHAN_LEFT_L_IS 1U`, `BIBA_ADC_CHAN_RIGHT_R_IS 2U`, `BIBA_ADC_CHAN_RIGHT_L_IS 2U`
- Keep: `BIBA_ADC_CHAN_VBAT 0U` (GP26)
- Add: `BIBA_ADC_CHAN_IBAT 1U` (GP27 — 3DR PM current output)
- Add ADS1115 logical channel defines (used by current_sense.c):
  ```c
  #define BIBA_ADS1115_CHAN_IS_L_FWD   0U   /* AIN0 — left motor, forward */
  #define BIBA_ADS1115_CHAN_IS_L_REV   1U   /* AIN1 — left motor, reverse */
  #define BIBA_ADS1115_CHAN_IS_R_FWD   2U   /* AIN2 — right motor, forward */
  #define BIBA_ADS1115_CHAN_IS_R_REV   3U   /* AIN3 — right motor, reverse */
  ```
- Update `BIBA_ADC_SCAN_LEN 2U` (only ADC0 + ADC1 used now)
- Update `BIBA_ADC_CHANNEL_SEQ { 0, 1 }`
- Update comments to reflect new pin assignment

---

#### Task 4 — Update target_config.h: calibration constants

**File:** `firmware/targets/RPICO_RP2040/target_config.h`

**Add:**
```c
/* BTS7960 IS current sense via ADS1115.
 * kILIS = 8500 (typ), RIS = 1 kΩ → VIS = (IL / 8.5 A) × 1 V
 * → amps_per_volt = 8.5 A/V */
#define BIBA_IS_AMPS_PER_VOLT        8.5f
#define BIBA_IS_ZERO_OFFSET_V        0.0f

/* 3DR Power Module current output calibration.
 * Module: ~60 A max range, voltage output 0–3.3 V linear.
 * Typical: 18.18 A/V (60 A / 3.3 V). Calibrate against known load. */
#define BIBA_IBAT_AMPS_PER_VOLT      18.18f
#define BIBA_IBAT_ZERO_OFFSET_V      0.0f

/* 3DR Power Module voltage output calibration.
 * Module uses a resistor divider to bring 18 V max → 3.3 V.
 * Typical ratio: 5.7×. Calibrate with multimeter. */
#define BIBA_VBAT_DIVIDER_RATIO      5.7f
```

**Note:** Remove the stale comment "No dedicated IS op-amp; leave zero offset/gain defaults". Replace with new comment block above.

---

### Wave 2 — Update existing code (depends on Wave 1)

---

#### Task 5 — Update current_sense.c: IS via ADS1115

**File:** `firmware/src/drivers/current_sense.c`

**Changes:**
- Add `#include "ads1115.h"`
- Replace `biba_hal_adc_sample()` + `biba_hal_adc_volts()` with `ads1115_read_channel_v()` in the `sample()` function:
  ```c
  static biba_motor_current_t sample(uint8_t fwd_ch, uint8_t rev_ch,
                                      const biba_current_calibration_t *cal)
  {
      float vf = 0.0f, vr = 0.0f;
      ads1115_read_channel_v(ADS1115_ADDR, fwd_ch, &vf);
      ads1115_read_channel_v(ADS1115_ADDR, rev_ch, &vr);
      float v = (vf > vr) ? vf : vr;
      float amps = (v - cal->zero_offset_v) * cal->amps_per_volt;
      biba_motor_current_t out = { .current_a = amps, .valid = true };
      return out;
  }
  ```
- Update `biba_current_sense_left()`: call `sample(BIBA_ADS1115_CHAN_IS_L_FWD, BIBA_ADS1115_CHAN_IS_L_REV, &s_left)`
- Update `biba_current_sense_right()`: call `sample(BIBA_ADS1115_CHAN_IS_R_FWD, BIBA_ADS1115_CHAN_IS_R_REV, &s_right)`
- Remove `#include "hal/biba_hal.h"` if no longer needed (check other uses in file)

---

#### Task 6 — Update voltage_sense.c/h: add ibat_a()

**Files:** `firmware/src/drivers/voltage_sense.h`, `firmware/src/drivers/voltage_sense.c`

**Add to voltage_sense.h:**
```c
/* Returns battery current in amps from 3DR PM output on ADC1. */
float biba_voltage_sense_ibat_a(void);
```

**Add to voltage_sense.c:**
```c
float biba_voltage_sense_ibat_a(void)
{
    uint16_t raw = biba_hal_adc_sample(BIBA_ADC_CHAN_IBAT);
    float pin_v  = biba_hal_adc_volts(raw);
    float amps   = (pin_v - BIBA_IBAT_ZERO_OFFSET_V) * BIBA_IBAT_AMPS_PER_VOLT;
    if (amps < 0.0f) amps = 0.0f;
    return amps;
}
```

**Add to biba_config.h defaults** (guarded with `#ifndef`):
```c
#ifndef BIBA_IBAT_AMPS_PER_VOLT
#  define BIBA_IBAT_AMPS_PER_VOLT    1.0f
#endif
#ifndef BIBA_IBAT_ZERO_OFFSET_V
#  define BIBA_IBAT_ZERO_OFFSET_V    0.0f
#endif
```

---

#### Task 7 — Update HAL init: new ADC pin + ADS1115/AHT30 init

**File:** `firmware/src/hal/biba_hal_rp2040.c`

**Changes in `biba_hal_init()`:**
- Change ADC GPIO init section:
  ```c
  /* ADC0 = GP26 (Vbat), ADC1 = GP27 (Ibat from 3DR PM). */
  adc_gpio_init(26u);   /* BIBA_ADC_CHAN_VBAT */
  adc_gpio_init(27u);   /* BIBA_ADC_CHAN_IBAT */
  ```
  Remove the old `adc_gpio_init(26u + BIBA_ADC_CHAN_RAIL_CURRENT)` line.
- After I2C init section, add:
  ```c
  /* ADS1115 (0x48) and AHT30 (0x38) on I2C0. */
  ads1115_init(ADS1115_ADDR, ADS1115_FSR_4096MV);
  aht30_init();
  ```
- Add includes at top of file: `#include "drivers/ads1115.h"` and `#include "drivers/aht30.h"`

---

### Wave 3 — Telemetry update (depends on Wave 2)

---

#### Task 8 — Update telemetry.h: new fields

**File:** `firmware/src/app/telemetry.h`

**Add to `biba_telemetry_input_t`:**
```c
typedef struct {
    float   setpoint_left;
    float   setpoint_right;
    float   current_left_a;
    float   current_right_a;
    uint16_t vbat_mv;         /* battery voltage, millivolts */
    float   ibat_a;           /* battery current, amps (3DR PM) */
    float   temperature_c;    /* ambient temperature °C (AHT30) */
    float   humidity_pct;     /* relative humidity % (AHT30) */
    uint8_t crsf_rssi;
    uint8_t crsf_link_quality;
    int8_t  crsf_snr_db;
    uint8_t error_flags;
    uint8_t seq;
} biba_telemetry_input_t;
```

---

#### Task 9 — Update telemetry.c: collect new fields

**File:** `firmware/src/app/telemetry.c` (locate via grep)

**At collection site** (wherever `biba_telemetry_input_t` is populated before `biba_telemetry_collect()` is called):
- Add `inputs.vbat_mv = biba_voltage_sense_vbat_mv();`
- Add `inputs.ibat_a  = biba_voltage_sense_ibat_a();`
- Add `aht30_read(&inputs.temperature_c, &inputs.humidity_pct);`

**In `biba_telemetry_collect()`** (`firmware/src/app/telemetry.c`):
- Map new fields into `biba_proto_telemetry_t *out` — check proto fields available; add if missing

**Add includes** to telemetry.c site: `voltage_sense.h`, `aht30.h`

---

### Wave 4 — Tests (depends on Wave 3)

---

#### Task 10 — Tests: ADS1115 and AHT30 drivers

**Files:** `tests/test_ads1115.py` and `tests/test_aht30.py` (Python unit tests, matching project pattern)

**test_ads1115.py:**
- Test config register encoding for each channel (ch0–ch3)
- Test voltage conversion: int16 raw → float volts (spot-check: 0x7FFF → +4.096V, 0x8000 → -4.096V, 0 → 0V)
- Test channel mapping: ch0=AIN0vsGND (MUX=100b), ch3=AIN3vsGND (MUX=111b)

**test_aht30.py:**
- Test humidity formula: known raw bytes → known humidity value
- Test temperature formula: known raw bytes → known temperature value
- Test status byte check: busy bit (bit 7 = 1) → returns false

**Note:** These test the pure data-conversion math in isolation (no hardware), consistent with existing `test_current_sense.py` pattern.

---

#### Task 11 — Tests: current_sense with ADS1115 channels

**File:** `tests/test_current_sense.py` (update existing)

- Add test: `biba_current_sense_left()` uses `BIBA_ADS1115_CHAN_IS_L_FWD` and `IS_L_REV` (not native ADC channels)
- Add test: with IS_L_fwd=2.5V, IS_L_rev=0V → current = 2.5 × 8.5 = 21.25 A
- Add test: with IS_L_fwd=0V, IS_L_rev=2.0V → current = 2.0 × 8.5 = 17.0 A (reverse direction)
- Verify `max(fwd, rev)` logic is used

---

#### Task 12 — Tests: telemetry with new fields

**File:** `tests/test_telemetry.py` (update existing)

- Add test: `vbat_mv`, `ibat_a`, `temperature_c`, `humidity_pct` are populated in output struct
- Add test: zero-value inputs produce zero outputs (no garbage data)
- Add test: struct field order/layout is backward-compatible (existing fields unchanged)

---

## Dependency Graph

```
Wave 1: [Task 1] [Task 2] [Task 3] [Task 4]  ← all independent
              ↓       ↓       ↓       ↓
Wave 2:    [Task 5] [Task 6] [Task 7]          ← need Wave 1 complete
                  ↓              ↓
Wave 3:        [Task 8]       [Task 9]          ← need Wave 2 complete
                        ↓
Wave 4:    [Task 10] [Task 11] [Task 12]        ← need Wave 3 complete
```

---

## UAT / Verification

1. **ADC-01:** `ads1115_read_channel_v()` returns correct volts for known I2C fixture response
2. **ADC-02:** `biba_current_sense_left()` returns 21.25 A when IS_L_fwd = 2.5 V (via mock ADS1115)
3. **ADC-03:** `biba_voltage_sense_ibat_a()` returns non-zero float when ADC1 reads non-zero
4. **ADC-04:** `aht30_read()` returns temperature in range –50…+150°C and humidity 0–100%
5. **TELEM-02:** `biba_telemetry_input_t` has all 4 new fields; `biba_telemetry_collect()` propagates them
6. **Cross-check:** `ibat_a ≈ current_left_a + current_right_a` (within 10% tolerance during bench test)
7. **Build:** firmware compiles for `RPICO_RP2040` env with no new warnings
8. **Tests:** all `tests/test_ads1115.py`, `test_aht30.py`, `test_current_sense.py`, `test_telemetry.py` pass

---

## Risk Notes

- **AHT30 busy wait 80ms:** `aht30_read()` blocks the control loop for 80ms — acceptable for telemetry polling (BIBA_TELEMETRY_PUBLISH_HZ = 200, period = 5ms). **Mitigation:** call `aht30_read()` outside the tight 500 Hz control loop, e.g. in a separate 1 Hz telemetry collection pass.
- **ADS1115 single-shot latency:** 4 channels × ~8ms each = 32ms per full scan at 128 SPS. Call from telemetry path (200 Hz), not from 500 Hz control loop.
- **BIBA_VBAT_DIVIDER_RATIO = 5.7f is a placeholder** — calibrate with multimeter against known battery voltage before trusting telemetry Vbat values.
- **3DR PM IBAT calibration:** `BIBA_IBAT_AMPS_PER_VOLT = 18.18f` is from spec; calibrate against a clamp meter at 10+ A load.
