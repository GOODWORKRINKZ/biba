#include "aht30.h"

#ifndef BIBA_NATIVE_TEST

#include "hal/biba_hal.h"
#include "pico/stdlib.h"   /* sleep_ms() */

/* AHT30 command bytes. */
#define AHT30_CMD_INIT      0xBEu
#define AHT30_CMD_TRIGGER   0xACu
#define AHT30_CMD_STATUS    0x71u
#define AHT30_STATUS_BUSY   0x80u   /* bit 7 = busy flag */

bool aht30_init(void)
{
    /* Initialization command: 0xBE 0x08 0x00 */
    uint8_t cmd[3] = { AHT30_CMD_INIT, 0x08u, 0x00u };
    (void)biba_hal_i2c_write(AHT30_ADDR, cmd, 3u);
    sleep_ms(10u);
    return true;
}

bool aht30_read(float *temp_c, float *humidity_pct)
{
    if (!temp_c || !humidity_pct) {
        return false;
    }

    /* Trigger measurement: 0xAC 0x33 0x00 */
    uint8_t cmd[3] = { AHT30_CMD_TRIGGER, 0x33u, 0x00u };
    if (!biba_hal_i2c_write(AHT30_ADDR, cmd, 3u)) {
        return false;
    }

    /* Wait for measurement to complete (~80 ms). */
    sleep_ms(80u);

    /* Read 6 data bytes (status + 5 data).
     * Protocol: write status command byte 0x71, then read 6 bytes. */
    uint8_t status_cmd = AHT30_CMD_STATUS;
    if (!biba_hal_i2c_write(AHT30_ADDR, &status_cmd, 1u)) {
        return false;
    }

    uint8_t buf[6];
    /* Re-use biba_hal_i2c_read with a dummy register byte workaround:
     * The HAL function does a write of reg then a read.  For AHT30 the
     * status register read is a raw read with no sub-address, so we
     * issue a plain write of 0x71 above and then read directly. */
    uint8_t tmp_reg = AHT30_CMD_STATUS;
    if (!biba_hal_i2c_read(AHT30_ADDR, tmp_reg, buf, 6u)) {
        return false;
    }

    /* Check busy flag in status byte. */
    if (buf[0] & AHT30_STATUS_BUSY) {
        return false;
    }

    /* Humidity: 20-bit value, top 8 bits in buf[1], next 8 in buf[2],
     * top 4 bits of buf[3].
     * hum_raw = (buf[1] << 12) | (buf[2] << 4) | (buf[3] >> 4)
     * humidity_pct = hum_raw / 1048576.0 * 100.0 */
    uint32_t hum_raw = ((uint32_t)buf[1] << 12u)
                     | ((uint32_t)buf[2] << 4u)
                     | ((uint32_t)buf[3] >> 4u);
    *humidity_pct = (float)hum_raw / 1048576.0f * 100.0f;

    /* Temperature: 20-bit value, low 4 bits of buf[3], all of buf[4],
     * all of buf[5].
     * temp_raw = ((buf[3] & 0x0F) << 16) | (buf[4] << 8) | buf[5]
     * temp_c = temp_raw / 1048576.0 * 200.0 - 50.0 */
    uint32_t temp_raw = ((uint32_t)(buf[3] & 0x0Fu) << 16u)
                      | ((uint32_t)buf[4] << 8u)
                      | (uint32_t)buf[5];
    *temp_c = (float)temp_raw / 1048576.0f * 200.0f - 50.0f;

    return true;
}

/* --- Native test stubs -------------------------------------------------- */

#else /* BIBA_NATIVE_TEST */

bool aht30_init(void)
{
    return true;
}

bool aht30_read(float *temp_c, float *humidity_pct)
{
    if (temp_c)       *temp_c       = 25.0f;
    if (humidity_pct) *humidity_pct = 50.0f;
    return true;
}

#endif /* BIBA_NATIVE_TEST */
