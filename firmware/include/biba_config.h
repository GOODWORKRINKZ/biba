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

/* ========================================================================
 * CRITICAL SAFETY — NO FEATURE TOGGLES
 * These are always present and cannot be disabled (per D-05).
 * ======================================================================== */

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

/* --- Current sense calibration (BTS7960 IS pin, volts → amps) ---------- */

#ifndef BIBA_IS_ZERO_OFFSET_V
#  define BIBA_IS_ZERO_OFFSET_V        0.0f
#endif
#ifndef BIBA_IS_AMPS_PER_VOLT
#  define BIBA_IS_AMPS_PER_VOLT        1.0f
#endif

/* --- Battery / ADC ------------------------------------------------------ */

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

/* Drive mode switch: low position → MANUAL, else → STABILIZED. */
#ifndef BIBA_DRIVE_MODE_LOW_THRESHOLD
#  define BIBA_DRIVE_MODE_LOW_THRESHOLD   (-0.3f)
#endif

/* Deadband below which throttle/steering are not considered active. */
#ifndef BIBA_MOTOR_DEADBAND
#  define BIBA_MOTOR_DEADBAND               0.05f
#endif

/* Motor direction inversion (1 = normal, -1 = inverted).
 * Mirror MOTOR1_INVERTED / MOTOR2_INVERTED from biba-controller/config.py. */
#ifndef BIBA_LEFT_MOTOR_DIR
#  define BIBA_LEFT_MOTOR_DIR    1
#endif
#ifndef BIBA_RIGHT_MOTOR_DIR
#  define BIBA_RIGHT_MOTOR_DIR  (-1)
#endif

/* Motor trim channel: trim_ch * MAX_EFFECT applied post-mix.
 * Positive trim → attenuate right motor, negative → attenuate left. */
#ifndef BIBA_MOTOR_TRIM_MAX_EFFECT
#  define BIBA_MOTOR_TRIM_MAX_EFFECT        0.30f
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

/* --- Motor output ramp (open-loop duty slew limiter) -------------------- */
/* Mirror RAMP_* from biba-controller/config.py. Not feature-gated —
 * these are critical for smooth motor control in all modes.            */
#ifndef BIBA_RAMP_ACCEL_RATE
#  define BIBA_RAMP_ACCEL_RATE           2.0f
#endif
#ifndef BIBA_RAMP_DECEL_RATE
#  define BIBA_RAMP_DECEL_RATE           2.0f
#endif
#ifndef BIBA_RAMP_REVERSE_DECEL_RATE
#  define BIBA_RAMP_REVERSE_DECEL_RATE   0.5f
#endif
#ifndef BIBA_RAMP_ZERO_HOLD_MS
#  define BIBA_RAMP_ZERO_HOLD_MS         150u
#endif

/* --- Motor / RPM calibration -------------------------------------------- */
/* MY1016Z3 24V 350W, 2-pole 4-brush, G=9:1 planetary gearbox,
 * N_comm=16 commutator bars.
 * Verified: 798.4 Hz @ 329 RPM wheel → G*N = 144.0 (1.1% err vs 145.6) */
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
/* Not feature-gated per D-05 — blackbox does not affect the signal chain;
 * recording is controlled by CH7 switch at runtime. */

#ifndef BIBA_BLACKBOX_RATE_HZ
#  define BIBA_BLACKBOX_RATE_HZ      25
#endif
#ifndef BIBA_BLACKBOX_FIELD_MASK
#  define BIBA_BLACKBOX_FIELD_MASK   0xFFFFu
#endif
#ifndef BIBA_BLACKBOX_MIN_FREE_KB
#  define BIBA_BLACKBOX_MIN_FREE_KB  64u
#endif
#ifndef BIBA_CH_BLACKBOX
#  define BIBA_CH_BLACKBOX  6   /* CH7 */
#endif


/* ========================================================================
 * FEATURE TOGGLES
 *
 * Each feature below has a BIBA_FEATURE_<NAME> toggle (default 1 = enabled)
 * and all its configuration parameters grouped in a named section.
 * Set any toggle to 0 in target_config.h to disable that feature.
 *
 * When BIBA_FEATURE_RPM_CLOSED_LOOP=0, ALL RPM sub-features (ZC, spectral,
 * dual-window, load gate, DR, PI, anti-stall) are disabled regardless of
 * their individual toggle settings.
 * ======================================================================== */

