#ifndef BIBA_TARGET_CONFIG_H
#define BIBA_TARGET_CONFIG_H

/* Target-specific overrides for BLUEPILL_F103C8_CLONE.
 *
 * Same calibration constants as the genuine Blue Pill rig.
 * Note: right-motor current sense is unavailable on this target
 * (PA2/PA3 are used for USART2 CRSF). */

#define BIBA_IS_ZERO_OFFSET_V        0.10f
#define BIBA_IS_AMPS_PER_VOLT        8.5f
#define BIBA_VBAT_DIVIDER_RATIO      11.0f

#endif /* BIBA_TARGET_CONFIG_H */
