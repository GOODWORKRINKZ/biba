#include "vesc_can.h"

#include "biba_board.h"
#include "biba_config.h"
#include "hal/biba_hal.h"

#include <string.h>

/* Compile-time anchor: this TU is only built on a VESC BLDC target. */
#if !defined(BIBA_TARGET_BLDC_BACKEND_VESC) || (BIBA_TARGET_BLDC_BACKEND_VESC == 0)
#  error "vesc_can.c is for the VESC BLDC target only — guard with src_filter or BIBA_TARGET_BLDC_BACKEND_VESC."
#endif

#include "drivers/mcp2515.h"
#include "drivers/can_queue.h"

/* ---- VESC encoding helpers ------------------------------------------ *
 *
 * All VESC payloads are BIG-endian (see vesc_can.h).  The id is a
 * 29-bit extended identifier: controller_id | (packet_id << 8).
 */

static inline uint32_t vesc_frame_id(uint8_t node_id, uint8_t packet_id)
{
    return (uint32_t)node_id | ((uint32_t)packet_id << 8u);
}

static void pack_i32_be(uint8_t *dst, int32_t v)
{
    uint32_t u = (uint32_t)v;
    dst[0] = (uint8_t)((u >> 24) & 0xFFu);
    dst[1] = (uint8_t)((u >> 16) & 0xFFu);
    dst[2] = (uint8_t)((u >>  8) & 0xFFu);
    dst[3] = (uint8_t)( u        & 0xFFu);
}

static int32_t unpack_i32_be(const uint8_t *src)
{
    uint32_t u = ((uint32_t)src[0] << 24) | ((uint32_t)src[1] << 16) |
                 ((uint32_t)src[2] <<  8) |  (uint32_t)src[3];
    return (int32_t)u;
}

static int16_t unpack_i16_be(const uint8_t *src)
{
    uint16_t u = (uint16_t)(((uint16_t)src[0] << 8) | (uint16_t)src[1]);
    return (int16_t)u;
}

/* Returns false if the TX queue is full. */
static bool send_to_mcp(uint8_t node_id, uint8_t packet_id,
                        const uint8_t *data, uint8_t dlc)
{
    biba_can_frame_t f = {
        .id  = vesc_frame_id(node_id, packet_id),
        .ext = true,               /* VESC always uses 29-bit ids */
        .dlc = dlc,
    };
    if (dlc > 0u && data != NULL) {
        memcpy(f.data, data, dlc);
    }
    return biba_can_queue_tx_push(&f);
}

/* ---- Per-node state -------------------------------------------------- *
 *
 * Two VESC nodes (left / right).  On a Flipsky dual FSESC the two
 * halves sit on the same bus with distinct controller ids — they must
 * be set to BIBA_BLDC_LEFT_NODE_ID / BIBA_BLDC_RIGHT_NODE_ID in VESC
 * Tool, since both ship as id 0 from the factory.
 *
 * The id is a full byte on VESC (vs 6 bits on ODrive), but we only
 * track the low ids we assign; anything above the table is ignored.
 */
typedef struct {
    bool     valid;             /* false until the first status frame  */
    uint32_t last_status_ms;
    float    last_erpm;
    float    last_current_a;    /* motor current, STATUS               */
    float    last_duty;         /* -1 .. +1, STATUS                    */
    float    last_in_voltage;   /* V, STATUS_5                         */
    float    last_in_current;   /* A, STATUS_4                         */
    int16_t  last_fet_temp_c;   /* STATUS_4                            */
    int16_t  last_motor_temp_c; /* STATUS_4                            */
} node_state_t;

#define MAX_VESC_NODES  8u

static node_state_t s_nodes[MAX_VESC_NODES];

/* ---- Driver-internal counters ---------------------------------------- */
static volatile uint32_t s_tx_count;
static volatile uint32_t s_rx_count;
static volatile uint32_t s_decode_errors;

/* ---- High-level BTS7960-shaped API ----------------------------------- */

static bool  s_enabled;
static float s_setpoint_left;
static float s_setpoint_right;
static uint32_t s_last_setpoint_ms_left;
static uint32_t s_last_setpoint_ms_right;

/* Emit one drive command for `node_id`.  `cmd` is the normalised
 * [-1, +1] setpoint; the wire encoding depends on
 * BIBA_VESC_CONTROL_MODE. */
