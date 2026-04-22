#ifndef BIBA_HAL_H
#define BIBA_HAL_H

/* Thin HAL facade over STM32Cube. Only the calls actually needed by BiBa
 * are exposed; the firmware never touches stm32f1xx_hal.h directly.
 *
 * This header is safe to include in files that end up in the native_test
 * build — the inline function bodies live in biba_hal.c which is only
 * added to the firmware envs via platformio.ini src_filter. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --- Core clock & tick --------------------------------------------------- */

/* Bring up the system clock (72 MHz from HSE PLL), enable peripheral clocks,
 * release JTAG to get PB3/PB4/PA15 as regular GPIOs, and initialise the
 * HAL tick source. Must be the very first call in main. */
void biba_hal_init(void);

/* Milliseconds since boot (monotonic). */
uint32_t biba_hal_now_ms(void);

/* Busy-wait. Only acceptable during bring-up / error LED patterns. */
void biba_hal_delay_ms(uint32_t ms);

/* --- GPIO ---------------------------------------------------------------- */

void biba_hal_status_led_set(bool on);

/* Raise/lower the DATA_READY line to the SBC. */
void biba_hal_data_ready_set(bool on);
void biba_hal_data_ready_pulse(void);

/* Latched MODE_SEL sample captured during biba_hal_init(). true = companion. */
bool biba_hal_mode_sel_is_companion(void);

/* BTS7960 enables, high-level. */
void biba_hal_left_enable(bool enabled);
void biba_hal_right_enable(bool enabled);

/* --- Motor PWM (TIM1_CH1..CH4) ------------------------------------------ */

/* `duty` is [-1.0, 1.0]. Negative drives LPWM, positive drives RPWM. */
void biba_hal_motor_pwm_left(float duty);
void biba_hal_motor_pwm_right(float duty);

/* --- ADC scan ----------------------------------------------------------- */

/* Fetch the latest 12-bit sample from the circular DMA scan buffer for
 * the given logical ADC channel index (BIBA_ADC_CHAN_*). */
uint16_t biba_hal_adc_sample(unsigned channel_index);

/* Count of completed scans since boot (rolls over). Used by telemetry to
 * detect fresh data for the DATA_READY line. */
uint32_t biba_hal_adc_scan_count(void);

/* Convert a raw ADC sample into volts at the pin. */
float biba_hal_adc_volts(uint16_t raw);

/* --- USART3 DMA (CRSF) -------------------------------------------------- */

/* Start DMA idle-line receive into an internal ring buffer. */
void biba_hal_crsf_begin(uint32_t baud);

/* Copy up to `cap` bytes of received data into `dst`. Returns the number
 * of bytes copied. */
size_t biba_hal_crsf_read(uint8_t *dst, size_t cap);

/* --- SPI2 slave --------------------------------------------------------- */

/* Prepare for the next SPI transaction. `tx` is the telemetry frame that
 * will be clocked out over MISO; `rx` receives the command frame from
 * MOSI. Both buffers must be BIBA_PROTO_FRAME_SIZE bytes. */
void biba_hal_spi_slave_arm(const uint8_t *tx, uint8_t *rx);

/* Non-blocking check: returns true if the previously armed transfer has
 * completed. Host driver clears the flag by calling biba_hal_spi_slave_arm
 * with the next buffers. */
bool biba_hal_spi_slave_poll(void);

/* --- I2C1 (IMU) --------------------------------------------------------- */

bool biba_hal_i2c_write(uint8_t addr, const uint8_t *data, size_t len);
bool biba_hal_i2c_read(uint8_t addr, uint8_t reg, uint8_t *data, size_t len);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_HAL_H */
