#ifndef BIBA_CONFIG_H
#define BIBA_CONFIG_H

/* Build-time configuration for the BiBa STM32F103 firmware.
 *
 * Defaults here intentionally mirror biba-controller/config.py and
 * docs/wiring.md so that standalone-mode behaviour on the STM32 matches
 * the existing Raspberry Pi runtime. */

/* --- Control loop timing ------------------------------------------------ */

#define BIBA_CONTROL_LOOP_HZ         500
#define BIBA_TELEMETRY_PUBLISH_HZ    200

/* --- Motor / PWM -------------------------------------------------------- */

#define BIBA_PWM_FREQUENCY_HZ        20000   /* 20 kHz carrier, above audible */
#define BIBA_PWM_DEADTIME_NS         500     /* dead-time between RPWM/LPWM */

/* --- Current / power limits (match Pi defaults) ------------------------- */

#define BIBA_LEFT_MAX_CURRENT_A      18.0f
#define BIBA_RIGHT_MAX_CURRENT_A     18.0f
#define BIBA_LEFT_MAX_POWER_W        180.0f
#define BIBA_RIGHT_MAX_POWER_W       180.0f
#define BIBA_FALLBACK_SUPPLY_V       24.0f

/* BTS7960 current sense calibration defaults (volts -> amps). */
#define BIBA_IS_ZERO_OFFSET_V        0.0f
#define BIBA_IS_AMPS_PER_VOLT        1.0f

/* --- Battery voltage divider (PA4 through 1:11 divider for ~33 V max) --- */

#define BIBA_VBAT_DIVIDER_RATIO      11.0f
#define BIBA_ADC_VREF_V              3.3f
#define BIBA_ADC_MAX_COUNTS          4095    /* 12-bit ADC1 */

/* --- CRSF link ---------------------------------------------------------- */

#define BIBA_CRSF_BAUD               420000
#define BIBA_CRSF_TIMEOUT_MS         500

/* --- SPI link ----------------------------------------------------------- */

#define BIBA_SPI_LINK_TIMEOUT_MS     200

#endif /* BIBA_CONFIG_H */