/* --- Backward compatibility: BIBA_OPEN_LOOP → RPM_CLOSED_LOOP=0 --------- */
#ifdef BIBA_OPEN_LOOP
#  warning "BIBA_OPEN_LOOP is deprecated. Use BIBA_FEATURE_RPM_CLOSED_LOOP=0 instead."
#  undef  BIBA_FEATURE_RPM_CLOSED_LOOP
#  define BIBA_FEATURE_RPM_CLOSED_LOOP 0
#endif

/* --- Feature: RPM Closed-Loop Master ----------------------------------- */
#ifndef BIBA_FEATURE_RPM_CLOSED_LOOP
#  define BIBA_FEATURE_RPM_CLOSED_LOOP   1
#endif

/* --- Feature: RPM ZC Detector ------------------------------------------ */
#ifndef BIBA_FEATURE_RPM_ZC
#  define BIBA_FEATURE_RPM_ZC            1
#endif
#ifndef ZC_SUBWIN_K
#  define ZC_SUBWIN_K                    8u
#endif
#ifndef ZC_SUBWIN_MIN_PKPK
#  define ZC_SUBWIN_MIN_PKPK             120u
#endif
#ifndef ZC_SUBWIN_MIN_STD
#  define ZC_SUBWIN_MIN_STD              40.0f
#endif
#ifndef ZC_MIN_VALID_HZ
#  define ZC_MIN_VALID_HZ                50.0f
#endif
#ifndef ZC_EMA_ALPHA
#  define ZC_EMA_ALPHA                   0.7f
#endif

/* --- Feature: RPM Spectral Estimator ----------------------------------- */
#ifndef BIBA_FEATURE_RPM_SPECTRAL
#  define BIBA_FEATURE_RPM_SPECTRAL      1
#endif
#ifndef BIBA_RPM_SPECTRAL_MIN_TARGET_HZ
#  define BIBA_RPM_SPECTRAL_MIN_TARGET_HZ      50.0f
#endif
#ifndef BIBA_RPM_SPECTRAL_MAX_TARGET_HZ
#  define BIBA_RPM_SPECTRAL_MAX_TARGET_HZ    1200.0f
#endif
#ifndef BIBA_RPM_SPECTRAL_REL_BAND
#  define BIBA_RPM_SPECTRAL_REL_BAND           0.35f
#endif
#ifndef BIBA_RPM_SPECTRAL_ABS_BAND_HZ
#  define BIBA_RPM_SPECTRAL_ABS_BAND_HZ        80.0f
#endif
#ifndef BIBA_RPM_SPECTRAL_MIN_PEAK_AMP_LSB
#  define BIBA_RPM_SPECTRAL_MIN_PEAK_AMP_LSB   45.0f
#endif
#ifndef BIBA_RPM_SPECTRAL_MIN_QUALITY
#  define BIBA_RPM_SPECTRAL_MIN_QUALITY         3.0f
#endif

/* --- Feature: RPM Dual-Window Search ----------------------------------- */
#ifndef BIBA_FEATURE_RPM_DUAL_WINDOW
#  define BIBA_FEATURE_RPM_DUAL_WINDOW   1
#endif

/* --- Feature: RPM IS-Pin Load Gate (Phase 11) -------------------------- */
#ifndef BIBA_FEATURE_RPM_LOAD_GATE
#  define BIBA_FEATURE_RPM_LOAD_GATE     1
#endif
#ifndef BIBA_RPM_LOAD_RATIO_THRESH
#  define BIBA_RPM_LOAD_RATIO_THRESH     1.5f   /* ratio = mean_IS_primary / mean_IS_other */
#endif
#ifndef BIBA_RPM_LOAD_QUALITY_MAX
#  define BIBA_RPM_LOAD_QUALITY_MAX      10.0f  /* gate fires only when quality < this */
#endif
#ifndef BIBA_RPM_LOAD_ABS_THRESH_ADC
#  define BIBA_RPM_LOAD_ABS_THRESH_ADC   3800u  /* absolute ADC count fallback gate (D-A3) */
#endif

/* --- Feature: RPM Dead Reckoning --------------------------------------- */
#ifndef BIBA_FEATURE_RPM_DR
#  define BIBA_FEATURE_RPM_DR            1
#endif
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

