#ifndef BIBA_TARGET_CONFIG_H
#define BIBA_TARGET_CONFIG_H

/* Tunables for the PWM → CRSF bridge (PWM2CRSF_RP2040).
 *
 * Everything here can be overridden with -D in platformio.ini. */

/* CRSF link towards BiBa. Must match BIBA_CRSF_BAUD in biba_config.h. */
#ifndef PWM2CRSF_CRSF_BAUD
#  define PWM2CRSF_CRSF_BAUD           420000u
#endif

/* RC frame rate. BiBa fails safe after BIBA_CRSF_TIMEOUT_MS (500 ms);
 * 100 Hz is well above the ~50 Hz a PWM receiver refreshes at. */
#ifndef PWM2CRSF_RC_PERIOD_MS
#  define PWM2CRSF_RC_PERIOD_MS        10u
#endif
#ifndef PWM2CRSF_LINK_STATS_PERIOD_MS
#  define PWM2CRSF_LINK_STATS_PERIOD_MS 200u
#endif

/* Receiver endpoints: these pulse widths become full -1 / +1 on BiBa.
 * Calibrate by watching the USB debug output while moving each stick
 * to its ends. */
#ifndef PWM2CRSF_MIN_US
#  define PWM2CRSF_MIN_US              1000u
#endif
#ifndef PWM2CRSF_MAX_US
#  define PWM2CRSF_MAX_US              2000u
#endif

/* Glitch filter: pulses outside this window are ignored. */
#ifndef PWM2CRSF_VALID_MIN_US
#  define PWM2CRSF_VALID_MIN_US        800u
#endif
#ifndef PWM2CRSF_VALID_MAX_US
#  define PWM2CRSF_VALID_MAX_US        2200u
#endif

/* No valid pulse on a mapped input for this long → stop sending RC
 * frames. BiBa then enters its own failsafe after 500 ms more. */
#ifndef PWM2CRSF_INPUT_TIMEOUT_MS
#  define PWM2CRSF_INPUT_TIMEOUT_MS    100u
#endif

/* CRSF channel ← PWM input map (0-based input index, -1 = unmapped).
 *
 * HotRC: PWM1/PWM2 are the two control axes (wheel = steering,
 * trigger = throttle), PWM3..PWM6 are buttons. Mapped onto the channels
 * BiBa actually reads in mode_standalone.c (biba_config.h BIBA_CH_*):
 *
 *   CRSF CH2  throttle    ← PWM2 (trigger)
 *   CRSF CH4  steering    ← PWM1 (wheel)
 *   CRSF CH5  ARM         ← PWM3 (button)   > 0.3 armed
 *   CRSF CH6  speed mode  ← PWM4 (button)   each press 1 → 2 → 3 → 1
 *   CRSF CH8  beacon      ← PWM6 (button)
 *   CRSF CH10 drive mode  ← PWM5 (button)   low = MANUAL, high = heading hold
 *
 * CH1 and CH3 carry no function on BiBa (only the trim gesture, which
 * needs CH1..CH4 all at full and is unreachable with a HotRC anyway).
 * CH7 (blackbox) and CH9 (trim) are left at constants — there are only
 * four buttons; swap PWM6 onto CH7 if blackbox matters more than beacon. */
#ifndef PWM2CRSF_CHANNEL_MAP
#  define PWM2CRSF_CHANNEL_MAP {                                  \
      -1,  1, -1,  0,         /* CH1 -,   CH2 thr,   CH3 -,  CH4 steer  */ \
       2,  3, -1,  5,         /* CH5 arm, CH6 speed, CH7 bb, CH8 beacon */ \
      -1,  4,                 /* CH9 trim, CH10 drive mode */           \
      -1, -1, -1, -1, -1, -1  /* CH11..CH16 unused by BiBa */           \
   }
#endif

/* Values sent on unmapped channels:
 *   CH1/CH3  992 → neutral (also keeps the trim gesture impossible)
 *   CH7      172 → blackbox recording off
 *   CH9      992 → no trim */
#ifndef PWM2CRSF_IDLE_VALUES
#  define PWM2CRSF_IDLE_VALUES {                                  \
       992,  992,  992,  992,  992,  992,                          \
       172,  172,  992,  172,                                      \
       992,  992,  992,  992,  992,  992                           \
   }
#endif

/* Bit i mirrors PWM input i+1 around 1500 µs. Use it when the HotRC
 * wheel turns BiBa the wrong way (bit 0), the trigger is backwards
 * (bit 1), or a button reads "on" in its released state (bits 2..5) —
 * ARM must be LOW with the button released. Prefer the transmitter's
 * own channel reverse if it has one. Example: (1u << 0) | (1u << 2). */
#ifndef PWM2CRSF_INPUT_INVERT_MASK
#  define PWM2CRSF_INPUT_INVERT_MASK   0u
#endif

/* Speed button: each press on PWM4 steps BiBa's speed mode
 * slow (1/3) → medium (2/3) → fast → slow. CH6 carries 172 / 992 / 1811,
 * which BiBa splits at ±0.3. Boots and recovers from failsafe in slow.
 * Set PWM2CRSF_SPEED_BUTTON_INPUT to -1 to pass PWM4 straight through. */
#ifndef PWM2CRSF_SPEED_BUTTON_INPUT
#  define PWM2CRSF_SPEED_BUTTON_INPUT     3    /* PWM4, 0-based */
#endif
#ifndef PWM2CRSF_SPEED_CRSF_CH
#  define PWM2CRSF_SPEED_CRSF_CH          5    /* CH6, 0-based = BIBA_CH_SPEED_MODE */
#endif
#ifndef PWM2CRSF_SPEED_STEPS
#  define PWM2CRSF_SPEED_STEPS            3u
#endif
/* 1: button latches (every press flips 1000 <-> 2000) → count both edges.
 * 0: momentary (2000 only while held) → count presses only.
 * Check the USB log: one press jumps two steps → set 0;
 * two presses per step → set 1. */
#ifndef PWM2CRSF_SPEED_BUTTON_LATCHING
#  define PWM2CRSF_SPEED_BUTTON_LATCHING  1
#endif

/* Button level hysteresis (µs) and debounce (ms). */
#ifndef PWM2CRSF_BUTTON_HIGH_US
#  define PWM2CRSF_BUTTON_HIGH_US         1700u
#endif
#ifndef PWM2CRSF_BUTTON_LOW_US
#  define PWM2CRSF_BUTTON_LOW_US          1300u
#endif
#ifndef PWM2CRSF_BUTTON_MIN_INTERVAL_MS
#  define PWM2CRSF_BUTTON_MIN_INTERVAL_MS 150u
#endif

/* Print pulse widths / link state over USB CDC twice a second. */
#ifndef PWM2CRSF_DEBUG_PRINT
#  define PWM2CRSF_DEBUG_PRINT         1
#endif
#ifndef PWM2CRSF_DEBUG_PERIOD_MS
#  define PWM2CRSF_DEBUG_PERIOD_MS     500u
#endif

#endif /* BIBA_TARGET_CONFIG_H */
