#ifndef BIBA_TARGET_CONFIG_H
#define BIBA_TARGET_CONFIG_H

/* Target-specific overrides for RPICO_RP2040.
 *
 * RP2040 runs at 125 MHz (PLL configured by pico-sdk before main).
 * ADC is 12-bit / 3.3 V reference — same as STM32, no override needed.
 * No per-motor current sense on this target; limits are unchanged. */

#define BIBA_SYS_CLOCK_HZ            125000000u
#define BIBA_PWM_FREQUENCY_HZ        20000   /* 20 kHz carrier, above audible */

/* No dedicated IS op-amp; leave zero offset/gain defaults from
 * biba_config.h — callers that read aliased current channels will get
 * voltage-rail data but won't crash. */

#endif /* BIBA_TARGET_CONFIG_H */
