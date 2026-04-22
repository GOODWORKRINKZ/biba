#ifndef BIBA_TARGET_H
#define BIBA_TARGET_H

/* Target: BIBA_F103_REV_A
 *
 * Reference custom PCB ("BiBa Driver Rev A") built around an STM32F103C8T6.
 * Same MCU family as BLUEPILL_F103C8 but the custom board brings the
 * following differences:
 *
 *   - Dedicated current-sense shunt with an op-amp, so the IS → amperes
 *     scale is different and the zero-offset is calibrated to 0.0 V.
 *   - Enable pins moved off the JTAG pins (PB3/PB4) onto PB0..PB2/PB9 so
 *     JTAG can stay live during prototyping — MODE_SEL re-homes to PB8.
 *   - No 12 V rail tap on ADC — that channel is re-purposed as a
 *     chassis-temperature NTC.
 *   - Status LED lives on PB5 (active high) because the silkscreen LED
 *     on the Rev A prototype is wired that way.
 *
 * The test-matrix point of this target is to make sure that adding a
 * new board never touches the portable code — only these three files.
 */

#define BIBA_TARGET_NAME            "BIBA_F103_REV_A"
#define BIBA_TARGET_HAS_BTS7960_2CH 1
#define BIBA_TARGET_HAS_CRSF        1
#define BIBA_TARGET_HAS_IMU         1
#define BIBA_TARGET_HAS_SPI_SLAVE   1
#define BIBA_TARGET_HAS_CHASSIS_NTC 1

#if !defined(BIBA_NATIVE_TEST)
#  include "stm32f1xx_hal.h"
#endif

/* --- Motor PWM (TIM1) --------------------------------------------------- */

#define BIBA_PIN_LEFT_RPWM_PORT      GPIOA
#define BIBA_PIN_LEFT_RPWM_PIN       GPIO_PIN_8
#define BIBA_PIN_LEFT_LPWM_PORT      GPIOA
#define BIBA_PIN_LEFT_LPWM_PIN       GPIO_PIN_9
#define BIBA_PIN_RIGHT_RPWM_PORT     GPIOA
#define BIBA_PIN_RIGHT_RPWM_PIN      GPIO_PIN_10
#define BIBA_PIN_RIGHT_LPWM_PORT     GPIOA
#define BIBA_PIN_RIGHT_LPWM_PIN      GPIO_PIN_11

/* --- Motor enables: PB0..PB2, PB9 (away from JTAG) --------------------- */

#define BIBA_PIN_LEFT_REN_PORT       GPIOB
#define BIBA_PIN_LEFT_REN_PIN        GPIO_PIN_0
#define BIBA_PIN_LEFT_LEN_PORT       GPIOB
#define BIBA_PIN_LEFT_LEN_PIN        GPIO_PIN_1
#define BIBA_PIN_RIGHT_REN_PORT      GPIOB
#define BIBA_PIN_RIGHT_REN_PIN       GPIO_PIN_2
#define BIBA_PIN_RIGHT_LEN_PORT      GPIOB
#define BIBA_PIN_RIGHT_LEN_PIN       GPIO_PIN_9

/* --- ADC1 scan -------------------------------------------------------- */

#define BIBA_ADC_CHAN_LEFT_R_IS      0U   /* PA0 */
#define BIBA_ADC_CHAN_LEFT_L_IS      1U   /* PA1 */
#define BIBA_ADC_CHAN_RIGHT_R_IS     2U   /* PA2 */
#define BIBA_ADC_CHAN_RIGHT_L_IS     3U   /* PA3 */
#define BIBA_ADC_CHAN_VBAT           4U   /* PA4 */
#define BIBA_ADC_CHAN_RAIL_12V       5U   /* PA5 — used as chassis NTC */
#define BIBA_ADC_CHAN_RAIL_CURRENT   6U   /* PA6 */

#define BIBA_ADC_SCAN_LEN            7U

/* --- CRSF (USART3) ---------------------------------------------------- */

#define BIBA_PIN_CRSF_TX_PORT        GPIOB
#define BIBA_PIN_CRSF_TX_PIN         GPIO_PIN_10
#define BIBA_PIN_CRSF_RX_PORT        GPIOB
#define BIBA_PIN_CRSF_RX_PIN         GPIO_PIN_11

/* --- SPI slave (SPI2) ------------------------------------------------- */

#define BIBA_PIN_SPI_NSS_PORT        GPIOB
#define BIBA_PIN_SPI_NSS_PIN         GPIO_PIN_12
#define BIBA_PIN_SPI_SCK_PORT        GPIOB
#define BIBA_PIN_SPI_SCK_PIN         GPIO_PIN_13
#define BIBA_PIN_SPI_MISO_PORT       GPIOB
#define BIBA_PIN_SPI_MISO_PIN        GPIO_PIN_14
#define BIBA_PIN_SPI_MOSI_PORT       GPIOB
#define BIBA_PIN_SPI_MOSI_PIN        GPIO_PIN_15

/* --- Data-ready line to SBC ------------------------------------------- */

#define BIBA_PIN_DATA_READY_PORT     GPIOA
#define BIBA_PIN_DATA_READY_PIN      GPIO_PIN_12

/* --- Mode select (PB8 on this PCB) ------------------------------------ */

#define BIBA_PIN_MODE_SEL_PORT       GPIOB
#define BIBA_PIN_MODE_SEL_PIN        GPIO_PIN_8

/* --- IMU (I2C1) ------------------------------------------------------- */

#define BIBA_PIN_I2C_SCL_PORT        GPIOB
#define BIBA_PIN_I2C_SCL_PIN         GPIO_PIN_6
#define BIBA_PIN_I2C_SDA_PORT        GPIOB
#define BIBA_PIN_I2C_SDA_PIN         GPIO_PIN_7

#define BIBA_PIN_IMU_INT1_PORT       GPIOB
#define BIBA_PIN_IMU_INT1_PIN        GPIO_PIN_3

/* --- Status LED on Rev A PCB (active HIGH) ---------------------------- */

#define BIBA_PIN_STATUS_LED_PORT     GPIOB
#define BIBA_PIN_STATUS_LED_PIN      GPIO_PIN_5
#define BIBA_STATUS_LED_ACTIVE_LOW   0

/* --- Aux tone (TIM2_CH1 remap) ---------------------------------------- */

#define BIBA_PIN_AUX_TONE_PORT       GPIOA
#define BIBA_PIN_AUX_TONE_PIN        GPIO_PIN_15

#endif /* BIBA_TARGET_H */
