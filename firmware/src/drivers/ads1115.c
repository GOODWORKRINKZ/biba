#include "ads1115.h"

#ifndef BIBA_NATIVE_TEST

#include "hal/biba_hal.h"
#include "pico/stdlib.h"   /* sleep_ms() */

/* ADS1115 register pointers. */
#define REG_CONVERSION  0x00u
#define REG_CONFIG      0x01u

/* Config register bit positions. */
#define CFG_OS_BIT      15u   /* write 1 to start single-shot conversion      */
#define CFG_MUX_SHIFT   12u   /* MUX[2:0] bits 14:12                          */
#define CFG_PGA_SHIFT    9u   /* PGA[2:0] bits 11:9                           */
#define CFG_MODE_BIT     8u   /* 1 = single-shot (power-down when done)       */
#define CFG_DR_SHIFT     5u   /* DR[2:0]  bits 7:5  — data rate               */
#define CFG_DR_128SPS    4u   /* DR=100b → 128 samples/s (~7.8 ms/conversion) */

/* MUX codes for single-ended channels vs GND (bits 14:12). */
static const uint8_t s_mux_se[4] = { 4u, 5u, 6u, 7u };

/* Stored FSR setting (PGA bits 11:9) — same for all channels. */
static uint8_t s_pga_bits;

/* Voltage scale per LSB at the stored FSR (V / count). */
static float s_lsb_v;

/* Full-scale voltages corresponding to ADS1115_FSR_* index (V). */
static const float s_fsr_lsb[6] = {
    6.144f / 32768.0f,   /* ADS1115_FSR_6144MV */
    4.096f / 32768.0f,   /* ADS1115_FSR_4096MV */
    2.048f / 32768.0f,   /* ADS1115_FSR_2048MV */
    1.024f / 32768.0f,   /* ADS1115_FSR_1024MV */
    0.512f / 32768.0f,   /* ADS1115_FSR_512MV  */
    0.256f / 32768.0f,   /* ADS1115_FSR_256MV  */
};

/* --- Helpers ------------------------------------------------------------ */

static bool write_config(uint8_t addr, uint16_t cfg)
{
    uint8_t buf[3];
    buf[0] = REG_CONFIG;
    buf[1] = (uint8_t)(cfg >> 8u);
    buf[2] = (uint8_t)(cfg & 0xFFu);
    return biba_hal_i2c_write(addr, buf, 3u);
}

static bool read_conversion(uint8_t addr, int16_t *raw)
{
    uint8_t buf[2];
    if (!biba_hal_i2c_read(addr, REG_CONVERSION, buf, 2u)) {
        return false;
    }
    *raw = (int16_t)((uint16_t)(buf[0]) << 8u | buf[1]);
    return true;
}

static bool poll_ready(uint8_t addr)
{
    /* Poll OS bit in config register — it reads 1 when conversion is done. */
    uint8_t buf[2];
    for (int i = 0; i < 20; i++) {
        if (!biba_hal_i2c_read(addr, REG_CONFIG, buf, 2u)) {
            return false;
        }
        if (buf[0] & 0x80u) {   /* OS = bit 15, in MSB of 16-bit config */
            return true;
        }
        sleep_ms(1);
    }
    return false;  /* timed out */
}

/* --- Public API --------------------------------------------------------- */

bool ads1115_init(uint8_t addr, uint8_t fsr_setting)
{
    if (fsr_setting > 5u) {
        fsr_setting = 2u;  /* fall back to ±2.048 V default */
    }
    s_pga_bits = fsr_setting;
    s_lsb_v    = s_fsr_lsb[fsr_setting];

    /* Write a benign config (power-down / default) to verify the device ACKs. */
    uint16_t cfg = (1u << CFG_OS_BIT)
                 | ((uint16_t)s_mux_se[0] << CFG_MUX_SHIFT)
                 | ((uint16_t)s_pga_bits  << CFG_PGA_SHIFT)
                 | (1u << CFG_MODE_BIT)
                 | ((uint16_t)CFG_DR_128SPS << CFG_DR_SHIFT);
    return write_config(addr, cfg);
}

bool ads1115_read_channel_v(uint8_t addr, uint8_t channel, float *out_v)
{
    if (channel > 3u || out_v == NULL) {
        return false;
    }

    /* Build config: start single-shot conversion on the requested channel. */
    uint16_t cfg = (1u << CFG_OS_BIT)
                 | ((uint16_t)s_mux_se[channel] << CFG_MUX_SHIFT)
                 | ((uint16_t)s_pga_bits         << CFG_PGA_SHIFT)
                 | (1u << CFG_MODE_BIT)
                 | ((uint16_t)CFG_DR_128SPS << CFG_DR_SHIFT);

    if (!write_config(addr, cfg)) {
        return false;
    }

    /* Wait for conversion to complete. */
    if (!poll_ready(addr)) {
        return false;
    }

    int16_t raw = 0;
    if (!read_conversion(addr, &raw)) {
        return false;
    }

    *out_v = (float)raw * s_lsb_v;
    return true;
}

/* --- Native test stubs -------------------------------------------------- */

#else /* BIBA_NATIVE_TEST */

bool ads1115_init(uint8_t addr, uint8_t fsr_setting)
{
    (void)addr; (void)fsr_setting;
    return true;
}

bool ads1115_read_channel_v(uint8_t addr, uint8_t channel, float *out_v)
{
    (void)addr; (void)channel;
    if (out_v) *out_v = 0.0f;
    return true;
}

#endif /* BIBA_NATIVE_TEST */