/* --- Feature: RPM PI Controller ---------------------------------------- */
#ifndef BIBA_FEATURE_RPM_PI
#  define BIBA_FEATURE_RPM_PI            1
#endif
#ifndef BIBA_RPM_PI_KP
#  define BIBA_RPM_PI_KP                 0.003f
#endif
#ifndef BIBA_RPM_PI_KI
#  define BIBA_RPM_PI_KI                 0.010f
#endif
#ifndef BIBA_RPM_PI_KI_LOW
#  define BIBA_RPM_PI_KI_LOW             0.005f
#endif
#ifndef BIBA_RPM_PI_KI_LOW_THRESH
#  define BIBA_RPM_PI_KI_LOW_THRESH      200.0f
#endif
#ifndef BIBA_RPM_PI_FF_SLOPE
#  define BIBA_RPM_PI_FF_SLOPE           10.13f
#endif
#ifndef BIBA_RPM_PI_FF_DEAD
#  define BIBA_RPM_PI_FF_DEAD            74.6f
#endif
#ifndef BIBA_RPM_PI_STICTION
#  define BIBA_RPM_PI_STICTION           0.15f
#endif
#ifndef BIBA_RPM_PI_P_CLAMP
#  define BIBA_RPM_PI_P_CLAMP            0.20f
#endif
#ifndef BIBA_RPM_PI_DT_S
#  define BIBA_RPM_PI_DT_S               0.104f
#endif

/* --- Feature: RPM Anti-Stall (Phase 11) -------------------------------- */
#ifndef BIBA_FEATURE_RPM_ANTI_STALL
#  define BIBA_FEATURE_RPM_ANTI_STALL    1
#endif
#ifndef BIBA_ANTISTALL_RAMP_STEP
#  define BIBA_ANTISTALL_RAMP_STEP       0.02f   /* +2% duty per window (~200ms) */
#endif
#ifndef BIBA_ANTISTALL_MAX_DUTY
#  define BIBA_ANTISTALL_MAX_DUTY        0.60f   /* cap at 60% */
#endif
#ifndef BIBA_ANTISTALL_CONFIRM
#  define BIBA_ANTISTALL_CONFIRM            2u   /* 2 consecutive HIGH_LOAD windows */
#endif

/* --- Feature: BTS7960 Latch Recovery ----------------------------------- */
#ifndef BIBA_FEATURE_LATCH_RECOVERY
#  define BIBA_FEATURE_LATCH_RECOVERY    1
#endif
#ifndef BIBA_LATCH_IS_RAW_MIN
#  define BIBA_LATCH_IS_RAW_MIN          3500u  /* ≈2.82 V; latch saturates ADC to 4095 */
#endif
#ifndef BIBA_LATCH_BLOCKS_CONFIRM
#  define BIBA_LATCH_BLOCKS_CONFIRM         3u  /* 3 × ~51 ms DMA window ≈ 150 ms */
#endif
#ifndef BIBA_LATCH_COOLDOWN_WINDOWS
#  define BIBA_LATCH_COOLDOWN_WINDOWS      20u  /* 20 × ~51 ms ≈ 1 s spin-up grace */
#endif

/* --- Feature: Per-Motor Current/Power Limiter -------------------------- */
#ifndef BIBA_FEATURE_CURRENT_LIMITER
#  define BIBA_FEATURE_CURRENT_LIMITER   1
#endif
#ifndef BIBA_LEFT_MAX_CURRENT_A
#  define BIBA_LEFT_MAX_CURRENT_A        18.0f
#endif
#ifndef BIBA_RIGHT_MAX_CURRENT_A
#  define BIBA_RIGHT_MAX_CURRENT_A       18.0f
#endif
#ifndef BIBA_LEFT_MAX_POWER_W
#  define BIBA_LEFT_MAX_POWER_W          180.0f
#endif
#ifndef BIBA_RIGHT_MAX_POWER_W
#  define BIBA_RIGHT_MAX_POWER_W         180.0f
#endif
#ifndef BIBA_FALLBACK_SUPPLY_V
#  define BIBA_FALLBACK_SUPPLY_V         24.0f
#endif

/* --- Feature: Steering Deadband ---------------------------------------- */
#ifndef BIBA_FEATURE_STEERING_DEADBAND
#  define BIBA_FEATURE_STEERING_DEADBAND 1
#endif
#ifndef BIBA_STEERING_DEADBAND
#  define BIBA_STEERING_DEADBAND         0.20f
#endif

