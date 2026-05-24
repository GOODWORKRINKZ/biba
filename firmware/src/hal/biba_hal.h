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
void biba_hal_delay_us(uint32_t us);

/* --- GPIO ---------------------------------------------------------------- */

void biba_hal_status_led_set(bool on);

/* RGB NeoPixel LED (WS2812).  No-op on targets without BIBA_HAS_RGB_LED. */
void biba_hal_rgb_led_set(uint8_t r, uint8_t g, uint8_t b);

/* Raise/lower the DATA_READY line to the SBC. */
void biba_hal_data_ready_set(bool on);
void biba_hal_data_ready_pulse(void);

/* Latched MODE_SEL sample captured during biba_hal_init(). true = companion. */
bool biba_hal_mode_sel_is_companion(void);

/* BTS7960 enables, high-level. */
void biba_hal_left_enable(bool enabled);
void biba_hal_right_enable(bool enabled);

/* SSR (Solid-State Relay) — BTS7960 power-rail control.
 * Implemented in biba_hal_rp2040.c; no-op stubs in biba_hal.c (STM32/debug).
 * D-13: init drives pin LOW at boot; set follows arm state in mode_standalone. */
void biba_hal_ssr_init(void);
void biba_hal_ssr_set(bool enabled);

/* --- Motor PWM ---------------------------------------------------------- */

/* Initialise the four BTS7960 motor-PWM lines. The exact topology is
 * per-target: BLUEPILL_F103C8 uses a single shared timer (TIM1), while
 * BIBA_F103_REV_A binds each line to its own hardware timer so the
 * motor-audio API below can run four independent carriers at once. */
void biba_hal_motor_pwm_init(void);

/* Traction-mode drive. `duty` is [-1.0, 1.0]. Negative drives LPWM,
 * positive drives RPWM. Shared carrier, BIBA_PWM_FREQUENCY_HZ (20 kHz). */
void biba_hal_motor_pwm_left(float duty);
void biba_hal_motor_pwm_right(float duty);

/* --- Motor audio -------------------------------------------------------- */

/* Per-channel PWM frequency + duty, batched. The `ch` index matches
 * `biba_motor_audio_channel_t` (see proto/biba_proto.h):
 *   0 = L_RPWM, 1 = L_LPWM, 2 = R_RPWM, 3 = R_LPWM.
 *
 * `freq_hz` of 0 silences the channel. `duty_unit` is [0.0, 1.0].
 *
 * Returns true if the target supports per-channel carriers and the
 * update has been programmed; false if the target keeps a single
 * carrier and the caller's audio intent cannot be honoured. The traction
 * API (biba_hal_motor_pwm_left/right) stays usable either way. */
bool biba_hal_motor_audio_set_all(const uint32_t freq_hz[4],
                                  const float    duty_unit[4]);

/* Switch the four motor-PWM carriers between shared-traction-carrier
 * (20 kHz) and independent-audio-carrier mode. On targets without
 * per-channel timers both calls are no-ops and return false. */
bool biba_hal_motor_audio_begin(void);
bool biba_hal_motor_audio_end(void);

/* --- PCM-over-PWM playback ---------------------------------------------- *
 *
 * RPWM is held at 50 % of the existing 20 kHz carrier (DC bias).
 * LPWM duty = sample / 255 — the differential voltage across the coil
 * follows the audio waveform at the carrier frequency.
 * A hardware repeating timer fires at rate_hz to feed each sample.
 *
 * While PCM is active traction PWM is blocked (same as audio mode).
 * Returns false if the audio melody mode is already active. */
bool biba_hal_motor_pcm_play(const uint8_t *samples, uint32_t count,
                              uint32_t rate_hz);
bool biba_hal_motor_pcm_active(void);
void biba_hal_motor_pcm_stop(void);

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

/* Blocking transmit of `len` bytes on USART3 TX (PB10). Used to send
 * CRSF ping/telemetry frames back to the receiver.
 * Returns 0 on success, non-zero HAL status on failure. */
uint32_t biba_hal_crsf_write(const uint8_t *data, size_t len);

/* Diagnostic snapshot: DMA NDTR, UART error code, UART Rx state, and
 * the HAL status returned by the last HAL_UART_Receive_DMA call. */
typedef struct {
    uint32_t dma_ndtr;        /* raw DMA counter — changes while data flows  */
    uint32_t uart_error_code; /* huart3.ErrorCode (HAL_UART_ERROR_*)         */
    uint32_t uart_rx_state;   /* huart3.RxState   (HAL_UART_STATE_*)         */
    uint32_t uart_tx_state;   /* huart3.gState    (HAL_UART_STATE_*)         */
    uint32_t uart_sr;         /* raw USART3->SR register                     */
    uint32_t uart_cr1;        /* raw USART3->CR1 register (TE/RE/UE bits)    */
    uint32_t rcc_apb1enr;     /* RCC->APB1ENR: bit18=USART3EN must be set   */
    uint32_t dma_init_status; /* HAL_OK=0 from HAL_UART_Receive_DMA          */
} biba_hal_crsf_diag_t;
biba_hal_crsf_diag_t biba_hal_crsf_diag(void);

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

/* --- USB-CDC serial readline (Arduino framework only) ------------------- */

/* Non-blocking line reader.  Accumulates bytes from USB CDC into an internal
 * 128-byte buffer; when a newline is received the line (without the newline)
 * is copied into `buf` (NUL-terminated, at most max_len-1 chars) and true is
 * returned.  Returns false when no complete line is available yet.
 * Empty lines (\n\n) are silently discarded. */
bool biba_hal_serial_readline(char *buf, size_t max_len);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_HAL_H */
