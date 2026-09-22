/* BLDC motor HAL-shim, shared by every BIBA_TARGET_HAS_BLDC_2CH
 * target (ODrive over CAN or UART, VESC over CAN).
 *
 * Two responsibilities that don't fit into either `drivers/mcp2515.c`
 * (register-level) or the protocol backends `drivers/odrive_can.c` /
 * `drivers/odrive_uart.c` / `drivers/vesc_can.c`:
 *
 *   1. On targets with BIBA_TARGET_HAS_MCP2515, wire the MCP2515 INT
 *      GPIO to the ISR callback exposed by `drivers/mcp2515.c`.  Done
 *      as a GPIO IRQ callback (rather than an exclusive vector) so we
 *      don't have to claim a hard IRQ channel — the only other shared GPIO IRQ on this project is
 *      the IMU INT1, which already uses the same edge-fallback
 *      scheme.  See target.h `BIBA_PIN_MCP2515_INT_GPIO`.
 *
 *   2. Provide no-op stubs for the BTS7960 PWM/PCM/Audio HAL
 *      surface area.  This target has no BTS7960 hardware, so the
 *      functions `biba_hal_motor_pwm_*`, `biba_hal_motor_audio_*`
 *      and `biba_hal_motor_pcm_*` from `biba_hal.h` resolve here as
 *      harmless no-ops.  Mode code that asks for audio on this
 *      target gets `false` (already-correct behaviour).
 *
 * The driver functions (`biba_bldc_set_enabled`, `biba_bldc_drive`,
 * `biba_bldc_thermal_reset`) live in the backend TU selected by the
 * env's src_filter, not here — they are not "HAL primitives", they're
 * protocol adapters.  See `drivers/bldc.h` for the contract.
 */

#include "hal/biba_hal.h"

#include "biba_board.h"
#include "biba_config.h"

#include "drivers/bldc.h"

#if defined(BIBA_TARGET_HAS_MCP2515) && (BIBA_TARGET_HAS_MCP2515 != 0)
#  include "drivers/mcp2515.h"
#endif

#include "hardware/gpio.h"
#include "pico/time.h"

#include <stddef.h>

#if defined(BIBA_TARGET_HAS_BLDC_2CH) && (BIBA_TARGET_HAS_BLDC_2CH != 0)

#include "app/control_loop.h"
#include "drivers/current_sense.h"
#include "drivers/voltage_sense.h"

/* --- MCP2515 INT → ISR callback wiring ------------------------------- *
 *
 * CAN-linked targets only.  RP2040_BLDC_ODRIVE_UART speaks ASCII over
 * UART1 and has no bridge chip, so it defines
 * BIBA_TARGET_HAS_MCP2515 = 0 and skips this whole section (including
 * the BIBA_PIN_MCP2515_INT_GPIO macro, which it does not define).
 */

#if defined(BIBA_TARGET_HAS_MCP2515) && (BIBA_TARGET_HAS_MCP2515 != 0)

static bool s_motor_bldc_irq_registered;

/* Forward-declared in drivers/mcp2515.h as the GPIO-IRQ entry point.
 * We bind it directly via the modern pico-sdk
 * gpio_set_irq_enabled_with_callback() — the older
 * gpio_set_irq_callback() global-callback path is no longer present
 * in the mbed-based arduino-pico framework (mbed pico-sdk 1.x → 2.x
 * migration).  The HAL-shim owns the wiring so the driver itself
 * stays portable. */
static void mcp2515_int_on_irq(uint gpio, uint32_t events)
{
    (void)gpio;
    (void)events;
    biba_mcp2515_rx_isr();
}

static void biba_hal_motor_pwm_init_bldc(void)
{
    /* Begin the high-level BLDC driver; it owns the SPI bring-up and
     * whatever boot-time configuration its protocol needs. */
    biba_bldc_init();

    if (!s_motor_bldc_irq_registered) {
        /* Enable the falling-edge IRQ and register the per-pin
         * callback in one call (mbed pico-sdk 2.x API).  Doing this
         * after the driver is alive ensures an early stray edge does
         * not dereference a NULL queue. */
        gpio_set_irq_enabled_with_callback(BIBA_PIN_MCP2515_INT_GPIO,
                                           GPIO_IRQ_EDGE_FALL,
                                           true,
                                           &mcp2515_int_on_irq);
        s_motor_bldc_irq_registered = true;
    }
}

#else  /* no SPI→CAN bridge on this target */

static void biba_hal_motor_pwm_init_bldc(void)
{
    /* Nothing to wire: the backend owns its UART and has no INT pin. */
    biba_bldc_init();
}

