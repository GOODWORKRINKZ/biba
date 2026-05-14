#ifndef BIBA_TARGET_H
#define BIBA_TARGET_H

/* Target: BLUEPILL_F103C8_CLONE
 *
 * Knock-off STM32F103C8T6 Blue Pill.  The die appears to be missing
 * the USART3 peripheral block entirely: RCC_APB1ENR bit 18 sets
 * correctly but USART3->SR and USART3->CR1 always read 0x0 regardless
 * of init, proving the peripheral is not physically present.
 *
 * Workaround: CRSF is moved to USART2 (PA2=TX, PA3=RX).  This
 * sacrifices the two right-motor current-sense channels (PA2/PA3 are
 * ADC_CH2/CH3 on the Blue Pill layout).  All four motor PWM lines and
 * the left-motor current sense remain functional.
 *
 * Everything else (timer topology, SPI2, I2C1, pin assignments) is
 * identical to BLUEPILL_F103C8.
 */

#define BIBA_TARGET_NAME            "BLUEPILL_F103C8_CLONE"
#define BIBA_TARGET_HAS_BTS7960_2CH 1
#define BIBA_TARGET_HAS_CRSF        1
#define BIBA_TARGET_HAS_IMU         1
#define BIBA_TARGET_HAS_SPI_SLAVE   1

#define BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM 0

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

/* --- ADC1 scan channels ------------------------------------------------- */
/*
 * PA2 and PA3 are reassigned to USART2 (CRSF TX/RX), so ADC_CH2 and
 * ADC_CH3 are unavailable.  The scan runs only 5 channels; the
 * RIGHT_R_IS / RIGHT_L_IS indices alias to LEFT_R_IS / LEFT_L_IS so
 * callers that read right-motor current get the left-motor reading
 * instead of out-of-bounds access.
 */
#define BIBA_ADC_CHAN_LEFT_R_IS     0U   /* PA0 */
#define BIBA_ADC_CHAN_LEFT_L_IS     1U   /* PA1 */
#define BIBA_ADC_CHAN_RIGHT_R_IS    0U   /* PA2 taken by USART2 TX — alias */
#define BIBA_ADC_CHAN_RIGHT_L_IS    1U   /* PA3 taken by USART2 RX — alias */
#define BIBA_ADC_CHAN_VBAT          2U   /* PA4 */
#define BIBA_ADC_CHAN_RAIL_12V      3U   /* PA5 */
#define BIBA_ADC_CHAN_RAIL_CURRENT  4U   /* PA6 */

#define BIBA_ADC_SCAN_LEN           5U

/* ADC1 scan channel sequence: CH0, CH1, CH4, CH5, CH6 (skip CH2/CH3). */
#define BIBA_ADC_CHANNEL_SEQ \
    { ADC_CHANNEL_0, ADC_CHANNEL_1, \
      ADC_CHANNEL_4, ADC_CHANNEL_5, ADC_CHANNEL_6 }

/* --- CRSF (USART2, PA2=TX / PA3=RX, default AF, no remap) -------------- */

#define BIBA_PIN_CRSF_TX_PORT        GPIOA
#define BIBA_PIN_CRSF_TX_PIN         GPIO_PIN_2
#define BIBA_PIN_CRSF_RX_PORT        GPIOA
#define BIBA_PIN_CRSF_RX_PIN         GPIO_PIN_3

/* CRSF UART peripheral abstraction. */
#define BIBA_CRSF_UART_INSTANCE      USART2
#define BIBA_CRSF_CLK_ENABLE()       __HAL_RCC_USART2_CLK_ENABLE()
#define BIBA_CRSF_AF_REMAP()         ((void)0)
#define BIBA_CRSF_DMA_CHANNEL_RX     DMA1_Channel6
#define BIBA_CRSF_DMA_IRQn_RX        DMA1_Channel6_IRQn
#define BIBA_CRSF_UART_IRQn          USART2_IRQn
#define BIBA_CRSF_DMA_IRQ_HANDLER    DMA1_Channel6_IRQHandler
#define BIBA_CRSF_UART_IRQ_HANDLER   USART2_IRQHandler

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

#endif /* BIBA_TARGET_H */
