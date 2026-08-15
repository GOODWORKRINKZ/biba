/* ODrive ASCII-protocol driver over UART1 (GP4/GP5).
 *
 * This is the transport fallback for the CAN backend (drivers/odrive_can.c).
 * ODrive 0.5.x speaks a line-oriented ASCII protocol (`r` / `w` / `c`,
 * one command per `\n`) on its UART-A pins at 115200 baud by default.
 *
 * Why it exists: the CANSimple stack in ODrive fw 0.5.6 has a firmware
 * bug where, at idle (zero throttle), the CAN peripheral silently wedges
 * (both RX and TX die, can.error == 0, no bus-off).  The UART ASCII path
 * does not share that code path and stays alive, so it is the preferred
 * production transport.  Selected per-target via BIBA_ODRIVE_LINK_UART.
 *
 * Transport contract (mirrors odrive.h):
 *   biba_odrive_init()         — bring up UART1, send Set_Limits
 *   biba_odrive_set_enabled()  — `w axisN.requested_state {8|1}`
 *   biba_odrive_drive()        — stores setpoint; TX happens in tick
 *   biba_odrive_tick_50hz()    — TX input_vel @ 50 Hz + liveness poll
 *   biba_odrive_node_alive()   — "responded to a read recently"
 *
 * Liveness is measured by polling `r axisN.current_state` (round-robin,
 * ~10 Hz).  A successful parse refreshes that node's last-response
 * timestamp; biba_odrive_node_alive() compares it against
 * BIBA_ODRIVE_UART_TIMEOUT_MS.  Unlike the CAN backend there is no
 * silent-wedge, so no MSG_RESET_ODRIVE watchdog is needed.
 *
 * ODrive-side prerequisites (set once over USB CDC, then save):
 *   w odrv0.config.enable_uart_a 1
 *   w odrv0.config.uart_a_baudrate 115200
 *   w odrv0.save_configuration 0
 * (The ASCII protocol is what runs on UART-A; enable_ascii_protocol
 * is a USB-side concept and is already on for USB.)
 */

#include "odrive.h"

#include "biba_board.h"
#include "biba_config.h"
#include "hal/biba_hal.h"

#include "hardware/uart.h"
#include "hardware/gpio.h"

#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <stdlib.h>

/* Compile-time anchor: BLDC target + UART transport selected.  This TU
 * compiles to nothing on the CAN build (drivers/odrive_can.c wins). */
#if !defined(BIBA_TARGET_HAS_BLDC_2CH) || (BIBA_TARGET_HAS_BLDC_2CH == 0)
#  error "odrive_uart.c is for the BLDC target only — guard with src_filter or BIBA_TARGET_HAS_BLDC_2CH."
#endif

#if BIBA_ODRIVE_LINK_UART

/* ---- Per-node state --------------------------------------------------- */

typedef struct {
    bool     valid;             /* false until first response          */
    uint32_t last_response_ms;
    uint8_t  last_state;        /* axis_state value                    */
    float    last_iq_measured;  /* measured motor current (A)          */
} node_state_t;

#define MAX_ODRIVE_NODES  4u

static node_state_t s_nodes[MAX_ODRIVE_NODES];

/* ODrive-global bus voltage (V) — one ODrive drives both axes. */
static float s_bus_voltage;

/* ---- Driver-internal counters ---------------------------------------- */
static volatile uint32_t s_tx_count;
static volatile uint32_t s_rx_count;
static volatile uint32_t s_rx_raw;       /* raw bytes read (pre-parse) */
static volatile uint32_t s_decode_errors;

/* ---- High-level state ------------------------------------------------- */
static bool  s_enabled;
static float s_setpoint_left;
static float s_setpoint_right;
static uint32_t s_last_setpoint_ms_left;
static uint32_t s_last_setpoint_ms_right;

/* ---- UART RX line buffering -------------------------------------------
 *
 * ODrive ASCII responses are short (`8\n`, `53.086819\n`).  We poll RX
 * inside the tick (no IRQ) — at 115200 baud a response is a few bytes
 * and arrives in <1 ms, so a 50 Hz poll with a small buffer is ample.
 * Only one read is ever outstanding (see s_rx_expect), and `w` commands
 * produce no response, so every received line maps 1:1 to our pending
 * read. */
static char     s_rx_line[48];
static uint8_t  s_rx_len;

typedef enum {
    UART_RX_IDLE = 0,
    UART_RX_AXIS0_STATE,
    UART_RX_AXIS1_STATE,
    UART_RX_VBUS,
    UART_RX_AXIS0_IQ,
    UART_RX_AXIS1_IQ,
} uart_rx_expect_t;

