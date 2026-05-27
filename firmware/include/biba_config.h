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

#ifndef BIBA_NATIVE_TEST
#include "target_config.h"

#else /* BIBA_NATIVE_TEST — no target_config.h available */

/* Provide minimal defaults so portable modules compile under pio test -e native_test. */
#ifndef BIBA_SYS_CLOCK_HZ
#  define BIBA_SYS_CLOCK_HZ 125000000u
#endif
#ifndef BIBA_PWM_FREQUENCY_HZ
#  define BIBA_PWM_FREQUENCY_HZ 20000
#endif

#endif /* BIBA_NATIVE_TEST */

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
#ifndef BIBA_BTS7960_RESET_PULSE_US
#  define BIBA_BTS7960_RESET_PULSE_US  100u
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
#  define BIBA_VBAT_DIVIDER_RATIO      10.12f  /* calibrated 2026-05-26: APM module, 23.3V bat → 2858 raw */
#endif

/* 3DR Power Module battery current calibration defaults.
 * Targets with a real power module should override in target_config.h. */
#ifndef BIBA_IBAT_AMPS_PER_VOLT
#  define BIBA_IBAT_AMPS_PER_VOLT      1.0f
#endif
#ifndef BIBA_IBAT_ZERO_OFFSET_V
#  define BIBA_IBAT_ZERO_OFFSET_V      0.0f
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

/* --- System clock ------------------------------------------------------- */

#ifndef BIBA_SYS_CLOCK_HZ
#  define BIBA_SYS_CLOCK_HZ            72000000u
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

/* --- RC channel assignments (0-based index, match biba-controller/config.py) */

#ifndef BIBA_CH_THROTTLE
#  define BIBA_CH_THROTTLE          1   /* CH2 */
#endif
#ifndef BIBA_CH_STEERING
#  define BIBA_CH_STEERING          3   /* CH4 */
#endif
#ifndef BIBA_CH_ARM
#  define BIBA_CH_ARM               4   /* CH5 */
#endif
#ifndef BIBA_CH_SPEED_MODE
#  define BIBA_CH_SPEED_MODE        5   /* CH6 */
#endif
#ifndef BIBA_CH_DRIVE_MODE
#  define BIBA_CH_DRIVE_MODE        9   /* CH10 */
#endif
#ifndef BIBA_CH_BEACON
#  define BIBA_CH_BEACON            7   /* CH8 */
#endif
#ifndef BIBA_CH_TRIM
#  define BIBA_CH_TRIM              8   /* CH9 */
#endif

/* Arm threshold: channel normalised value must exceed this to arm. */
#ifndef BIBA_ARM_THRESHOLD
#  define BIBA_ARM_THRESHOLD        0.3f
#endif

/* Speed mode 3-position switch thresholds (normalised -1..+1). */
#ifndef BIBA_SPEED_MODE_LOW_THRESHOLD
#  define BIBA_SPEED_MODE_LOW_THRESHOLD   (-0.3f)
#endif
#ifndef BIBA_SPEED_MODE_HIGH_THRESHOLD
#  define BIBA_SPEED_MODE_HIGH_THRESHOLD    0.3f
#endif
#ifndef BIBA_SPEED_MODE_SLOW_SCALE
#  define BIBA_SPEED_MODE_SLOW_SCALE       (1.0f / 3.0f)
#endif
#ifndef BIBA_SPEED_MODE_MEDIUM_SCALE
#  define BIBA_SPEED_MODE_MEDIUM_SCALE     (2.0f / 3.0f)
#endif
#ifndef BIBA_SPEED_MODE_FAST_SCALE
#  define BIBA_SPEED_MODE_FAST_SCALE        1.0f
#endif

/* Drive mode switch: low position → MANUAL, else → STABILIZED. */
#ifndef BIBA_DRIVE_MODE_LOW_THRESHOLD
#  define BIBA_DRIVE_MODE_LOW_THRESHOLD   (-0.3f)
#endif

/* Motor trim channel: trim_ch * MAX_EFFECT applied post-mix.
 * Positive trim → attenuate right motor, negative → attenuate left. */
#ifndef BIBA_MOTOR_TRIM_MAX_EFFECT
#  define BIBA_MOTOR_TRIM_MAX_EFFECT        0.30f
#endif

/* Deadband below which throttle/steering are not considered active. */
#ifndef BIBA_MOTOR_DEADBAND
#  define BIBA_MOTOR_DEADBAND               0.05f
#endif

/* Operator steering input deadband. The transmitter stick can mechanically
 * stick near center; below this threshold straight throttle must remain straight. */
#ifndef BIBA_STEERING_DEADBAND
#  define BIBA_STEERING_DEADBAND            0.20f
#endif

/* Trim gesture: hold the first 4 RC channels above this threshold
 * for BIBA_TRIM_CONFIRM_HOLD_MS (while disarmed) to enter/exit trim mode.
 * Matches biba-controller/main.py _TRIM_GESTURE_HIGH_THRESHOLD / MOTOR_TRIM_CONFIRM_HOLD_S. */
#ifndef BIBA_TRIM_GESTURE_THRESHOLD
#  define BIBA_TRIM_GESTURE_THRESHOLD       0.9f
#endif
#ifndef BIBA_TRIM_CONFIRM_HOLD_MS
#  define BIBA_TRIM_CONFIRM_HOLD_MS         5000u
#endif

