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
 *   ---- SBC SPI slave (4 consecutive pins) ----------
 *   GP10 SPI1_SCK  SBC SCK
 *   GP11 SPI1_TX   SBC MISO (RP2040 → SBC)
 *   GP12 SPI1_RX   SBC MOSI (SBC → RP2040)
 *   GP13 SPI1_CSn  SBC NSS
 *   GP14 GPIO OUT  DATA_READY to SBC
 *   GP15 GPIO IN   MODE_SEL (pull-up; low = companion)
 *
 * Pin assignment — right side (GP16-GP29, bottom to top):
 *
 *   GP16 GPIO OUT  SSR (BTS7960 power relay)
 *   GP20 I2C0_SDA  IMU  (SDA)
 *   GP21 I2C0_SCL  IMU  (SCL)
 *   GP22 GPIO IN   IMU INT1
 *   GP25 GPIO OUT  Onboard LED (active high)
 *   GP26 ADC0      IS_LEFT  (1kΩ‖1kΩ RC filter from BTS7960 L IS pins — Phase 06)
 *   GP27 ADC1      IS_RIGHT (1kΩ‖1kΩ RC filter from BTS7960 R IS pins — Phase 06)
 *   GP20 I2C0_SDA  IMU + ADS1115 + AHT30 (shared I2C0 bus)
 *   GP21 I2C0_SCL  IMU + ADS1115 + AHT30 (shared I2C0 bus)
 *
 * Phase 06 topology change: VBAT and IBAT moved to ADS1115 AIN0/AIN1.
 * GP26/GP27 now carry RC-filtered IS signals for RPM PoC.
 * ADS1115 AIN0–AIN1 carry VBAT/IBAT (3DR Power Module outputs).
 *
 * Motor audio: L and R pairs each share one PWM slice (fixed wrap),
 * so per-channel independent carriers are not supported.
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

/* --- SPI slave (SPI1) -------------------------------------------------- */

#define BIBA_PIN_SPI_SCK_GPIO        10
#define BIBA_PIN_SPI_TX_GPIO         11   /* SPI1_TX = MISO when slave */
#define BIBA_PIN_SPI_RX_GPIO         12   /* SPI1_RX = MOSI when slave */
#define BIBA_PIN_SPI_CSN_GPIO        13
#define BIBA_SPI_INST                spi1

/* --- Data-ready / mode-select ------------------------------------------ */

#define BIBA_PIN_DATA_READY_GPIO     14
#define BIBA_PIN_MODE_SEL_GPIO       15

/* --- SSR (Solid-State Relay — BTS7960 power control) ------------------- */
/* GP16: first free pin after SBC SPI interface (GP10-GP14) and MODE_SEL   */
/* (GP15). HIGH = BTS7960 powered (armed); LOW = BTS7960 power off.        */
/* D-09: SSR pin assignment.                                                */
#define BIBA_PIN_SSR_GPIO            16

/* --- IMU (I2C0, GP20=SDA / GP21=SCL) ----------------------------------- */
/* GP20/GP21 are adjacent on the right side of the board. */
#define BIBA_PIN_I2C_SDA_GPIO        20
#define BIBA_PIN_I2C_SCL_GPIO        21
#define BIBA_PIN_IMU_INT1_GPIO       22
#define BIBA_I2C_INST                i2c0

/* --- ADC ---------------------------------------------------------------- */
/*
 * Phase 06 topology: RP2040 native ADC GP26/GP27 now carry RC-filtered
 * BTS7960 IS signals for RPM PoC.  VBAT and IBAT (3DR Power Module) are
 * routed to ADS1115 AIN0/AIN1 via I2C0.
 *
 *   CH0 (GP26) — IS_LEFT  (1kΩ‖1kΩ + 0.1µF RC filter)
 *   CH1 (GP27) — IS_RIGHT (1kΩ‖1kΩ + 0.1µF RC filter)
 *
 * ADS1115 AIN0 — VBAT (3DR Power Module voltage output)
 * ADS1115 AIN1 — IBAT (3DR Power Module current output)
 */
#define BIBA_ADC_CHAN_IS_RIGHT       0U   /* GP27 = ADC1, RC-filtered IS right */
#define BIBA_ADC_CHAN_IS_LEFT        1U   /* GP26 = ADC0, RC-filtered IS left  */

#define BIBA_ADC_SCAN_LEN           2U
#define BIBA_ADC_CHANNEL_SEQ        { 0, 1 }

/* ADS1115 logical channel mapping (AIN0–AIN1 vs GND — Phase 06).
 * AIN0: VBAT via 3DR Power Module resistive divider.
 * AIN1: IBAT via 3DR Power Module current output.
 */
#define BIBA_ADS1115_CHAN_VBAT       0U   /* AIN0: 3DR PM voltage out  */
#define BIBA_ADS1115_CHAN_IBAT       1U   /* AIN1: 3DR PM current out  */

/* --- Status LED (GP25, onboard on Pico, active high) ------------------- */

#define BIBA_PIN_STATUS_LED_GPIO     25
#define BIBA_STATUS_LED_ACTIVE_LOW   0

/* --- WS2812 RGB LED (GP23, YD-RP2040 onboard NeoPixel) ----------------- */

#define BIBA_PIN_RGB_LED_GPIO        23
#define BIBA_HAS_RGB_LED             1

#endif /* BIBA_TARGET_H */