static uart_rx_expect_t s_rx_expect;
static uint32_t         s_rx_expect_ms;   /* when the read was sent */
static uint32_t         s_last_poll_ms;

/* ---- TX helpers -------------------------------------------------------- */

static void uart_tx_raw(const char *s)
{
    uart_write_blocking(BIBA_ODRIVE_UART_INST, (const uint8_t *)s,
                        strlen(s));
    uart_putc_raw(BIBA_ODRIVE_UART_INST, '\n');
    s_tx_count++;
}

static void uart_tx_fmt(const char *fmt, ...)
{
    char buf[64];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    if (n < 0) n = 0;
    if ((size_t)n >= sizeof(buf)) n = (int)sizeof(buf) - 1;
    uart_write_blocking(BIBA_ODRIVE_UART_INST, (const uint8_t *)buf,
                        (size_t)n);
    uart_putc_raw(BIBA_ODRIVE_UART_INST, '\n');
    s_tx_count++;
}

/* ---- Set_Limits (both axes, velocity then current) --------------------- */

static void send_limits(void)
{
    uart_tx_fmt("w axis0.controller.config.vel_limit %f",
                (double)BIBA_ODRIVE_MAX_VEL_LIMIT_REV_S);
    uart_tx_fmt("w axis1.controller.config.vel_limit %f",
                (double)BIBA_ODRIVE_MAX_VEL_LIMIT_REV_S);
    uart_tx_fmt("w axis0.motor.config.current_lim %f",
                (double)BIBA_ODRIVE_MAX_CURRENT_A);
    uart_tx_fmt("w axis1.motor.config.current_lim %f",
                (double)BIBA_ODRIVE_MAX_CURRENT_A);
}

/* ---- RX parsing -------------------------------------------------------- */

static void handle_line(uint32_t now_ms)
{
    s_rx_count++;

    /* current_state is an integer enum; vbus / Iq are IEEE-754 floats.
     * strtol / strtof both tolerate a trailing `\r` or garbage. */
    float val  = strtof(s_rx_line, NULL);
    long state = strtol(s_rx_line, NULL, 0);
    if (state < 0) state = 0;
    if (state > 255) state = 255;

    switch (s_rx_expect) {
    case UART_RX_AXIS0_STATE:
        if (BIBA_ODRIVE_LEFT_NODE_ID < MAX_ODRIVE_NODES) {
            s_nodes[BIBA_ODRIVE_LEFT_NODE_ID].valid = true;
            s_nodes[BIBA_ODRIVE_LEFT_NODE_ID].last_response_ms = now_ms;
            s_nodes[BIBA_ODRIVE_LEFT_NODE_ID].last_state = (uint8_t)state;
        }
        break;
    case UART_RX_AXIS1_STATE:
        if (BIBA_ODRIVE_RIGHT_NODE_ID < MAX_ODRIVE_NODES) {
            s_nodes[BIBA_ODRIVE_RIGHT_NODE_ID].valid = true;
            s_nodes[BIBA_ODRIVE_RIGHT_NODE_ID].last_response_ms = now_ms;
            s_nodes[BIBA_ODRIVE_RIGHT_NODE_ID].last_state = (uint8_t)state;
        }
        break;
    case UART_RX_VBUS:
        s_bus_voltage = val;
        printf("[odrive] VBUS      = %6.2f V\r\n", val);
        break;
    case UART_RX_AXIS0_IQ:
        if (BIBA_ODRIVE_LEFT_NODE_ID < MAX_ODRIVE_NODES) {
            s_nodes[BIBA_ODRIVE_LEFT_NODE_ID].last_iq_measured = val;
            printf("[odrive] Iq LEFT   = %+6.2f A\r\n", val);
        }
        break;
    case UART_RX_AXIS1_IQ:
        if (BIBA_ODRIVE_RIGHT_NODE_ID < MAX_ODRIVE_NODES) {
            s_nodes[BIBA_ODRIVE_RIGHT_NODE_ID].last_iq_measured = val;
            printf("[odrive] Iq RIGHT  = %+6.2f A\r\n", val);
        }
        break;
    case UART_RX_IDLE:
    default:
        s_decode_errors++;
        break;
    }
    s_rx_expect = UART_RX_IDLE;
}

static void uart_drain_rx(uint32_t now_ms)
{
    while (uart_is_readable(BIBA_ODRIVE_UART_INST)) {
        char c = (char)uart_getc(BIBA_ODRIVE_UART_INST);
        s_rx_raw++;
        if (c == '\n') {
            s_rx_line[s_rx_len] = '\0';
            s_rx_len = 0;
            handle_line(now_ms);
        } else if (c != '\r' && s_rx_len < sizeof(s_rx_line) - 1u) {
            s_rx_line[s_rx_len++] = c;
        }
    }
}