static void send_setpoint(uint8_t node_id, float cmd)
{
    uint8_t payload[4];

#if BIBA_VESC_CONTROL_MODE == BIBA_VESC_MODE_ERPM
    /* Closed-loop speed.  Needs a sensored (or well-tuned sensorless)
     * motor config — an unconfigured VESC simply stalls here, which is
     * why DUTY is the default. */
    pack_i32_be(payload, (int32_t)(cmd * (float)BIBA_VESC_MAX_ERPM));
    send_to_mcp(node_id, VESC_PKT_SET_RPM, payload, sizeof(payload));

#elif BIBA_VESC_CONTROL_MODE == BIBA_VESC_MODE_CURRENT
    /* Torque control: amps × 1000. */
    pack_i32_be(payload,
                (int32_t)(cmd * BIBA_VESC_MAX_CURRENT_A * 1000.0f));
    send_to_mcp(node_id, VESC_PKT_SET_CURRENT, payload, sizeof(payload));

#else /* BIBA_VESC_MODE_DUTY — default */
    /* Open-loop duty: duty × 100000.  Works on any motor the VESC has
     * completed detection for, with no encoder or PID tuning. */
    pack_i32_be(payload,
                (int32_t)(cmd * BIBA_VESC_MAX_DUTY * 100000.0f));
    send_to_mcp(node_id, VESC_PKT_SET_DUTY, payload, sizeof(payload));
#endif
}

void biba_bldc_init(void)
{
    memset(s_nodes, 0, sizeof(s_nodes));
    s_enabled = false;
    s_setpoint_left = s_setpoint_right = 0.0f;
    s_last_setpoint_ms_left = s_last_setpoint_ms_right = 0u;
    s_tx_count = s_rx_count = s_decode_errors = 0u;

    biba_can_queue_rx_init();
    biba_can_queue_tx_init();

    (void)biba_mcp2515_init();      /* idempotent, see driver header */

    /* Unlike ODrive there is nothing to configure over the bus: the
     * VESC's current / ERPM / duty limits live in its own motor
     * configuration (VESC Tool → Motor Settings) and CAN commands are
     * clamped against them controller-side.  We only announce
     * ourselves with a PING so a bench listener sees the link come up;
     * the PONG reply counts as liveness evidence too. */
    send_to_mcp(BIBA_BLDC_LEFT_NODE_ID,  VESC_PKT_PING, NULL, 0u);
    send_to_mcp(BIBA_BLDC_RIGHT_NODE_ID, VESC_PKT_PING, NULL, 0u);
}

void biba_bldc_set_enabled(bool enabled)
{
    /* Arming is edge-triggered; disarming is not.  Re-asserting the
     * zero setpoint is cheap, and a stale non-zero command would
     * otherwise keep the wheel turning until the VESC's own timeout
     * expires. */
    if (enabled && (enabled == s_enabled)) {
        return;
    }
    s_enabled = enabled;

    if (!enabled) {
        /* There is no VESC "axis state" to request — disarming means
         * commanding zero and then staying quiet.  The VESC's command
         * timeout (App Settings → General, 1 s by default) is the
         * backstop if even this frame is lost. */
        s_setpoint_left = s_setpoint_right = 0.0f;
        send_setpoint(BIBA_BLDC_LEFT_NODE_ID,  0.0f);
        send_setpoint(BIBA_BLDC_RIGHT_NODE_ID, 0.0f);
    }
}

void biba_bldc_drive(float left_duty, float right_duty)
{
    /* Clamp to [-1, +1] (guards against racing RC failure modes). */
    if (left_duty  >  1.0f) left_duty  =  1.0f;
    if (left_duty  < -1.0f) left_duty  = -1.0f;
    if (right_duty >  1.0f) right_duty =  1.0f;
    if (right_duty < -1.0f) right_duty = -1.0f;

    s_setpoint_left  = left_duty;
    s_setpoint_right = right_duty;
    /* The actual CAN transmit happens inside the 50 Hz tick so we stay
     * lock-step with the control loop. */
}

void biba_bldc_thermal_reset(uint32_t pulse_us)
{
    /* The VESC runs its own thermal throttling (Motor Settings →
     * Temperature).  The BTS7960 API hook exists for source-compat;
     * here it degrades to a normal disarm + safe zero. */
    (void)pulse_us;
    biba_bldc_set_enabled(false);
    biba_bldc_drive(0.0f, 0.0f);
}

