#ifndef BIBA_ADS1115_H
#define BIBA_ADS1115_H

/* ADS1115 — 16-bit I2C ADC driver (Texas Instruments).
 *
 * Operates in single-shot mode.  Each call to ads1115_read_channel_v()
 * triggers one conversion on the requested channel and blocks until the
 * result is ready (~8 ms at 128 SPS).
 *
 * I2C address is selected by the ADDR pin:
 *   GND → 0x48   VDD → 0x49   SDA → 0x4A   SCL → 0x4B
 *
 * BiBa wiring: ADDR → GND → address = 0x48.
 * PGA setting: ±4.096 V FSR (PGA=001b) — covers IS-pin range up to ~34.8 A
 * with RIS = 1 kΩ (VIS = IL / 8.5 V).
 */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Default I2C address (ADDR pin → GND). */
#define ADS1115_ADDR        0x48u

/* PGA / FSR selector values (passed to ads1115_init as fsr_setting). */
#define ADS1115_FSR_6144MV  0u   /* PGA = 000b → ±6.144 V (input capped at VDD+0.3V) */
#define ADS1115_FSR_4096MV  1u   /* PGA = 001b → ±4.096 V — used for BTS7960 IS pins */
#define ADS1115_FSR_2048MV  2u   /* PGA = 010b → ±2.048 V (power-on default) */
#define ADS1115_FSR_1024MV  3u   /* PGA = 011b → ±1.024 V */
#define ADS1115_FSR_512MV   4u   /* PGA = 100b → ±0.512 V */
#define ADS1115_FSR_256MV   5u   /* PGA = 101b → ±0.256 V */

/* Channel indices for single-ended measurements (AINx vs GND). */
#define ADS1115_CH0         0u
#define ADS1115_CH1         1u
#define ADS1115_CH2         2u
#define ADS1115_CH3         3u

/* Initialise the ADS1115 at the given I2C address.
 * fsr_setting: one of ADS1115_FSR_* constants above.
 * Returns true if the device ACKs on I2C (present and responsive). */
bool ads1115_init(uint8_t addr, uint8_t fsr_setting);

/* Trigger a single-shot conversion on the given channel and return the
 * voltage at the pin (volts, float).  Blocks ~8 ms for conversion.
 *
 * channel: ADS1115_CH0 … ADS1115_CH3
 * out_v:   pointer to float that receives the result.
 * Returns true on success; false if I2C communication failed. */
bool ads1115_read_channel_v(uint8_t addr, uint8_t channel, float *out_v);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_ADS1115_H */
