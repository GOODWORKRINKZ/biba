#ifndef BIBA_TARGET_H
#define BIBA_TARGET_H

/* Target: RP2040_BRIDGE_PWM2CRSF
 *
 * Not a BiBa controller: a stand-alone Raspberry Pi Pico (RP2040) that
 * reads 6 servo-PWM channels from a HotRC receiver and emits CRSF on
 * UART0, so it plugs into BiBa's CRSF port in place of the ELRS receiver.
 * Firmware entry: src/pwm2crsf/pwm2crsf_main.cpp, env `rp2040_bridge_pwm2crsf`.
 *
 * Pin assignment:
 *
 *   GP0  UART0_TX  CRSF out → BiBa CRSF RX (BiBa GP1)
 *   GP1  UART0_RX  CRSF in  ← BiBa CRSF TX (BiBa GP0), read and ignored
 *   GP2  GPIO IN   PWM input 1 ← HotRC CH1
 *   GP3  GPIO IN   PWM input 2 ← HotRC CH2
 *   GP4  GPIO IN   PWM input 3 ← HotRC CH3
 *   GP5  GPIO IN   PWM input 4 ← HotRC CH4
 *   GP6  GPIO IN   PWM input 5 ← HotRC CH5
 *   GP7  GPIO IN   PWM input 6 ← HotRC CH6
 *   GP25 GPIO OUT  Onboard LED: solid = link, blinking = failsafe
 *
 * RP2040 GPIOs are 3.3 V only. See target.md before wiring a receiver
 * whose signal swings to 5 V.
 */

#define BIBA_TARGET_NAME             "RP2040_BRIDGE_PWM2CRSF"

#if !defined(BIBA_NATIVE_TEST)
#  include "pico/stdlib.h"
#  include "hardware/gpio.h"
#  include "hardware/uart.h"
#  include "hardware/irq.h"
#endif

/* --- CRSF output (UART0) ----------------------------------------------- */

#define PWM2CRSF_PIN_CRSF_TX_GPIO    0
#define PWM2CRSF_PIN_CRSF_RX_GPIO    1
#define PWM2CRSF_CRSF_UART_INST      uart0

/* --- PWM inputs -------------------------------------------------------- */

#define PWM2CRSF_INPUT_COUNT         6u
#define PWM2CRSF_INPUT_PINS          { 2, 3, 4, 5, 6, 7 }

/* --- Status LED -------------------------------------------------------- */

#define PWM2CRSF_PIN_LED_GPIO        25

#endif /* BIBA_TARGET_H */
