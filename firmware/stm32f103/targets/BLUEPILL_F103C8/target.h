#ifndef BIBA_TARGET_H
#define BIBA_TARGET_H

/* Target: BLUEPILL_F103C8
 *
 * STM32F103C8T6 ("Blue Pill") dev board — the reference BiBa target.
 * Rationale for the peripheral and pin assignment is documented in
 * targets/BLUEPILL_F103C8/target.md, docs/stm32_architecture.md and
 * the "Подключение STM32F103" section of docs/wiring.md.
 *
 *   - TIM1 owns all four BTS7960 PWM channels so the four lines stay in
 *     phase and dead-time can be inserted between RPWM/LPWM of the same
 *     side.
 *   - USART1 is deliberately unused: its AF pins PA9/PA10 are taken by
 *     PWM.
 *   - ADC1 runs a circular DMA scan over PA0..PA6.
 *   - SPI2 is the slave link to the SBC (PB12..PB15).
 *   - USART3 (PB10/PB11) is the CRSF UART at 420 000 baud via DMA.
 *   - I2C1 (PB6/PB7) is the IMU bus.
 *   - JTAG is released at boot (SW-DP only) so PB3/PB4/PA15 are free
 *     GPIOs.
 */

#define BIBA_TARGET_NAME            "BLUEPILL_F103C8"
#define BIBA_TARGET_HAS_BTS7960_2CH 1
#define BIBA_TARGET_HAS_CRSF        1
#define BIBA_TARGET_HAS_IMU         1
#define BIBA_TARGET_HAS_SPI_SLAVE   1

/* STM32 HAL-style macros. We guard inclusion so this header stays
 * usable from native_test (where STM32 HAL headers are absent). */
#if !defined(BIBA_NATIVE_TEST)
#  include "stm32f1xx_hal.h"
#endif

/* --- Motor PWM (TIM1) --------------------------------------------------- */

#define BIBA_PIN_LEFT_RPWM_PORT      GPIOA
#define BIBA_PIN_LEFT_RPWM_PIN       GPIO_PIN_8    /* TIM1_CH1 */
#define BIBA_PIN_LEFT_LPWM_PORT      GPIOA
#define BIBA_PIN_LEFT_LPWM_PIN       GPIO_PIN_9    /* TIM1_CH2 */
#define BIBA_PIN_RIGHT_RPWM_PORT     GPIOA
#define BIBA_PIN_RIGHT_RPWM_PIN      GPIO_PIN_10   /* TIM1_CH3 */
#define BIBA_PIN_RIGHT_LPWM_PORT     GPIOA
#define BIBA_PIN_RIGHT_LPWM_PIN      GPIO_PIN_11   /* TIM1_CH4 */

/* --- Motor enables (GPIO, JTAG-released) -------------------------------- */

#define BIBA_PIN_LEFT_REN_PORT       GPIOB
#define BIBA_PIN_LEFT_REN_PIN        GPIO_PIN_3    /* freed from JTDO */
#define BIBA_PIN_LEFT_LEN_PORT       GPIOB
#define BIBA_PIN_LEFT_LEN_PIN        GPIO_PIN_4    /* freed from NJTRST */
#define BIBA_PIN_RIGHT_REN_PORT      GPIOB
#define BIBA_PIN_RIGHT_REN_PIN       GPIO_PIN_5
#define BIBA_PIN_RIGHT_LEN_PORT      GPIOB
#define BIBA_PIN_RIGHT_LEN_PIN       GPIO_PIN_8

/* --- ADC1 scan channels (analog inputs) --------------------------------- */

#define BIBA_ADC_CHAN_LEFT_R_IS      0U   /* PA0 */
#define BIBA_ADC_CHAN_LEFT_L_IS      1U   /* PA1 */
#define BIBA_ADC_CHAN_RIGHT_R_IS     2U   /* PA2 */
#define BIBA_ADC_CHAN_RIGHT_L_IS     3U   /* PA3 */
#define BIBA_ADC_CHAN_VBAT           4U   /* PA4 */
#define BIBA_ADC_CHAN_RAIL_12V       5U   /* PA5 */
#define BIBA_ADC_CHAN_RAIL_CURRENT   6U   /* PA6 */

#define BIBA_ADC_SCAN_LEN            7U

/* --- CRSF (USART3) ------------------------------------------------------ */

#define BIBA_PIN_CRSF_TX_PORT        GPIOB
#define BIBA_PIN_CRSF_TX_PIN         GPIO_PIN_10
#define BIBA_PIN_CRSF_RX_PORT        GPIOB
#define BIBA_PIN_CRSF_RX_PIN         GPIO_PIN_11

/* --- SPI slave (SPI2) --------------------------------------------------- */

#define BIBA_PIN_SPI_NSS_PORT        GPIOB
#define BIBA_PIN_SPI_NSS_PIN         GPIO_PIN_12
#define BIBA_PIN_SPI_SCK_PORT        GPIOB
#define BIBA_PIN_SPI_SCK_PIN         GPIO_PIN_13
#define BIBA_PIN_SPI_MISO_PORT       GPIOB
#define BIBA_PIN_SPI_MISO_PIN        GPIO_PIN_14
#define BIBA_PIN_SPI_MOSI_PORT       GPIOB
#define BIBA_PIN_SPI_MOSI_PIN        GPIO_PIN_15

/* --- Data-ready line to SBC (GPIO OUT) ---------------------------------- */

#define BIBA_PIN_DATA_READY_PORT     GPIOA
#define BIBA_PIN_DATA_READY_PIN      GPIO_PIN_12

/* --- Mode select (pull-up; read once at boot for `combined` env) -------- */

#define BIBA_PIN_MODE_SEL_PORT       GPIOB
#define BIBA_PIN_MODE_SEL_PIN        GPIO_PIN_9

/* --- IMU (I2C1) --------------------------------------------------------- */

#define BIBA_PIN_I2C_SCL_PORT        GPIOB
#define BIBA_PIN_I2C_SCL_PIN         GPIO_PIN_6
#define BIBA_PIN_I2C_SDA_PORT        GPIOB
#define BIBA_PIN_I2C_SDA_PIN         GPIO_PIN_7

#define BIBA_PIN_IMU_INT1_PORT       GPIOB
#define BIBA_PIN_IMU_INT1_PIN        GPIO_PIN_2

/* --- Status LED on Blue Pill (active low) ------------------------------- */

#define BIBA_PIN_STATUS_LED_PORT     GPIOC
#define BIBA_PIN_STATUS_LED_PIN      GPIO_PIN_13
#define BIBA_STATUS_LED_ACTIVE_LOW   1

/* --- Optional auxiliary buzzer / tone (TIM2_CH1 remap) ------------------ */

#define BIBA_PIN_AUX_TONE_PORT       GPIOA
#define BIBA_PIN_AUX_TONE_PIN        GPIO_PIN_15

#endif /* BIBA_TARGET_H */
