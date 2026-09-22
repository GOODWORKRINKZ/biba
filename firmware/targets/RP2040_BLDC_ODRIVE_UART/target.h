#ifndef BIBA_TARGET_H
#define BIBA_TARGET_H

/* Target: RP2040_BLDC_ODRIVE_UART
 *
 * Name follows the <MCU>_<MOTOR>_<DRIVER>_<LINK> standard documented
 * in firmware/targets/README.md: RP2040 + BLDC motors + ODrive
 * controllers + UART link.  Sibling of RP2040_BLDC_ODRIVE_CAN, which
 * drives the same controllers through an MCP2515 SPI→CAN bridge;
 * the two are separate targets because the wiring genuinely differs
 * (two UART1 pins here vs. MCP2515 on SPI0 there).
 *
 * RP2040-based BLDC control board.  Talks to two ODrive controllers
 * over the ODrive ASCII protocol on UART1 (GP4/GP5) — one shared bus,
 * one axis addressed per command.  This is the two-wire bring-up
 * variant, and currently the preferred production link: the CANSimple
 * stack in ODrive fw 0.5.6 silently wedges at idle (ADR-0002).
 *
 * Pin assignment — left side (GP0-GP15, top to bottom):
 *
 *   GP0  UART0_TX   CRSF TX → receiver
 *   GP1  UART0_RX   CRSF RX ← receiver
 *   GP2  —           (free, PWM1A not used)
 *   GP3  —           (free, PWM1B not used)
 *   GP4  UART1_TX   ODRIVE_ASY_TX (ODrive UART-A RX)
 *   GP5  UART1_RX   ODRIVE_ASY_RX (ODrive UART-A TX)
 *   GP6  —           (free, PWM3A not used)
 *   GP7  —           (free, PWM3B not used)
 *   GP8  —           (free)
 *   GP9  —           (free)
 *   GP10 —           (free)
 *   GP11 —           (free)
 *   GP12 —           (free)
 *   GP13 —           (free)
 *   GP14 —           (free)
 *   GP15 —           (free — MCP2515 INT on the _CAN sibling)
 *
 * Pin assignment — right side (GP16-GP29, bottom to top):
 *
 *   GP16 —          (free — MCP2515 SO  on the _CAN sibling)
 *   GP17 —          (free — MCP2515 CS  on the _CAN sibling)
 *   GP18 —          (free — MCP2515 SCK on the _CAN sibling)
 *   GP19 —          (free — MCP2515 SI  on the _CAN sibling)
 *   GP20 I2C0_SDA   IMU + ADS1115 + AHT30 (shared I2C0 bus)
 *   GP21 I2C0_SCL   IMU + ADS1115 + AHT30 (shared I2C0 bus)
 *   GP22 GPIO IN    IMU INT1
 *   GP23 GPIO OUT   (NeoPixel WS2812 — same as RP2040_DC_BTS7960_PWM)
 *   GP25 GPIO OUT   Status LED (Pico onboard, active high)
 *   GP26 ADC0       (reserved — n/a on this target)
 *   GP27 ADC1       (reserved — n/a on this target)
 *   GP28 ADC2       (reserved — n/a on this target)
 *   GP29 ADC3       (reserved — n/a on this target)
 *
 * Status indicator: GP25 (onboard LED on YD-RP2040; WS2812 on GP23).
 * No BTS7960 IS pins are wired — current sense happens ODrive-side
 * (`Get_Iq` cmd_id 0x14). Native ADC pins remain available for
 * thermal / VBAT monitoring if the project ever adds a non-ODrive
 * board power-rail sense.
 *
 * Node IDs:
 *   - node_id 0 → LEFT ODrive (Set_Input_Vel mirrors [+1.0] left forward)
 *   - node_id 1 → RIGHT ODrive
 * (Overridable in target_config.h if discovery assigns different IDs.)
 *
 * Discovery: none.  The ASCII backend polls each axis in turn and
 * treats a well-formed reply as liveness (BIBA_ODRIVE_UART_TIMEOUT_MS).
 */

#define BIBA_TARGET_NAME            "RP2040_BLDC_ODRIVE_UART"

/* --- Capability flags ------------------------------------------------- */

/* BTS7960 driver removed: the drive API is backed by
 * drivers/odrive_uart.c behind the drivers/bldc.h contract. */
#define BIBA_TARGET_HAS_BTS7960_2CH  0
#define BIBA_TARGET_HAS_BLDC_2CH     1

/* Which BLDC backend implements drivers/bldc.h on this target.
 * Exactly one of the BACKEND flags may be 1 (see ADR-0002). */
#define BIBA_TARGET_BLDC_BACKEND_ODRIVE  1
#define BIBA_TARGET_BLDC_BACKEND_VESC    0


/* No SPI→CAN bridge on this target: the ODrive link is UART1. */
#define BIBA_TARGET_HAS_MCP2515      0

