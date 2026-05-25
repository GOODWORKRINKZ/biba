#ifndef BIBA_TARGET_H
#define BIBA_TARGET_H

/* Target: RPICO_RP2040
 *
 * Compact RP2040 board (dual Cortex-M0+, 125 MHz, 264 KB SRAM).
 * Compatible with Raspberry Pi Pico pinout (PlatformIO board: rpipico).
 *
 * Pin assignment — left side (GP0-GP15, top to bottom):
 *
 *   GP0  UART0_TX  CRSF TX → receiver
 *   GP1  UART0_RX  CRSF RX ← receiver
 *   ---- Left BTS7960 driver (4 consecutive pins) ----
 *   GP2  PWM1A     L_RPWM  (slice 1, ch A)
 *   GP3  PWM1B     L_LPWM  (slice 1, ch B — same carrier)
 *   GP4  GPIO OUT  L_REN
 *   GP5  GPIO OUT  L_LEN
 *   ---- Right BTS7960 driver (4 consecutive pins) ---
 *   GP6  PWM3A     R_RPWM  (slice 3, ch A)
 *   GP7  PWM3B     R_LPWM  (slice 3, ch B — same carrier)
 *   GP8  GPIO OUT  R_REN
 *   GP9  GPIO OUT  R_LEN
 *   ---- SBC UART link (UART1) --------------------------
 *   GP10 —          (free)
 *   GP11 —          (free)
 *   GP12 UART1_TX   SBC RX  (RP2040 → SBC)
 *   GP13 UART1_RX   SBC TX  (SBC → RP2040)
 *   GP14 —          (free)
 *   GP15 —          (free)
 *
 * Pin assignment — right side (GP16-GP29, bottom to top):
 *
 *   GP16 —          (free)
 *   GP20 I2C0_SDA  IMU  (SDA)
 *   GP21 I2C0_SCL  IMU  (SCL)
 *   GP22 GPIO IN   IMU INT1
 *   GP25 GPIO OUT  Onboard LED (active high)
 *   GP26 ADC0      IS_RIGHT (1kΩ‖1kΩ RC filter from BTS7960 R IS pins — Phase 06)
 *   GP27 ADC1      IS_LEFT  (1kΩ‖1kΩ RC filter from BTS7960 L IS pins — Phase 06)
 *   GP20 I2C0_SDA  IMU + ADS1115 + AHT30 (shared I2C0 bus)
 *   GP21 I2C0_SCL  IMU + ADS1115 + AHT30 (shared I2C0 bus)
 *
 * ADC topology: all three native channels used on-board (no ADS1115).
 * GP26=IS_RIGHT, GP27=IS_LEFT, GP28=VBAT (resistive divider).
 *
 * Motor audio: L and R pairs each share one PWM slice (fixed wrap),
 * so per-channel independent carriers are not supported.
 * BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM = 0.
 */

#define BIBA_TARGET_NAME            "RPICO_RP2040"
#define BIBA_TARGET_HAS_BTS7960_2CH 1
#define BIBA_TARGET_HAS_CRSF        1
#define BIBA_TARGET_HAS_IMU         1
#define BIBA_TARGET_HAS_SPI_SLAVE   0   /* SBC link switched to UART1 */

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

/* Left  pair: GP2/GP3  → PWM slice 1 (ch A / ch B). */
/* Right pair: GP6/GP7  → PWM slice 3 (ch A / ch B). */
/* Both channels of a slice share the same wrap (carrier frequency). */
#define BIBA_PIN_LEFT_RPWM_GPIO      2   /* PWM slice 1, channel A */
#define BIBA_PIN_LEFT_LPWM_GPIO      3   /* PWM slice 1, channel B */
#define BIBA_PIN_RIGHT_RPWM_GPIO     6   /* PWM slice 3, channel A */
#define BIBA_PIN_RIGHT_LPWM_GPIO     7   /* PWM slice 3, channel B */

/* --- Motor enables (GPIO OUT) ------------------------------------------ */
/* Left driver: GP4/GP5 (adjacent to GP2/GP3 PWM — all 4 pins together). */
/* Right driver: GP8/GP9 (adjacent to GP6/GP7 PWM — all 4 pins together). */
#define BIBA_PIN_LEFT_REN_GPIO       4
#define BIBA_PIN_LEFT_LEN_GPIO       5
#define BIBA_PIN_RIGHT_REN_GPIO      8
#define BIBA_PIN_RIGHT_LEN_GPIO      9

/* --- CRSF (UART0, GP0=TX / GP1=RX) ------------------------------------- */

#define BIBA_PIN_CRSF_TX_GPIO        0
#define BIBA_PIN_CRSF_RX_GPIO        1
#define BIBA_CRSF_UART_INST          uart0
#define BIBA_CRSF_UART_IRQ           UART0_IRQ

/* --- SBC link (UART1, GP12=TX / GP13=RX) ------------------------------- */
/* SPI slave replaced by UART1. GP10, GP11, GP14, GP15 are free.           */
#define BIBA_PIN_SBC_TX_GPIO         12   /* UART1_TX → SBC RX */
#define BIBA_PIN_SBC_RX_GPIO         13   /* UART1_RX ← SBC TX */
#define BIBA_SBC_UART_INST           uart1
#define BIBA_SBC_UART_IRQ            UART1_IRQ

/* --- SSR removed — GP16 is free --------------------------------------- */
/* biba_hal_ssr_init / biba_hal_ssr_set are kept as no-ops in the HAL.    */

/* --- IMU (I2C0, GP20=SDA / GP21=SCL) ----------------------------------- */
/* GP20/GP21 are adjacent on the right side of the board. */
#define BIBA_PIN_I2C_SDA_GPIO        20
#define BIBA_PIN_I2C_SCL_GPIO        21
#define BIBA_PIN_IMU_INT1_GPIO       22
#define BIBA_I2C_INST                i2c0

/* --- ADC ---------------------------------------------------------------- */
/*
 * Native ADC topology — three channels on-board:
 *
 *   CH0 (GP26) — IS_RIGHT (1kΩ‖1kΩ + 0.1µF RC filter from BTS7960 right)
 *   CH1 (GP27) — IS_LEFT  (1kΩ‖1kΩ + 0.1µF RC filter from BTS7960 left)
 *   CH2 (GP28) — VBAT     (resistive voltage divider → BIBA_VBAT_DIVIDER_RATIO)
 *
 * No external ADC (ADS1115 not used).
 */
#define BIBA_ADC_CHAN_IS_RIGHT       0U   /* GP26 = ADC0, RC-filtered IS right */
#define BIBA_ADC_CHAN_IS_LEFT        1U   /* GP27 = ADC1, RC-filtered IS left  */
#define BIBA_ADC_CHAN_VBAT           2U   /* GP28 = ADC2, VBAT voltage divider */

#define BIBA_ADC_SCAN_LEN           3U
#define BIBA_ADC_CHANNEL_SEQ        { 0, 1, 2 }

/* --- Status LED (GP25, onboard on Pico, active high) ------------------- */

#define BIBA_PIN_STATUS_LED_GPIO     25
#define BIBA_STATUS_LED_ACTIVE_LOW   0

/* --- WS2812 RGB LED (GP23, YD-RP2040 onboard NeoPixel) ----------------- */

#define BIBA_PIN_RGB_LED_GPIO        23
#define BIBA_HAS_RGB_LED             1

#endif /* BIBA_TARGET_H */
