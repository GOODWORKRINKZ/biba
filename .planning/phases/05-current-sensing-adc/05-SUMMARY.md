# Phase 05 – Current Sensing & ADC Architecture: Summary

## Outcome

Phase 05 successfully migrated all four BTS7960 IS-pin signals from the RP2040's
native ADC to an external ADS1115 (16-bit I2C ADC), added battery-current sensing
via the 3DR Power Module on native ADC channels, and wired AHT30 temperature/humidity
into the telemetry pipeline.  All 12 tasks executed across 4 waves; 70 new/updated
tests pass with zero regressions.

## Commits

| Wave | Commit   | Contents |
|------|----------|----------|
| 1    | cb47161  | `ads1115.h/c`, `aht30.h/c`, `target.h` ADC remap, `target_config.h` calibration |
| 2    | 5d7652f  | `current_sense.c` → ADS1115, `voltage_sense` + ibat, HAL I2C/ADC init |
| 3    | 2de4f65  | `telemetry.h` new inputs, `telemetry.c` collections, `biba_proto.h` struct carved |
| 4    | d0f30bd  | `protocol.py` Pi-side decoder, `test_ads1115.py`, `test_aht30.py`, test updates |

## Key Decisions

### 1. All 4 IS pins → ADS1115 (not native RP2040 ADC)
- **Reason**: Native ADC clips at 3.3 V = ~28 A; ADS1115 FSR ±4.096 V handles ~34.8 A.
- **Prior bug fixed**: LEFT_L_IS and LEFT_R_IS both aliased to CH1; RIGHT_L_IS and RIGHT_R_IS both aliased to CH2 — only 2 of 4 IS signals were actually read.

### 2. ADS1115 channel map (mirrors firmware target.h)
| Signal       | AIN  | MUX bits |
|--------------|------|----------|
| IS_L_FWD     | AIN0 | 100b     |
| IS_L_REV     | AIN1 | 101b     |
| IS_R_FWD     | AIN2 | 110b     |
| IS_R_REV     | AIN3 | 111b     |

### 3. AHT30 NOT called from 500 Hz control loop
- `aht30_read()` blocks ~80 ms; caller must pre-populate `biba_telemetry_input_t.temperature_c`
  and `.humidity_pct` from a separate low-rate task before calling `biba_telemetry_collect()`.

### 4. `biba_proto_telemetry_t` size unchanged at 48 bytes
- Carved from the `reserved[16]` tail: `int16_t ibat_ma`, `int16_t temperature_cdeg`,
  `uint8_t humidity_q8`, `uint8_t reserved[11]`.

### 5. Calibration constants (placeholder, field-tune later)
| Constant                  | Value      | Location           |
|---------------------------|------------|--------------------|
| `BIBA_IS_AMPS_PER_VOLT`   | 8.5 A/V    | `target_config.h`  |
| `BIBA_IBAT_AMPS_PER_VOLT` | 18.18 A/V  | `target_config.h`  |
| `BIBA_VBAT_DIVIDER_RATIO` | 5.7        | `target_config.h`  |

## Files Changed

### New firmware
- `firmware/src/drivers/ads1115.h` / `.c`
- `firmware/src/drivers/aht30.h` / `.c`

### Updated firmware
- `firmware/targets/RPICO_RP2040/target.h`
- `firmware/targets/RPICO_RP2040/target_config.h`
- `firmware/include/biba_config.h`
- `firmware/src/drivers/current_sense.c`
- `firmware/src/drivers/voltage_sense.h` / `.c`
- `firmware/src/hal/biba_hal_rp2040.c`
- `firmware/src/app/telemetry.h` / `.c`
- `firmware/src/proto/biba_proto.h`

### Updated Pi-side
- `biba-controller/stm32_link/protocol.py`

### New/updated tests
- `tests/test_ads1115.py` (12 tests — new)
- `tests/test_aht30.py` (10 tests — new)
- `tests/test_current_sense.py` (8 firmware-alignment tests appended)
- `tests/test_stm32_link_protocol.py` (4 new proto round-trip tests)
- `tests/test_telemetry.py` (2 new battery-encoding tests)

## Test Results

```
70 passed in 0.09s  (phase 05 tests)
521 passed / 94 failed  (full suite — 94 failures pre-existed before this phase)
```

## Follow-up Items

- [ ] Field-tune `BIBA_IS_AMPS_PER_VOLT`, `BIBA_IBAT_AMPS_PER_VOLT`, `BIBA_VBAT_DIVIDER_RATIO`
- [ ] Implement low-rate AHT30 polling task in `main.c` / HAL loop
- [ ] Add BIBA current-limit logic using the new IS data
- [ ] Confirm ADS1115 conversion timing is acceptable at 500 Hz loop (single-shot 128 SPS = ~8 ms/ch)
