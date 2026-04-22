/* Minimal IMU driver scaffolding. A detailed LSM6DS3 / BMI160 driver is
 * out of scope for the initial firmware drop — we only expose the API so
 * that the control loop and telemetry can call into it. The probe/read
 * functions return graceful defaults until the full driver lands. */

#include "imu.h"

#include <string.h>

#include "hal/biba_hal.h"

#define IMU_ADDR_LSM6DS3   0x6Au
#define IMU_REG_WHOAMI     0x0Fu
#define IMU_WHOAMI_LSM6DS3 0x69u
#define IMU_WHOAMI_BMI160  0xD1u

static bool s_present;

bool biba_imu_probe(void)
{
    uint8_t id = 0;
    s_present = false;
    if (biba_hal_i2c_read(IMU_ADDR_LSM6DS3, IMU_REG_WHOAMI, &id, 1)) {
        if (id == IMU_WHOAMI_LSM6DS3 || id == IMU_WHOAMI_BMI160) {
            s_present = true;
        }
    }
    return s_present;
}

bool biba_imu_read(biba_imu_sample_t *out)
{
    if (out == NULL) return false;
    memset(out, 0, sizeof(*out));
    if (!s_present) {
        return false;
    }
    /* TODO(stm32): read the 12-byte gyro+accel block and scale into
     * centi-degrees/sec and milli-g. Kept as a stub so the telemetry
     * path already produces a well-formed zero sample and downstream
     * integration work can iterate. */
    out->valid = true;
    return true;
}
