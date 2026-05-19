#ifndef BIBA_AHT30_H
#define BIBA_AHT30_H

/* AHT30 — I2C temperature and humidity sensor driver.
 *
 * Fixed I2C address: 0x38.
 * Shares I2C0 (GP20/GP21) with the IMU (0x68/0x6A) and ADS1115 (0x48).
 * No address conflict.
 *
 * Measurement time: ~80 ms per reading.  Call from the low-rate telemetry
 * path (1 Hz), not from the 500 Hz control loop.
 */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AHT30_ADDR  0x38u

/* Initialise the AHT30.  Sends the initialization command and waits 10 ms.
 * Returns true on success. */
bool aht30_init(void);

/* Trigger a measurement and read temperature and humidity.
 * Blocks ~80 ms for the conversion.
 *
 * temp_c:        pointer to float for temperature in °C (–50 … +150°C range).
 * humidity_pct:  pointer to float for relative humidity 0–100 %.
 * Returns true on success; false if I2C communication failed or sensor busy. */
bool aht30_read(float *temp_c, float *humidity_pct);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_AHT30_H */
