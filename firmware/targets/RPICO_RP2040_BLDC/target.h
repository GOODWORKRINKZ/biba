#ifndef BIBA_TARGET_H
#define BIBA_TARGET_H

/* Target: RPICO_RP2040_BLDC
 *
 * RP2040-based BLDC control board. Communicates with two ODrive
 * controllers via a single MCP2515+TJA1050 SPI→CAN module. Replaces
 * the brushed BTS7960 boards of the existing RPICO_RP2040 target.
 *
 * Pin assignment — left side (GP0-GP15, top to bottom):
 *
 *   GP0  UART0_TX   CRSF TX → receiver
 *   GP1  UART0_RX   CRSF RX ← receiver
 *   GP2  —           (free, PWM1A not used)
 *   GP3  —           (free, PWM1B not used)
 *   GP4  UART1_TX   ODRIVE_ASY_TX (UART ASCII fallback, opt)
 *   GP5  UART1_RX   ODRIVE_ASY_RX (UART ASCII fallback, opt)
 *   GP6  —           (free, PWM3A not used)
 *   GP7  —           (free, PWM3B not used)
 *   GP8  —           (free)
 *   GP9  —           (free)
 *   GP10 —           (free)
 *   GP11 —           (free)
 *   GP12 —           (free)
 *   GP13 —           (free)
 *   GP14 —           (free)
 *   GP15 GPIO IRQ    MCP2515 INT (open-drain, active low)
 *
 * Pin assignment — right side (GP16-GP29, bottom to top):
 *
 *   GP16 SPI0 MISO  MCP2515 SO  (RX)
 *   GP17 GPIO OUT   MCP2515 CS  (chip select, active low)
 *   GP18 SPI0 SCK   MCP2515 SCK
 *   GP19 SPI0 MOSI  MCP2515 SI  (TX)
 *   GP20 I2C0_SDA   IMU + ADS1115 + AHT30 (shared I2C0 bus)
 *   GP21 I2C0_SCL   IMU + ADS1115 + AHT30 (shared I2C0 bus)
 *   GP22 GPIO IN    IMU INT1
 *   GP23 GPIO OUT   (NeoPixel WS2812 — same as RPICO_RP2040)
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
 * Discovery: CNF3/CNF2/CNF1 set 250 kbps with 87.5% sample point.
 * The firmware issues one CAN Address broadcast (cmd_id 0x06, RTR=1)
 * at boot and listens for the ODrive heartbeat within 1 s.
 */

#define BIBA_TARGET_NAME            "RPICO_RP2040_BLDC"

/* --- Capability flags ------------------------------------------------- */

/* BTS7960 driver removed: drive API is now backed by biba_odrive_can. */
#define BIBA_TARGET_HAS_BTS7960_2CH  0
#define BIBA_TARGET_HAS_BLDC_2CH     1

/* New peripheral capability flag introduced for this target. */
#define BIBA_TARGET_HAS_MCP2515      1

/* Same as RPICO_RP2040 — CRSF through UART0. */
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

/* Drive duty on this target is encoded into CANSimple Set_Input_Vel;
 * the BTS7960 PWM pin macros are intentionally NOT defined here. The
 * portable code in src/hal/biba_hal_motor.c, src/hal/biba_hal_motor_rp2040.c
 * and src/drivers/bts7960.c is excluded by [rp2040_bldc_src_filter].
 *
 * Numerical mapping [-1.0, +1.0] → rev/s comes from target_config.h:
 *   - BIBA_ODRIVE_LEFT_MAX_VEL_REV_S
 *   - BIBA_ODRIVE_RIGHT_MAX_VEL_REV_S
 * (set conservatively; ODrive enforces its own limits via Set_Limits).
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

/* --- MCP2515 SPI0 bus (CAN bridge) ------------------------------------ */

/* GP16 SPI0 MISO, GP17 CS, GP18 SCK, GP19 MOSI.
 * Datasheet pin assignments are dictated by the RP2040 SPI0 peripheral
 * — see RP2040 datasheet §1.4.3 "Function Select Table". */
#define BIBA_PIN_SPI0_MISO_GPIO      16   /* SPI0 RX  ← MCP2515 SO  */
#define BIBA_PIN_SPI0_CS_GPIO        17   /* GPIO    → MCP2515 CS  */
#define BIBA_PIN_SPI0_SCK_GPIO       18   /* SPI0 SCK → MCP2515 SCK */
#define BIBA_PIN_SPI0_MOSI_GPIO      19   /* SPI0 TX  → MCP2515 SI  */
#define BIBA_MCP2515_SPI_INST        spi0

/* MCP2515 INT — open-drain, active low. Wired to GP15 (no secondary
 * SPI/UART function on standard Pico pinout). MCP2515 module already
 * has on-board 10 kΩ pull-up to its Vdd. */
#define BIBA_PIN_MCP2515_INT_GPIO    15

/* MCP2515 clocks — see §2.1 of docs/mcp2515_bldc_research.md. */
#define BIBA_MCP2515_SPI_BAUD_HZ     7812500   /* divider 16 from clk_peri=125 MHz */
#define BIBA_MCP2515_CPOL            0
#define BIBA_MCP2515_CPHA            0
#define BIBA_MCP2515_BIT_ORDER       SPI_MSB_FIRST

/* --- IMU (I2C0, GP20=SDA / GP21=SCL) ----------------------------------- */
#define BIBA_PIN_I2C_SDA_GPIO        20
#define BIBA_PIN_I2C_SCL_GPIO        21
#define BIBA_PIN_IMU_INT1_GPIO       22
#define BIBA_I2C_INST                i2c0

/* --- ADC ---------------------------------------------------------------
 *
 * No native ADC channels are wired on this BLDC target by default.
 * The ODrive unit reports Bus_Voltage / FET_Temperature / Motor_Temperature
 * over CAN, so the native ADC remains a clean reserve.
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
