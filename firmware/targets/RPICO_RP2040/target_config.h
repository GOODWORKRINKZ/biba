#ifndef BIBA_TARGET_CONFIG_H
#define BIBA_TARGET_CONFIG_H

/* Target-specific overrides for RPICO_RP2040.
 *
 * RP2040 runs at 125 MHz (PLL configured by pico-sdk before main).
 * ADC is 12-bit / 3.3 V reference.
 *
 * Current sensing topology (Phase 05):
 *   - BTS7960 IS pins → ADS1115 AIN0–3 (I2C, ±4.096 V FSR)
 *     kILIS = 8500 (chip constant), RIS = 1 kΩ → VIS = IL / 8.5 A
 *     BIBA_IS_AMPS_PER_VOLT = 8.5 A/V
 *   - 3DR Power Module current output → RP2040 ADC1 (GP27)
 *     Placeholder calibration — tune from measured shunt data.
 *   - 3DR Power Module voltage output → RP2040 ADC0 (GP26)
 *     Placeholder calibration — tune from measured divider ratio.
 */

#define BIBA_SYS_CLOCK_HZ            125000000u
#define BIBA_PWM_FREQUENCY_HZ        20000   /* 20 kHz carrier, above audible */

/* BTS7960 IS-pin calibration (ADS1115 path).
 * kILIS = 8500 (datasheet), RIS = 1 kΩ → VIS = IL / kILIS × RIS
 * Rearranged: IL = VIS × (kILIS / RIS) = VIS × 8.5 A/V              */
#define BIBA_IS_AMPS_PER_VOLT        8.5f
#define BIBA_IS_ZERO_OFFSET_V        0.0f

/* 3DR Power Module — Ibat (RP2040 ADC1 / GP27).
 * Calibration placeholder: ~18.18 A/V (90 A range over 0–3.3 V ≈ 27.3).
 * TODO: replace with measured shunt calibration value.               */
#define BIBA_IBAT_AMPS_PER_VOLT      18.18f
#define BIBA_IBAT_ZERO_OFFSET_V      0.0f

/* 3DR Power Module — Vbat (RP2040 ADC0 / GP26).
 * Calibration placeholder: ~5.7× resistive divider ratio.
 * TODO: replace with measured divider ratio.                         */
#define BIBA_VBAT_DIVIDER_RATIO      5.7f

#endif /* BIBA_TARGET_CONFIG_H */