/* ---- Input_Vel (rate-limited per node, mirrors CAN backend) ------------ */

static void send_set_input_vel(uint8_t node_id, float vel_rev_s,
                               uint32_t now_ms)
{
    uint32_t *last_ms = (node_id == BIBA_ODRIVE_LEFT_NODE_ID)
                          ? &s_last_setpoint_ms_left
                          : &s_last_setpoint_ms_right;
    const uint32_t min_period_ms = 1000u / BIBA_ODRIVE_SETPOINT_RATE_HZ;
    if ((now_ms - *last_ms) < min_period_ms) {
        return;
    }
    *last_ms = now_ms;

    const char axis = (node_id == BIBA_ODRIVE_LEFT_NODE_ID) ? '0' : '1';
    uart_tx_fmt("w axis%c.controller.input_vel %f", axis,
                (double)vel_rev_s);
}

/* ---- Public API -------------------------------------------------------- */

void biba_odrive_init(void)
{
    memset(s_nodes, 0, sizeof(s_nodes));
    s_bus_voltage = 0.0f;
    s_enabled = false;
    s_setpoint_left = s_setpoint_right = 0.0f;
    s_last_setpoint_ms_left = s_last_setpoint_ms_right = 0u;
    s_tx_count = s_rx_count = s_decode_errors = 0u;
    s_rx_len = 0u;
    s_rx_expect = UART_RX_IDLE;
    s_rx_expect_ms = 0u;
    s_last_poll_ms = 0u;

    uart_init(BIBA_ODRIVE_UART_INST, BIBA_ODRIVE_UART_BAUD);
    uart_set_fifo_enabled(BIBA_ODRIVE_UART_INST, true);
    gpio_set_function(BIBA_PIN_ODRIVE_UART_TX_GPIO, GPIO_FUNC_UART);
    gpio_set_function(BIBA_PIN_ODRIVE_UART_RX_GPIO, GPIO_FUNC_UART);

    /* Conservative limits on both axes at boot.  Re-issued on every
     * arm/disarm edge too (see set_enabled), mirroring the CAN backend. */
    send_limits();
}

void biba_odrive_set_enabled(bool enabled)
{
    if (enabled && (enabled == s_enabled)) {
        return;
    }
    s_enabled = enabled;

    /* CLOSED_LOOP_CONTROL = 8, IDLE = 1 (0 = UNDEFINED / ignored). */
    const int new_state = enabled ? 8 : 1;
    uart_tx_fmt("w axis0.requested_state %d", new_state);
    uart_tx_fmt("w axis1.requested_state %d", new_state);

    /* Re-issue limits so the hard envelope is in effect even after an
     * ODrive power-cycle or external NVM change. */
    send_limits();
}

void biba_odrive_drive(float left_duty, float right_duty)
{
    if (left_duty  >  1.0f) left_duty  =  1.0f;
    if (left_duty  < -1.0f) left_duty  = -1.0f;
    if (right_duty >  1.0f) right_duty =  1.0f;
    if (right_duty < -1.0f) right_duty = -1.0f;

    s_setpoint_left  = left_duty;
    s_setpoint_right = right_duty;
    /* Actual TX happens in biba_odrive_tick_50hz() to stay lock-step
     * with the control loop. */
}

void biba_odrive_thermal_reset(uint32_t pulse_us)
{
    (void)pulse_us;
    biba_odrive_set_enabled(false);
    biba_odrive_drive(0.0f, 0.0f);
}

void biba_odrive_drain_rx(void)
{
    uart_drain_rx(biba_hal_now_ms());
}