void biba_bldc_clear_errors(void)
{
    /* No equivalent in the VESC CAN command set: faults latch only as
     * long as their cause is present and clear themselves once the
     * controller is happy again.  Kept as a no-op so the mode code can
     * call it unconditionally on the arm edge. */
}

/* ---- TX drain --------------------------------------------------------- */

static bool flush_tx_queue(void)
{
    biba_can_frame_t f;
    bool submitted = false;
    while (biba_can_queue_tx_pop(&f)) {
        if (biba_mcp2515_tx(&f)) {
            s_tx_count++;
            submitted = true;
        }
    }
    return submitted;
}

static void send_setpoint_rate_limited(uint8_t node_id, float cmd,
                                       uint32_t now_ms)
{
    uint32_t *last_ms = (node_id == BIBA_BLDC_LEFT_NODE_ID)
                          ? &s_last_setpoint_ms_left
                          : &s_last_setpoint_ms_right;
    const uint32_t min_period_ms = 1000u / BIBA_VESC_SETPOINT_RATE_HZ;
    if ((now_ms - *last_ms) < min_period_ms) {
        return;
    }
    *last_ms = now_ms;
    send_setpoint(node_id, cmd);
}

/* ---- RX decoding ------------------------------------------------------ */

static node_state_t *node_for(const biba_can_frame_t *f)
{
    uint8_t node_id = (uint8_t)(f->id & 0xFFu);
    if (node_id >= MAX_VESC_NODES) {
        return NULL;
    }
    return &s_nodes[node_id];
}

static void mark_alive(node_state_t *n, uint32_t now_ms)
{
    n->valid          = true;
    n->last_status_ms = now_ms;
}

static void decode_status(const biba_can_frame_t *f, uint32_t now_ms)
{
    if (f->dlc < 8u) return;
    node_state_t *n = node_for(f);
    if (n == NULL) return;

    /* i32 ERPM, i16 motor current ×10, i16 duty ×1000. */
    n->last_erpm      = (float)unpack_i32_be(&f->data[0]);
    n->last_current_a = (float)unpack_i16_be(&f->data[4]) / 10.0f;
    n->last_duty      = (float)unpack_i16_be(&f->data[6]) / 1000.0f;
    mark_alive(n, now_ms);
}

static void decode_status_4(const biba_can_frame_t *f, uint32_t now_ms)
{
    if (f->dlc < 8u) return;
    node_state_t *n = node_for(f);
    if (n == NULL) return;

    /* i16 temp_fet ×10, i16 temp_motor ×10, i16 current_in ×10,
     * i16 pid_pos ×50 (unused here). */
    n->last_fet_temp_c   = (int16_t)(unpack_i16_be(&f->data[0]) / 10);
    n->last_motor_temp_c = (int16_t)(unpack_i16_be(&f->data[2]) / 10);
    n->last_in_current   = (float)unpack_i16_be(&f->data[4]) / 10.0f;
    mark_alive(n, now_ms);
}

static void decode_status_5(const biba_can_frame_t *f, uint32_t now_ms)
{
    if (f->dlc < 6u) return;
    node_state_t *n = node_for(f);
    if (n == NULL) return;

    /* i32 tachometer (unused here), i16 input voltage ×10. */
    n->last_in_voltage = (float)unpack_i16_be(&f->data[4]) / 10.0f;
    mark_alive(n, now_ms);
}

void biba_bldc_drain_rx(void)
{
    biba_can_frame_t f;
    while (biba_mcp2515_rx_pop(&f)) {
        (void)biba_can_queue_rx_push(&f);
    }
    uint32_t now = biba_hal_now_ms();
    while (biba_can_queue_rx_pop(&f)) {
        s_rx_count++;

        /* RP2040_BLDC_VESC runs the MCP2515 in accept-all mode, so
         * anything on the bus lands here — including 11-bit frames
         * from a stray device.  Only 29-bit VESC frames are ours. */
        if (!f.ext) {
            s_decode_errors++;
            continue;
        }

        node_state_t *n;
        uint8_t packet_id = (uint8_t)((f.id >> 8u) & 0xFFu);
        switch (packet_id) {
        case VESC_PKT_STATUS:
            decode_status(&f, now);
            break;
        case VESC_PKT_STATUS_4:
            decode_status_4(&f, now);
            break;
        case VESC_PKT_STATUS_5:
            decode_status_5(&f, now);
            break;
        case VESC_PKT_PONG:
            /* A PONG proves the node is on the bus even before its
             * status broadcasts are enabled — useful during bring-up. */
            n = node_for(&f);
            if (n != NULL) {
                mark_alive(n, now);
            }
            break;
        case VESC_PKT_STATUS_2:
        case VESC_PKT_STATUS_3:
            /* Amp-hour / watt-hour counters: valid frames we simply do
             * not consume.  Still evidence the node is alive. */
            n = node_for(&f);
            if (n != NULL) {
                mark_alive(n, now);
            }
            break;
        default:
            /* Other VESC traffic (buffer transfers between the two
             * halves of a dual FSESC, VESC Tool over CAN, …).  Not an
             * error on a shared bus, but counted so a mis-set baud
             * rate shows up as a flood here. */
            s_decode_errors++;
            break;
        }
    }
}

