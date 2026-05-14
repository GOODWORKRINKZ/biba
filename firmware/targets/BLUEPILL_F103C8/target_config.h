#ifndef BIBA_TARGET_CONFIG_H
#define BIBA_TARGET_CONFIG_H

/* Target-specific overrides for BLUEPILL_F103C8.
 *
 * This file is included *before* biba_config.h picks its defaults, so
 * anything defined here wins. Keep global policy (timeouts, protocol
 * version, etc.) in include/biba_config.h; keep per-board calibration
 * and current-sense tuning here. */

/* Current-sense calibration for a reference Blue Pill rig with
 * 1 kΩ pull-down on each BTS7960 IS pin (rated 8500:1 ratio). */
#define BIBA_IS_ZERO_OFFSET_V        0.10f
#define BIBA_IS_AMPS_PER_VOLT        8.5f

/* The reference Blue Pill build ships without a dedicated VBAT divider
 * tap, so the default 1:11 resistor ladder is assumed. */
#define BIBA_VBAT_DIVIDER_RATIO      11.0f

#endif /* BIBA_TARGET_CONFIG_H */