/* --- Feature: RPM Setpoint Ramp ---------------------------------------- */
#ifndef BIBA_FEATURE_RPM_RAMP
#  define BIBA_FEATURE_RPM_RAMP          1
#endif
#ifndef BIBA_RPM_SETPOINT_ACCEL_RATE
#  define BIBA_RPM_SETPOINT_ACCEL_RATE   2.0f
#endif
#ifndef BIBA_RPM_SETPOINT_DECEL_RATE
#  define BIBA_RPM_SETPOINT_DECEL_RATE   1.0f
#endif
#ifndef BIBA_RPM_SETPOINT_REVERSE_DECEL_RATE
#  define BIBA_RPM_SETPOINT_REVERSE_DECEL_RATE 0.5f
#endif
#ifndef BIBA_RPM_SETPOINT_ZERO_HOLD_MS
#  define BIBA_RPM_SETPOINT_ZERO_HOLD_MS 150u
#endif

/* --- Feature: Motor Coil Melodies -------------------------------------- */
#ifndef BIBA_FEATURE_MELODY
#  define BIBA_FEATURE_MELODY            1
#endif

/* --- Feature: Reverse Backup Pip --------------------------------------- */
/* Migration: old BIBA_REVERSE_PIP_ENABLED → BIBA_FEATURE_REVERSE_PIP.
 * The old name is still accepted for backward compat. */
#ifdef BIBA_REVERSE_PIP_ENABLED
#  undef  BIBA_FEATURE_REVERSE_PIP
#  define BIBA_FEATURE_REVERSE_PIP       BIBA_REVERSE_PIP_ENABLED
#endif
#ifndef BIBA_FEATURE_REVERSE_PIP
#  define BIBA_FEATURE_REVERSE_PIP       0
#endif
#ifndef BIBA_REVERSE_PIP_INTERVAL_MS
#  define BIBA_REVERSE_PIP_INTERVAL_MS   600u
#endif

/* --- Feature: Heading Hold --------------------------------------------- */
#ifndef BIBA_FEATURE_HEADING_HOLD
#  define BIBA_FEATURE_HEADING_HOLD      1
#endif

/* --- Feature: Speed Mode (3-position switch scaling) ------------------- */
#ifndef BIBA_FEATURE_SPEED_MODE
#  define BIBA_FEATURE_SPEED_MODE        1
#endif
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

/* --- Feature: Mixer L∞ Ball Projection --------------------------------- */
#ifndef BIBA_FEATURE_MIXER_PROJECTION
#  define BIBA_FEATURE_MIXER_PROJECTION  1
#endif


/* ========================================================================
 * DEPENDENCY VALIDATION
 *
 * #error checks at the bottom of biba_config.h — after all toggles
 * and target_config.h overrides are resolved — catch illegal combinations
 * at compile time.
 *
 * When BIBA_FEATURE_RPM_CLOSED_LOOP=0, dependency checks are skipped
 * because all RPM sub-features are implicitly disabled.
 * ======================================================================== */

#if BIBA_FEATURE_RPM_CLOSED_LOOP

#  if BIBA_FEATURE_RPM_PI && !BIBA_FEATURE_RPM_DR
#    error "BIBA_FEATURE_RPM_PI requires BIBA_FEATURE_RPM_DR (PI uses DR as measurement source)"
#  endif

#  if BIBA_FEATURE_RPM_DUAL_WINDOW && !BIBA_FEATURE_RPM_SPECTRAL
#    error "BIBA_FEATURE_RPM_DUAL_WINDOW requires BIBA_FEATURE_RPM_SPECTRAL (hint is a second Goertzel search)"
#  endif

#  if BIBA_FEATURE_RPM_LOAD_GATE && !BIBA_FEATURE_RPM_SPECTRAL
#    error "BIBA_FEATURE_RPM_LOAD_GATE requires BIBA_FEATURE_RPM_SPECTRAL (gate applied to spectral result)"
#  endif

#  if BIBA_FEATURE_RPM_ANTI_STALL && !BIBA_FEATURE_RPM_SPECTRAL
#    error "BIBA_FEATURE_RPM_ANTI_STALL requires BIBA_FEATURE_RPM_SPECTRAL (uses HIGH_LOAD from spectral)"
#  endif

#endif /* BIBA_FEATURE_RPM_CLOSED_LOOP */

#endif /* BIBA_CONFIG_H */