/* ---- Tick ------------------------------------------------------------- */

void biba_bldc_tick_50hz(void)
{
    uint32_t now = biba_hal_now_ms();

    /* Always drain incoming frames before acting on anything else. */
    biba_bldc_drain_rx();

    if (!biba_mcp2515_ready()) {
        return;
    }

    /* Auto-recover the MCP2515 from a bus-off wedge (CAN errors from
     * bad termination / motor noise).  Checked at 10 Hz to keep SPI
     * traffic low; recovery resets + reprograms the chip in place. */
    static uint32_t s_bus_off_check_ms;
    if ((now - s_bus_off_check_ms) >= 100u) {
        s_bus_off_check_ms = now;
        if (biba_mcp2515_recover()) {
            for (unsigned i = 0; i < MAX_VESC_NODES; ++i) {
                s_nodes[i].valid = false;
            }
        }
    }

    /* Drive commands, rate-limited per node.  While disarmed we keep
     * sending zero rather than going silent: an explicit zero stops
     * the wheel now instead of after the VESC's own 1 s timeout. */
    const float left  = s_enabled ? s_setpoint_left  : 0.0f;
    const float right = s_enabled ? s_setpoint_right : 0.0f;

    send_setpoint_rate_limited(BIBA_BLDC_LEFT_NODE_ID,
                               left  * BIBA_VESC_LEFT_DIR,  now);
    send_setpoint_rate_limited(BIBA_BLDC_RIGHT_NODE_ID,
                               right * BIBA_VESC_RIGHT_DIR, now);

    /* There is no telemetry poll to issue: the VESC broadcasts its
     * STATUS frames on its own schedule once "CAN status message
     * mode" is enabled (see vesc_can.h).  If it is off, node_alive()
     * stays false and the fail-safe keeps the robot disarmed. */

    flush_tx_queue();
}

bool biba_bldc_node_alive(uint8_t node_id)
{
    if (node_id >= MAX_VESC_NODES)  return false;
    if (!s_nodes[node_id].valid)    return false;
    uint32_t now = biba_hal_now_ms();
    return (now - s_nodes[node_id].last_status_ms) <
            BIBA_VESC_STATUS_TIMEOUT_MS;
}

/* ---- Counters ---------------------------------------------------------- */

uint32_t biba_bldc_tx_count(void)       { return s_tx_count; }
uint32_t biba_bldc_rx_count(void)       { return s_rx_count; }
uint32_t biba_bldc_decode_errors(void)  { return s_decode_errors; }
uint32_t biba_bldc_recovery_count(void) { return biba_mcp2515_recovery_count(); }

uint32_t biba_bldc_reset_count(void)
{
    /* ODrive-only concept (its CANSimple stack can wedge and needs a
     * remote reboot).  No VESC equivalent — reported as zero so the
     * shared telemetry line keeps its shape. */
    return 0u;
}

/* ---- Telemetry getters -------------------------------------------------- */

float biba_bldc_bus_voltage(void)
{
    /* Both halves of a dual FSESC share the same pack; report the left
     * node and fall back to the right one if it has not reported yet. */
    if (s_nodes[BIBA_BLDC_LEFT_NODE_ID].valid) {
        return s_nodes[BIBA_BLDC_LEFT_NODE_ID].last_in_voltage;
    }
    return s_nodes[BIBA_BLDC_RIGHT_NODE_ID].last_in_voltage;
}

float biba_bldc_iq_measured(uint8_t node_id)
{
    if (node_id >= MAX_VESC_NODES) return 0.0f;
    return s_nodes[node_id].last_current_a;
}