/* Same as RP2040_DC_BTS7960_PWM — CRSF through UART0. */
#define BIBA_TARGET_HAS_CRSF         1

/* IMU stays on I2C0 GP20/21, no conflict. */
#define BIBA_TARGET_HAS_IMU          1

/* SBC link moved to USB-CDC on the BLDC variant. */
#define BIBA_TARGET_HAS_SPI_SLAVE    0

/* Pairs of RPWM/LPWM per motor each share a PWM slice → no per-channel
 * timer PWM. The BTS7960 motor-audio API does not apply on this target
 * (no BTS7960); audio reuse is reserved for a future buzz feature. */
#define BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM 0

#if !defined(BIBA_NATIVE_TEST)
#  include "hardware/gpio.h"
#  include "hardware/uart.h"
#  include "hardware/spi.h"
#  include "hardware/i2c.h"
#  include "hardware/adc.h"
#  include "hardware/dma.h"
#  include "hardware/irq.h"
#  include "pico/time.h"
#endif

/* --- Motor drive (BLDC, not BTS7960) ---------------------------------- */

/* Drive duty on this target is encoded into an ODrive ASCII velocity
 * command (`v <axis> <vel> <torque_ff>`); the BTS7960 PWM pin macros
 * are intentionally NOT defined here. The portable code in
 * src/hal/biba_hal_motor.c, src/hal/biba_hal_motor_rp2040.c and
 * src/drivers/bts7960.c is excluded by [rp2040_bldc_odrive_uart_src_filter].
 *
 * Numerical mapping [-1.0, +1.0] → rev/s comes from target_config.h:
 *   - BIBA_ODRIVE_LEFT_MAX_VEL_REV_S
 *   - BIBA_ODRIVE_RIGHT_MAX_VEL_REV_S
 * (set conservatively; ODrive enforces its own limits).
 */

/* --- CRSF (UART0, GP0=TX / GP1=RX) ------------------------------------- */

#define BIBA_PIN_CRSF_TX_GPIO        0
#define BIBA_PIN_CRSF_RX_GPIO        1
#define BIBA_CRSF_UART_INST          uart0
#define BIBA_CRSF_UART_IRQ           UART0_IRQ

/* --- SBC link -----------------------------------------------------------
 * SPI slave (used on F103 / non-BLDC targets) is replaced on this
 * target by USB-CDC → SBC (Serial over USB on the YD-RP2040 board).
 * No dedicated UART is reserved for the SBC; the SBC handles the USB
 * gadget itself. If needed in future, UART1 (GP12/13) can be reused.
 */

/* --- ODrive UART-A (UART1, GP4=TX / GP5=RX) ---------------------------- *
 *
 * ODrive ASCII protocol (drivers/odrive_uart.c).  UART0 is CRSF, so
 * ODrive gets UART1.  Cross the pair: Pico TX (GP4) to ODrive RX,
 * Pico RX (GP5) from ODrive TX, and share a ground.
 *
 * ODrive-side UART-A must be enabled with the baud matched to
 * BIBA_ODRIVE_UART_BAUD:
 *
 *   odrv0.config.enable_uart_a = True
 *   odrv0.config.uart_a_baudrate = 115200
 *   odrv0.save_configuration()
 *
 * See the drivers/odrive_uart.c header note and
 * scripts/odrive_setup_uart.py. */
#define BIBA_PIN_ODRIVE_UART_TX_GPIO 4
#define BIBA_PIN_ODRIVE_UART_RX_GPIO 5
#define BIBA_ODRIVE_UART_INST        uart1
#define BIBA_ODRIVE_UART_BAUD        115200

/* --- IMU (I2C0, GP20=SDA / GP21=SCL) ----------------------------------- */
#define BIBA_PIN_I2C_SDA_GPIO        20
#define BIBA_PIN_I2C_SCL_GPIO        21
#define BIBA_PIN_IMU_INT1_GPIO       22
#define BIBA_I2C_INST                i2c0

/* --- ADC ---------------------------------------------------------------
 *
 * No native ADC channels are wired on this BLDC target by default.
 * The ODrive unit reports vbus_voltage / motor current over the ASCII
 * link, so the native ADC remains a clean reserve.
 * The macros below are kept defined (length 0) so any code that walks
 * BIBA_ADC_CHANNEL_SEQ will compile cleanly.
 */

#define BIBA_ADC_SCAN_LEN           0U
#define BIBA_ADC_CHANNEL_SEQ        { /* empty */ }

/* --- Status LED (GP25, onboard Pico LED, active high) ----------------- */

#define BIBA_PIN_STATUS_LED_GPIO     25
#define BIBA_STATUS_LED_ACTIVE_LOW   0

/* --- WS2812 RGB LED (GP23, YD-RP2040 onboard NeoPixel) ---------------- */

#define BIBA_PIN_RGB_LED_GPIO        23
#define BIBA_HAS_RGB_LED             1

#endif /* BIBA_TARGET_H */
