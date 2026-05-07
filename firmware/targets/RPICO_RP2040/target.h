#ifndef BIBA_TARGET_H
#define BIBA_TARGET_H

/* Target: RPICO_RP2040
 *
 * Raspberry Pi Pico (RP2040, dual Cortex-M0+, 125 MHz, 264 KB SRAM).
 *
 * Pin assignment:
 *
 *   GP0  UART0_TX  CRSF TX → receiver
 *   GP1  UART0_RX  CRSF RX ← receiver
 *   GP2  PWM1A     L_RPWM
 *   GP3  PWM1B     L_LPWM   (slice 1, same carrier as L_RPWM)
 *   GP4  PWM2A     R_RPWM
 *   GP5  PWM2B     R_LPWM   (slice 2, same carrier as R_RPWM)
 *   GP6  GPIO OUT  L_REN
 *   GP7  GPIO OUT  L_LEN
 *   GP8  GPIO OUT  R_REN
 *   GP9  GPIO OUT  R_LEN
 *   GP10 SPI1_SCK  SBC SCK
 *   GP11 SPI1_TX   SBC MISO (data RP2040→SBC)
 *   GP12 SPI1_RX   SBC MOSI (data SBC→RP2040)
 *   GP13 SPI1_CSn  SBC NSS
 *   GP14 GPIO OUT  DATA_READY to SBC
 *   GP15 GPIO IN   MODE_SEL (pull-up; low = companion)
 *   GP16 I2C0_SDA  IMU
 *   GP17 I2C0_SCL  IMU
 *   GP18 GPIO IN   IMU INT1
 *   GP25 GPIO OUT  Onboard LED (active high)
 *   GP26 ADC0      VBAT
 *   GP27 ADC1      Rail current sense
 *
 * ADC: only 2 channels (RP2040 has 4 ADC pins but we only need VBAT and
 * rail current; per-motor current sense is not wired on this target).
 * Per-motor current aliases all point to CH0 to avoid out-of-bounds.
 *
 * Motor audio: L and R pairs share a PWM slice (fixed wrap/frequency),
 * so independent per-channel carriers are not supported.
 * BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM = 0.
 */

#define BIBA_TARGET_NAME            "RPICO_RP2040"
#define BIBA_TARGET_HAS_BTS7960_2CH 1
#define BIBA_TARGET_HAS_CRSF        1
#define BIBA_TARGET_HAS_IMU         1
#define BIBA_TARGET_HAS_SPI_SLAVE   1

#define BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM 0

#if !defined(BIBA_NATIVE_TEST)
#  include "pico/stdlib.h"
#  include "hardware/gpio.h"
#  include "hardware/uart.h"
#  include "hardware/spi.h"
#  include "hardware/i2c.h"
#  include "hardware/adc.h"
#  include "hardware/pwm.h"
#  include "hardware/dma.h"
#  include "hardware/irq.h"
#endif

/* --- Motor PWM (RP2040 hardware PWM) ----------------------------------- */

/* GP2/GP3 are on PWM slice 1 (channels A and B).
 * GP4/GP5 are on PWM slice 2 (channels A and B).
 * Both channels of a slice share the same wrap (period/frequency). */
#define BIBA_PIN_LEFT_RPWM_GPIO      2   /* PWM slice 1, channel A */
#define BIBA_PIN_LEFT_LPWM_GPIO      3   /* PWM slice 1, channel B */
#define BIBA_PIN_RIGHT_RPWM_GPIO     4   /* PWM slice 2, channel A */
#define BIBA_PIN_RIGHT_LPWM_GPIO     5   /* PWM slice 2, channel B */

/* --- Motor enables (GPIO OUT) ------------------------------------------ */

#define BIBA_PIN_LEFT_REN_GPIO       6
#define BIBA_PIN_LEFT_LEN_GPIO       7
#define BIBA_PIN_RIGHT_REN_GPIO      8
#define BIBA_PIN_RIGHT_LEN_GPIO      9

/* --- CRSF (UART0, GP0=TX / GP1=RX) ------------------------------------- */

#define BIBA_PIN_CRSF_TX_GPIO        0
#define BIBA_PIN_CRSF_RX_GPIO        1
#define BIBA_CRSF_UART_INST          uart0
#define BIBA_CRSF_UART_IRQ           UART0_IRQ

/* --- SPI slave (SPI1) -------------------------------------------------- */

#define BIBA_PIN_SPI_SCK_GPIO        10
#define BIBA_PIN_SPI_TX_GPIO         11   /* SPI1_TX = MISO when slave */
#define BIBA_PIN_SPI_RX_GPIO         12   /* SPI1_RX = MOSI when slave */
#define BIBA_PIN_SPI_CSN_GPIO        13
#define BIBA_SPI_INST                spi1

/* --- Data-ready / mode-select ------------------------------------------ */

#define BIBA_PIN_DATA_READY_GPIO     14
#define BIBA_PIN_MODE_SEL_GPIO       15

/* --- IMU (I2C0, GP16=SDA / GP17=SCL) ----------------------------------- */

#define BIBA_PIN_I2C_SDA_GPIO        16
#define BIBA_PIN_I2C_SCL_GPIO        17
#define BIBA_PIN_IMU_INT1_GPIO       18
#define BIBA_I2C_INST                i2c0

/* --- ADC ---------------------------------------------------------------- */
/*
 * RP2040 ADC pins: GP26=CH0, GP27=CH1, GP28=CH2, GP29=CH3.
 * We use only CH0 (VBAT) and CH1 (rail current).
 * Per-motor current channels are aliased to CH0 so callers do not get
 * out-of-bounds reads; the returned value is not meaningful for those.
 */
#define BIBA_ADC_CHAN_LEFT_R_IS     0U   /* aliased — not wired */
#define BIBA_ADC_CHAN_LEFT_L_IS     0U   /* aliased — not wired */
#define BIBA_ADC_CHAN_RIGHT_R_IS    0U   /* aliased — not wired */
#define BIBA_ADC_CHAN_RIGHT_L_IS    0U   /* aliased — not wired */
#define BIBA_ADC_CHAN_VBAT          0U   /* GP26 = ADC0 */
#define BIBA_ADC_CHAN_RAIL_12V      0U   /* aliased — not wired */
#define BIBA_ADC_CHAN_RAIL_CURRENT  1U   /* GP27 = ADC1 */

#define BIBA_ADC_SCAN_LEN           2U

/* Polled on demand; no DMA sequence needed. */
#define BIBA_ADC_CHANNEL_SEQ        { 0, 1 }

/* --- Status LED (GP25, onboard on Pico, active high) ------------------- */

#define BIBA_PIN_STATUS_LED_GPIO     25
#define BIBA_STATUS_LED_ACTIVE_LOW   0

#endif /* BIBA_TARGET_H */
