#ifndef BIBA_IMU_H
#define BIBA_IMU_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int16_t gyro_x_cdps;
    int16_t gyro_y_cdps;
    int16_t gyro_z_cdps;
    int16_t accel_x_mg;
    int16_t accel_y_mg;
    int16_t accel_z_mg;
    bool    valid;
} biba_imu_sample_t;

/* Probe the IMU on I2C1; returns true when at least one known chip id is
 * detected (BMI160 or LSM6DS3). */
bool biba_imu_probe(void);

/* Pull the latest sample over I2C. Returns false on bus error; the caller
 * should treat the last sample as stale in that case. */
bool biba_imu_read(biba_imu_sample_t *out);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_IMU_H */
