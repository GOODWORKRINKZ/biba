#ifndef BIBA_TARGET_CONFIG_H
#define BIBA_TARGET_CONFIG_H

/* Target-specific overrides for RPICO_RP2040.
 *
 * RP2040 runs at 125 MHz (PLL configured by pico-sdk before main).
 * ADC is 12-bit / 3.3 V reference.
 *
 * Native ADC topology — three channels on-board (no external ADC):
 *   - GP26 / ADC0: IS_RIGHT — BTS7960 right IS pins → 1kΩ‖1kΩ + 0.1µF RC filter
 *     R_eff = 500Ω, kILIS = 8500 → VIS = IL / 17 → BIBA_IS_AMPS_PER_VOLT = 17.0 A/V
 *   - GP27 / ADC1: IS_LEFT  — BTS7960 left  IS pins → 1kΩ‖1kΩ + 0.1µF RC filter
 *     Same calibration as IS_RIGHT.
 *   - GP28 / ADC2: VBAT     — resistive voltage divider → BIBA_VBAT_DIVIDER_RATIO
 *     Tune BIBA_VBAT_DIVIDER_RATIO from measured Vbat vs ADC reading.
 */

#define BIBA_SYS_CLOCK_HZ            125000000u
#define BIBA_PWM_FREQUENCY_HZ        20000   /* 20 kHz carrier, above audible */

/* BTS7960 IS-pin calibration (Phase 06: RC-filtered native ADC path).
 * R_eff = 500Ω (1kΩ ‖ 1kΩ), kILIS = 8500.
 * VIS = IL × R_eff / kILIS = IL / 17 → IL = VIS × 17.0 A/V         */
#define BIBA_IS_AMPS_PER_VOLT        17.0f
#define BIBA_IS_ZERO_OFFSET_V        0.0f

/* VBAT — GP28 / ADC2, native RP2040 ADC (3.3 V reference, 12-bit).
 * Resistive divider ratio — tune BIBA_VBAT_DIVIDER_RATIO from measured
 * Vbat vs ADC reading once the divider is wired to GP28.
 * Placeholder: 10.1× matches a standard 10kΩ/1kΩ divider for ~33 V max.
 * At 6S full charge (25.2 V): 25.2 / 10.1 = 2.49 V — within 3.3 V ADC ref. */
#define BIBA_VBAT_DIVIDER_RATIO      10.1f

/* Phase 06 HW not yet wired: native ADC GP26/GP27 carry noise/old VBAT
 * divider until 1k‖1k + 0.1µF RC filter is installed on BTS7960 IS pins.
 * Disable per-motor current AND power limiters so spurious IS readings
 * don't throttle PWM (power limiter uses the same current sample).
 * Restore to 18.0f / 180.0f after Phase 06 hardware rework. */
#define BIBA_LEFT_MAX_CURRENT_A      0.0f
#define BIBA_RIGHT_MAX_CURRENT_A     0.0f
#define BIBA_LEFT_MAX_POWER_W        0.0f
#define BIBA_RIGHT_MAX_POWER_W       0.0f

#endif /* BIBA_TARGET_CONFIG_H */