#endif /* BIBA_TARGET_HAS_MCP2515 */

/* Exposed by biba_hal_init() in biba_hal_rp2040.c as the bring-up
 * hook for the motor subsystem.  The brushed-DC implementation in
 * src/hal/biba_hal_motor_rp2040.c is excluded on the BLDC targets
 * by their src_filter, so this definition wins. */
void biba_hal_motor_pwm_init(void)
{
    biba_hal_motor_pwm_init_bldc();
}

/* --- No-op PWM HAL ---------------------------------------------------- */

/* These stubs exist because biba_hal_motor.c (per-channel-timer
 * implementation) and biba_hal_motor_rp2040.c (BTS7960 PWM) are both
 * excluded on this target.  biba_hal.h declares the API. */
void biba_hal_motor_pwm_left (float duty) { (void)duty; }
void biba_hal_motor_pwm_right(float duty) { (void)duty; }

bool biba_hal_motor_audio_begin(void) { return false; }
bool biba_hal_motor_audio_end  (void) { return false; }
bool biba_hal_motor_audio_set_all(const uint32_t freq_hz[4],
                                  const float    duty_unit[4])
{
    (void)freq_hz; (void)duty_unit;
    return false;
}

bool biba_hal_motor_pcm_play(const uint8_t *samples, uint32_t count,
                              uint32_t rate_hz)
{
    (void)samples; (void)count; (void)rate_hz;
    return false;
}
bool biba_hal_motor_pcm_active(void) { return false; }
void biba_hal_motor_pcm_stop (void) {}

/* --- BTS7960 enable pins (no BTS7960 → do nothing) ------------------- */

void biba_hal_left_enable (bool enabled) { (void)enabled; }
void biba_hal_right_enable(bool enabled) { (void)enabled; }

/* No `biba_bts7960_*` aliases here on purpose: ADR-0001 §1.5 calls
 * for the application code to switch on `BIBA_TARGET_HAS_*` and call
 * `biba_bldc_*` directly, rather than masking the dispatch behind
 * a re-named BTS7960 symbol.  See #if chains in src/modes/*.c. */

/* --- Hook called from biba_hal_init() (defined per-target) ----------- *
 *
 * biba_hal_init() in src/hal/biba_hal_rp2040.c calls
 * biba_hal_motor_pwm_init() unconditionally after the GPIO bring-up.
 * On this target that symbol lives here, so we define it non-weak so
 * it wins over the brushed-DC default.
 */

/* --- Stubs for current / voltage sense -------------------------------- *
 *
 * The BLDC target has no native ADC channels (BIBA_ADC_SCAN_LEN = 0
 * in target.h).  Motor current and bus voltage are reported by the
 * ODrive controller over CAN (Get_Iq / Get_Bus_Voltage_Current).  The
 * firmware's telemetry / failsafe paths still expect the legacy
 * biba_current_sense_* / biba_voltage_sense_* symbols to exist, so
 * we provide them here as harmless zero-returning stubs.  This avoids
 * having to scatter #if BIBA_TARGET_HAS_BLDC_2CH guards across
 * mode_standalone.c / mode_companion.c / telemetry.c.
 *
 * The real values are surfaced via ODrive CAN → odrive_can.c →
 * decoded into s_nodes[].last_* — see the BIBA_ODRIVE_HEARTBEAT_*
 * macros in target_config.h.
 */

void biba_current_sense_configure(biba_current_calibration_t left,
                                  biba_current_calibration_t right)
{
    (void)left;
    (void)right;
}

biba_motor_current_t biba_current_sense_left(void)
{
    biba_motor_current_t z = {
        .current_a = biba_bldc_iq_measured(BIBA_BLDC_LEFT_NODE_ID),
        .valid = biba_bldc_node_alive(BIBA_BLDC_LEFT_NODE_ID),
    };
    return z;
}

biba_motor_current_t biba_current_sense_right(void)
{
    biba_motor_current_t z = {
        .current_a = biba_bldc_iq_measured(BIBA_BLDC_RIGHT_NODE_ID),
        .valid = biba_bldc_node_alive(BIBA_BLDC_RIGHT_NODE_ID),
    };
    return z;
}

uint16_t biba_voltage_sense_vbat_mv(void)
{
    return (uint16_t)(biba_bldc_bus_voltage() * 1000.0f);
}
uint16_t biba_voltage_sense_rail_mv(void) { return 0u; }
float    biba_voltage_sense_ibat_a(void)  { return 0.0f; }

#endif /* BIBA_TARGET_HAS_BLDC_2CH */