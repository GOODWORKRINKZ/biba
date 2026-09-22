#ifndef BIBA_TARGET_H
#define BIBA_TARGET_H

/* Target: RP2040_BLDC_VESC_CAN
 *
 * Name follows the <MCU>_<MOTOR>_<DRIVER>_<LINK> standard documented
 * in firmware/targets/README.md: RP2040 + BLDC motors + VESC
 * controllers + CAN link.
 *
 * RP2040-based BLDC control board driving a **Flipsky dual FSESC**
 * (two VESC halves on one board) through a single MCP2515+TJA1050
 * SPI→CAN module.  Electrically identical to RP2040_BLDC_ODRIVE_CAN —
 * same MCP2515 wiring, same pinout — but a different controller
 * dialect: 29-bit extended ids at 500 kbps instead of ODrive
 * CANSimple's 11-bit ids at 250 kbps.  See ADR-0002 and
 * src/drivers/vesc_can.c.
 *
 * Wiring to the FSESC (per the Flipsky wiring sheet):
 *
 *   FSESC connector 1 "CAN"  →  MCP2515 module
 *     CAH  (CAN-H)           →  TJA1050 CANH
 *     CAL  (CAN-L)           →  TJA1050 CANL
 *     -    (GND)             →  common ground
 *     5V                     →  leave unconnected; the MCP2515 module
 *                               is powered from the Pico's 5 V rail so
 *                               a FSESC reboot does not brown it out.
 *
 * Only ONE of the two CAN connectors needs wiring: on a dual FSESC the
 * two halves already share the internal CAN bus.  Keep the board's
 * dual/single switch in the **ON: dual** position so both halves
 * arbitrate on that bus.
 *
 * Termination: the FSESC has no 120 Ω terminator.  The MCP2515 module
 * carries a 120 Ω jumper — leave it fitted.  A single terminator on a
 * sub-metre bus is out of spec but works reliably at 500 kbps; if the
 * bus errors, add a second 120 Ω at the FSESC end.
 *
 * Pin assignment — left side (GP0-GP15, top to bottom):
 *
 *   GP0  UART0_TX   CRSF TX → receiver
 *   GP1  UART0_RX   CRSF RX ← receiver
 *   GP2  —           (free, PWM1A not used)
 *   GP3  —           (free, PWM1B not used)
 *   GP4  UART1_TX   reserved: VESC UART link (FSESC "COMM" TX)
 *   GP5  UART1_RX   reserved: VESC UART link (FSESC "COMM" RX)
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
 *   GP23 GPIO OUT   (NeoPixel WS2812 — same as RP2040_DC_BTS7960_PWM)
 *   GP25 GPIO OUT   Status LED (Pico onboard, active high)
 *   GP26 ADC0       (reserved — n/a on this target)
 *   GP27 ADC1       (reserved — n/a on this target)
 *   GP28 ADC2       (reserved — n/a on this target)
 *   GP29 ADC3       (reserved — n/a on this target)
 *
 * GP4/GP5 are reserved, not wired: the VESC UART link would be its own
 * target (RP2040_BLDC_VESC_UART) under the naming standard, and it
 * does not exist yet.
 *
 * No BTS7960 IS pins are wired — motor current comes from the VESC
 * itself (CAN_PACKET_STATUS).  Native ADC pins remain available for
 * thermal / VBAT monitoring if the project ever adds a board-side
 * power-rail sense.
 *
 * Controller ids:
 *   - id 0 → LEFT  VESC
 *   - id 1 → RIGHT VESC
 * Both FSESC halves ship as id 0, so the right-hand one MUST be
 * changed in VESC Tool (App Settings → General → VESC ID) before the
 * firmware can tell them apart.  Overridable in target_config.h.
 *
 * Bus: 500 kbps, 29-bit extended ids, MCP2515 in accept-all mode
 * (BIBA_MCP2515_ACCEPT_ALL) — see src/drivers/vesc_can.h for why the
 * hardware filters cannot express "any VESC, these packet types".
 */

#define BIBA_TARGET_NAME            "RP2040_BLDC_VESC_CAN"

/* --- Capability flags ------------------------------------------------- */

/* No BTS7960: the drive API is backed by drivers/vesc_can.c. */
#define BIBA_TARGET_HAS_BTS7960_2CH  0
#define BIBA_TARGET_HAS_BLDC_2CH     1

/* Which BLDC backend implements drivers/bldc.h on this target.
 * Exactly one of the BACKEND flags may be 1 (see ADR-0002 §3). */
#define BIBA_TARGET_BLDC_BACKEND_ODRIVE  0
#define BIBA_TARGET_BLDC_BACKEND_VESC    1

/* SPI→CAN bridge present. */
#define BIBA_TARGET_HAS_MCP2515      1

/* Same as RP2040_DC_BTS7960_PWM — CRSF through UART0. */
#define BIBA_TARGET_HAS_CRSF         1

/* IMU stays on I2C0 GP20/21, no conflict. */
#define BIBA_TARGET_HAS_IMU          1

/* SBC link is USB-CDC on the BLDC variants. */
#define BIBA_TARGET_HAS_SPI_SLAVE    0

/* No BTS7960 → no motor-audio API on this target. */
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

/* Drive duty on this target is encoded into a VESC CAN command
 * (SET_DUTY / SET_RPM / SET_CURRENT, picked by
 * BIBA_VESC_CONTROL_MODE); the BTS7960 PWM pin macros are
 * intentionally NOT defined here.  The portable code in
 * src/hal/biba_hal_motor.c, src/hal/biba_hal_motor_rp2040.c and
 * src/drivers/bts7960.c is excluded by [rp2040_bldc_vesc_src_filter].
 *
 * Numerical mapping of [-1.0, +1.0] comes from target_config.h:
 *   - BIBA_VESC_MAX_DUTY      (duty mode, the default)
 *   - BIBA_VESC_MAX_ERPM      (ERPM mode)
 *   - BIBA_VESC_MAX_CURRENT_A (current mode)
 * The VESC additionally clamps every command against its own motor
 * configuration, which stays the real safety limit.
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
 * gadget itself.
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
 * No native ADC channels are wired on this target.  The VESC reports
 * input voltage, motor current and FET / motor temperature over CAN
 * (CAN_PACKET_STATUS / _4 / _5), so the native ADC remains a clean
 * reserve.  The macros below are kept defined (length 0) so any code
 * that walks BIBA_ADC_CHANNEL_SEQ still compiles cleanly.
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
