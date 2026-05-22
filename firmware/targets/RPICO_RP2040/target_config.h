#ifndef BIBA_TARGET_CONFIG_H
#define BIBA_TARGET_CONFIG_H

/* Target-specific overrides for RPICO_RP2040.
 *
 * RP2040 runs at 125 MHz (PLL configured by pico-sdk before main).
 * ADC is 12-bit / 3.3 V reference.
 *
 * Current sensing topology (Phase 06):
 *   - BTS7960 IS pins RC-filtered → RP2040 native ADC GP26 (IS_LEFT) / GP27 (IS_RIGHT)
 *     R_eff = 500Ω (1kΩ ‖ 1kΩ), kILIS = 8500 → VIS = IL × 500 / 8500 = IL / 17
 *     BIBA_IS_AMPS_PER_VOLT = 17.0 A/V
 *   - 3DR Power Module voltage output → ADS1115 AIN0
 *     Placeholder calibration — tune from measured divider ratio.
 *   - 3DR Power Module current output → ADS1115 AIN1
 *     Placeholder calibration — tune from measured shunt data.
 */

#define BIBA_SYS_CLOCK_HZ            125000000u
#define BIBA_PWM_FREQUENCY_HZ        20000   /* 20 kHz carrier, above audible */

/* BTS7960 IS-pin calibration (Phase 06: RC-filtered native ADC path).
 * R_eff = 500Ω (1kΩ ‖ 1kΩ), kILIS = 8500.
 * VIS = IL × R_eff / kILIS = IL / 17 → IL = VIS × 17.0 A/V         */
#define BIBA_IS_AMPS_PER_VOLT        17.0f
#define BIBA_IS_ZERO_OFFSET_V        0.0f

/* 3DR Power Module — Ibat (Phase 06: ADS1115 AIN1).
 * Calibration placeholder: ~18.18 A/V (90 A range over 0–3.3 V ≈ 27.3).
 * TODO: replace with measured shunt calibration value.               */
#define BIBA_IBAT_AMPS_PER_VOLT      18.18f
#define BIBA_IBAT_ZERO_OFFSET_V      0.0f

/* GM v1.0 / APM-Pixhawk Power Module clone (90 A) — Vbat (Phase 06: ADS1115 AIN0).
 * Standard resistive divider ratio = 10.1× (matches ArduPilot BATT_VOLT_MULT).
 * At 6S full charge (25.2 V): 25.2 / 10.1 = 2.49 V — within ADS1115 max.
 * Fine-tune from measured Vbat vs ADC reading if needed.             */
#define BIBA_VBAT_DIVIDER_RATIO      10.1f

#endif /* BIBA_TARGET_CONFIG_H */
