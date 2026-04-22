#ifndef BIBA_CONFIG_H
#define BIBA_CONFIG_H

/* Global firmware configuration.
 *
 * Layering:
 *   1. The selected target may override any of the values below by
 *      defining them in targets/<TARGET>/target_config.h. That header
 *      is pulled in first here, and every default below is guarded by
 *      an `#ifndef`, so a target override always wins.
 *   2. Values here are the sensible fallbacks that are either
 *      non-board-specific (control loop rate, CRSF baud, protocol
 *      timeouts) or reasonable for a stock Blue Pill rig.
 *
 * Defaults intentionally mirror biba-controller/config.py and
 * docs/wiring.md so that standalone-mode behaviour on the STM32 lines
 * up with the Raspberry Pi runtime out of the box.
 */

#include "target_config.h"

/* --- Control loop timing ------------------------------------------------ */

#ifndef BIBA_CONTROL_LOOP_HZ
#  define BIBA_CONTROL_LOOP_HZ         500
#endif
#ifndef BIBA_TELEMETRY_PUBLISH_HZ
#  define BIBA_TELEMETRY_PUBLISH_HZ    200
#endif

/* --- Motor / PWM -------------------------------------------------------- */

#ifndef BIBA_PWM_FREQUENCY_HZ
#  define BIBA_PWM_FREQUENCY_HZ        20000   /* 20 kHz carrier, above audible */
#endif
#ifndef BIBA_PWM_DEADTIME_NS
#  define BIBA_PWM_DEADTIME_NS         500     /* dead-time between RPWM/LPWM */
#endif

/* --- Current / power limits (match Pi defaults) ------------------------- */

#ifndef BIBA_LEFT_MAX_CURRENT_A
#  define BIBA_LEFT_MAX_CURRENT_A      18.0f
#endif
#ifndef BIBA_RIGHT_MAX_CURRENT_A
#  define BIBA_RIGHT_MAX_CURRENT_A     18.0f
#endif
#ifndef BIBA_LEFT_MAX_POWER_W
#  define BIBA_LEFT_MAX_POWER_W        180.0f
#endif
#ifndef BIBA_RIGHT_MAX_POWER_W
#  define BIBA_RIGHT_MAX_POWER_W       180.0f
#endif
#ifndef BIBA_FALLBACK_SUPPLY_V
#  define BIBA_FALLBACK_SUPPLY_V       24.0f
#endif

/* BTS7960 current sense calibration defaults (volts -> amps). */
#ifndef BIBA_IS_ZERO_OFFSET_V
#  define BIBA_IS_ZERO_OFFSET_V        0.0f
#endif
#ifndef BIBA_IS_AMPS_PER_VOLT
#  define BIBA_IS_AMPS_PER_VOLT        1.0f
#endif

/* --- Battery voltage divider (default 1:11 for ~33 V max) -------------- */

#ifndef BIBA_VBAT_DIVIDER_RATIO
#  define BIBA_VBAT_DIVIDER_RATIO      11.0f
#endif
/* PA5 rail tap uses its own divider. Defaults to the VBAT ratio because
 * the reference Blue Pill wiring shares the 1:11 ladder; a custom board
 * with a dedicated 12 V rail divider should override this in its
 * targets/<TARGET>/target_config.h. */
#ifndef BIBA_RAIL_12V_DIVIDER_RATIO
#  define BIBA_RAIL_12V_DIVIDER_RATIO  BIBA_VBAT_DIVIDER_RATIO
#endif
#ifndef BIBA_ADC_VREF_V
#  define BIBA_ADC_VREF_V              3.3f
#endif
#ifndef BIBA_ADC_MAX_COUNTS
#  define BIBA_ADC_MAX_COUNTS          4095    /* 12-bit ADC1 */
#endif

/* --- CRSF link ---------------------------------------------------------- */

#ifndef BIBA_CRSF_BAUD
#  define BIBA_CRSF_BAUD               420000
#endif
#ifndef BIBA_CRSF_TIMEOUT_MS
#  define BIBA_CRSF_TIMEOUT_MS         500
#endif

/* --- SPI link ----------------------------------------------------------- */

#ifndef BIBA_SPI_LINK_TIMEOUT_MS
#  define BIBA_SPI_LINK_TIMEOUT_MS     200
#endif

#endif /* BIBA_CONFIG_H */