/* Reverse backup beep: interval between pip starts (ms). */
#ifndef BIBA_REVERSE_PIP_ENABLED
#  define BIBA_REVERSE_PIP_ENABLED          0
#endif
#ifndef BIBA_REVERSE_PIP_INTERVAL_MS
#  define BIBA_REVERSE_PIP_INTERVAL_MS      600u
#endif

/* Motor direction inversion (1 = normal, -1 = inverted).
 * Mirror MOTOR1_INVERTED / MOTOR2_INVERTED from biba-controller/config.py. */
#ifndef BIBA_LEFT_MOTOR_DIR
#  define BIBA_LEFT_MOTOR_DIR    1
#endif
#ifndef BIBA_RIGHT_MOTOR_DIR
#  define BIBA_RIGHT_MOTOR_DIR  (-1)
#endif

/* --- Output ramping (MOTOR-03) --------------------------------------- */
/* Mirror RAMP_* from biba-controller/config.py.                        */
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

#ifndef BIBA_RPM_SETPOINT_ACCEL_RATE
#  define BIBA_RPM_SETPOINT_ACCEL_RATE   2.0f   /* was 0.6 — ramp faster than physics so PI uses full duty */
#endif
#ifndef BIBA_RPM_SETPOINT_DECEL_RATE
#  define BIBA_RPM_SETPOINT_DECEL_RATE   1.0f   /* 1.0 = full→zero in 1s */
#endif
#ifndef BIBA_RPM_SETPOINT_REVERSE_DECEL_RATE
#  define BIBA_RPM_SETPOINT_REVERSE_DECEL_RATE 0.5f
#endif
#ifndef BIBA_RPM_SETPOINT_ZERO_HOLD_MS
#  define BIBA_RPM_SETPOINT_ZERO_HOLD_MS 150u
#endif

/* Motor calibration — MY1016Z3 24V 350W, 2-pole 4-brush
 * G=9:1 planetary gearbox, N_comm=16 commutator bars
 * Verified: 798.4 Hz @ 329 RPM wheel → G*N = 144.0 (1.1% err vs 145.6 measured) */
#ifndef BIBA_RPM_GEAR_RATIO
#  define BIBA_RPM_GEAR_RATIO             9
#endif
#ifndef BIBA_RPM_COMMUTATOR_BARS
#  define BIBA_RPM_COMMUTATOR_BARS        16
#endif
#ifndef BIBA_RPM_PULSES_PER_WHEEL_REV
#  define BIBA_RPM_PULSES_PER_WHEEL_REV   (BIBA_RPM_GEAR_RATIO * BIBA_RPM_COMMUTATOR_BARS)  /* 144 */
#endif

/* --- Blackbox recorder -------------------------------------------------- */

/* Recording rate in Hz (records per second written to LittleFS). */
#ifndef BIBA_BLACKBOX_RATE_HZ
#  define BIBA_BLACKBOX_RATE_HZ      25
#endif

/* Bitmask of fields included in each record (0xFFFF = all 16 fields). */
#ifndef BIBA_BLACKBOX_FIELD_MASK
#  define BIBA_BLACKBOX_FIELD_MASK   0xFFFFu
#endif

/* Minimum free space threshold: if LittleFS free < this, session is blocked. */
#ifndef BIBA_BLACKBOX_MIN_FREE_KB
#  define BIBA_BLACKBOX_MIN_FREE_KB  64u
#endif

/* CH7 triggers the blackbox recorder (separate from beacon/SOS on CH8). */
#ifndef BIBA_CH_BLACKBOX
#  define BIBA_CH_BLACKBOX  6   /* CH7 */
#endif

/* --- RPM dead-reckoning fallback --------------------------------------- */

#ifndef BIBA_RPM_DR_MAX_STREAK
#  define BIBA_RPM_DR_MAX_STREAK    5u       /* ~500 ms at 10 Hz ADC loop */
#endif
#ifndef BIBA_RPM_DR_RATIO_LO
#  define BIBA_RPM_DR_RATIO_LO      0.50f    /* p10 floor across all sweep channels */
#endif
#ifndef BIBA_RPM_DR_RATIO_HI
#  define BIBA_RPM_DR_RATIO_HI      1.30f    /* generous ceiling above p95=1.129 LEFT FWD */
#endif
#ifndef BIBA_RPM_DR_ALPHA
#  define BIBA_RPM_DR_ALPHA         0.2f     /* EMA smoothing (5-step time constant) */
#endif

/* --- IS-pin DC load gate (Phase 11) ------------------------------------ */
#ifndef BIBA_RPM_LOAD_RATIO_THRESH
#  define BIBA_RPM_LOAD_RATIO_THRESH     1.5f   /* ratio = mean_IS_primary / mean_IS_other */
#endif
#ifndef BIBA_RPM_LOAD_QUALITY_MAX
#  define BIBA_RPM_LOAD_QUALITY_MAX      10.0f  /* gate fires only when quality < this */
#endif
#ifndef BIBA_RPM_LOAD_ABS_THRESH_ADC
#  define BIBA_RPM_LOAD_ABS_THRESH_ADC   3800u  /* absolute ADC count fallback gate (D-A3) */
#endif

/* --- Open-loop bypass (disable PI + spectral + ZC entirely) ------------- */
/* When defined, the firmware runs in pure open-loop mode:
 *   - CRSF throttle maps directly to motor duty (no PI controller)
 *   - Spectral estimator, ZC detector, DR, and PI step are all skipped
 *   - ADC DMA still runs (for IS mean current monitoring)
 *   - Blackbox still records throttle + actual duty
 * Comment out to restore closed-loop PI control. */
#define BIBA_OPEN_LOOP

#endif /* BIBA_CONFIG_H */
