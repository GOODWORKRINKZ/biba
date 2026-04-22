#ifndef BIBA_TARGET_CONFIG_H
#define BIBA_TARGET_CONFIG_H

/* Target-specific overrides for BIBA_F103_REV_A.
 *
 * The Rev A prototype has a dedicated op-amp on each IS line, so the
 * volts-to-amperes scale is different from the stock Blue Pill setup.
 * Every constant here overrides the fallback in
 * include/biba_config.h. */

/* Dedicated op-amp: 0 V at 0 A, 0.1 V per ampere (10 A / V). */
#define BIBA_IS_ZERO_OFFSET_V        0.0f
#define BIBA_IS_AMPS_PER_VOLT        10.0f

/* 1:20 battery divider for up to ~66 V packs. */
#define BIBA_VBAT_DIVIDER_RATIO      20.0f

/* Tighter current limits because the Rev A board uses 5 mΩ shunts. */
#define BIBA_LEFT_MAX_CURRENT_A      25.0f
#define BIBA_RIGHT_MAX_CURRENT_A     25.0f

#endif /* BIBA_TARGET_CONFIG_H */