void biba_odrive_tick_50hz(void)
{
    uint32_t now = biba_hal_now_ms();

    /* Always drain RX first. */
    uart_drain_rx(now);

    /* Periodic UART1 RX health dump (~2 s). */
    static uint32_t s_last_uart_diag_ms;
    if (now - s_last_uart_diag_ms >= 2000u) {
        s_last_uart_diag_ms = now;
        uart_hw_t *h = uart_get_hw(BIBA_ODRIVE_UART_INST);
        printf("[odrive-uart] rx_raw=%lu rx_lines=%lu fr=0x%08lx rsr=0x%08lx expect=%d\r\n",
               (unsigned long)s_rx_raw,
               (unsigned long)s_rx_count,
               (unsigned long)h->fr,
               (unsigned long)h->rsr,
               (int)s_rx_expect);
    }

    /* Send Set_Input_Vel, rate-limited per node (50 Hz). */
    send_set_input_vel(BIBA_ODRIVE_LEFT_NODE_ID,
                       s_setpoint_left  * BIBA_ODRIVE_LEFT_DIR  *
                                          BIBA_ODRIVE_LEFT_MAX_VEL_REV_S,
                       now);
    send_set_input_vel(BIBA_ODRIVE_RIGHT_NODE_ID,
                       s_setpoint_right * BIBA_ODRIVE_RIGHT_DIR *
                                          BIBA_ODRIVE_RIGHT_MAX_VEL_REV_S,
                       now);

    /* Liveness poll: round-robin `r axisN.current_state` at ~10 Hz.
     * One read in flight at a time; if the previous read timed out,
     * drop it and move on so liveness recovers cleanly. */
    if (s_rx_expect != UART_RX_IDLE &&
        (now - s_rx_expect_ms) >= BIBA_ODRIVE_UART_TIMEOUT_MS) {
        s_rx_expect = UART_RX_IDLE;
    }
    if (s_rx_expect == UART_RX_IDLE &&
        (now - s_last_poll_ms) >= 100u) {
        s_last_poll_ms = now;
        /* Round-robin liveness + telemetry reads: state (both axes) at
         * ~200 ms each, plus vbus + Iq (both axes) for the telemetry
         * uplink.  One read in flight at a time. */
        static uint8_t s_poll_step;
        switch (s_poll_step) {
        case 0:
            uart_tx_raw("r axis0.current_state");
            s_rx_expect = UART_RX_AXIS0_STATE;
            break;
        case 1:
            uart_tx_raw("r axis1.current_state");
            s_rx_expect = UART_RX_AXIS1_STATE;
            break;
        case 2:
            uart_tx_raw("r vbus_voltage");
            s_rx_expect = UART_RX_VBUS;
            break;
        case 3:
            uart_tx_raw("r axis0.motor.current_control.Iq_measured");
            s_rx_expect = UART_RX_AXIS0_IQ;
            break;
        default:
            uart_tx_raw("r axis1.motor.current_control.Iq_measured");
            s_rx_expect = UART_RX_AXIS1_IQ;
            break;
        }
        s_poll_step = (uint8_t)((s_poll_step + 1u) % 5u);
        s_rx_expect_ms = now;
    }

    /* Keep the requested_state in effect: if disarmed but a node still
     * reports CLOSED_LOOP, re-send IDLE; if armed but not yet closed,
     * re-send CLOSED_LOOP (mirrors the CAN backend's retry). */
    if (!s_enabled) {
        if (s_nodes[BIBA_ODRIVE_LEFT_NODE_ID].valid &&
            s_nodes[BIBA_ODRIVE_LEFT_NODE_ID].last_state == 0x08u) {
            uart_tx_raw("w axis0.requested_state 1");
        }
        if (s_nodes[BIBA_ODRIVE_RIGHT_NODE_ID].valid &&
            s_nodes[BIBA_ODRIVE_RIGHT_NODE_ID].last_state == 0x08u) {
            uart_tx_raw("w axis1.requested_state 1");
        }
    } else {
        if (s_nodes[BIBA_ODRIVE_LEFT_NODE_ID].valid &&
            s_nodes[BIBA_ODRIVE_LEFT_NODE_ID].last_state != 0x08u) {
            uart_tx_raw("w axis0.requested_state 8");
        }
        if (s_nodes[BIBA_ODRIVE_RIGHT_NODE_ID].valid &&
            s_nodes[BIBA_ODRIVE_RIGHT_NODE_ID].last_state != 0x08u) {
            uart_tx_raw("w axis1.requested_state 8");
        }
    }
}

bool biba_odrive_node_alive(uint8_t node_id)
{
    if (node_id >= MAX_ODRIVE_NODES) return false;
    if (!s_nodes[node_id].valid)      return false;
    uint32_t now = biba_hal_now_ms();
    return (now - s_nodes[node_id].last_response_ms) <
            BIBA_ODRIVE_UART_TIMEOUT_MS;
}

/* ---- Debug counters ---------------------------------------------------- */

uint32_t biba_odrive_tx_count(void)       { return s_tx_count; }
uint32_t biba_odrive_rx_count(void)       { return s_rx_count; }
uint32_t biba_odrive_decode_errors(void)  { return s_decode_errors; }
uint32_t biba_odrive_recovery_count(void) { return 0u; }   /* no MCP2515 */
uint32_t biba_odrive_reset_count(void)    { return 0u; }   /* no watchdog */

/* ---- Telemetry getters ------------------------------------------------ */

float biba_odrive_bus_voltage(void)
{
    return s_bus_voltage;
}

float biba_odrive_iq_measured(uint8_t node_id)
{
    if (node_id >= MAX_ODRIVE_NODES) return 0.0f;
    return s_nodes[node_id].last_iq_measured;
}

#endif /* BIBA_ODRIVE_LINK_UART */
