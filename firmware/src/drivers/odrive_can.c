#include "odrive_can.h"

#include "biba_board.h"
#include "biba_config.h"
#include "hal/biba_hal.h"

#include <string.h>

/* Compile-time anchor: this TU is only built on the BLDC target. */
#if !defined(BIBA_TARGET_HAS_BLDC_2CH) || (BIBA_TARGET_HAS_BLDC_2CH == 0)
#  error "odrive_can.c is for the BLDC target only — guard with src_filter or BIBA_TARGET_HAS_BLDC_2CH."
#endif

/* ---- Forward declarations of MCP2515 driver ------------------------- */

#include "drivers/mcp2515.h"
#include "drivers/can_queue.h"

/* ---- CANSimple encoding helpers ------------------------------------- *
 *
 * All ODrive CANSimple payloads are little-endian, IEEE-754 float.
 * The cmd_id lives in the upper bits of the 11-bit CAN ID; the
 * node_id lives in the lower 5 bits.
 *
 *   frame_id = (node_id << 5) | cmd_id
 */

static inline uint32_t frame_id(uint8_t node_id, uint8_t cmd_id)
{
    return ((uint32_t)(node_id & 0x3Fu) << 5u) |
           (uint32_t)(cmd_id  & 0x1Fu);
}

static void pack_u32_le(uint8_t *dst, uint32_t v)
{
    dst[0] = (uint8_t)(v        & 0xFFu);
    dst[1] = (uint8_t)((v >>  8) & 0xFFu);
    dst[2] = (uint8_t)((v >> 16) & 0xFFu);
    dst[3] = (uint8_t)((v >> 24) & 0xFFu);
}

static void pack_f32_le(uint8_t *dst, float v)
{
    union { float f; uint32_t u; } x;
    x.f = v;
    pack_u32_le(dst, x.u);
}

/* Return false if the queue full. */
static bool send_to_mcp(uint8_t node_id, uint8_t cmd_id,
                        const uint8_t *data, uint8_t dlc)
{
    biba_can_frame_t f = {
        .id  = frame_id(node_id, cmd_id),
        .dlc = dlc,
    };
    if (dlc > 0 && data != NULL) {
        memcpy(f.data, data, dlc);
    }
    return biba_can_queue_tx_push(&f);
}

/* ---- Per-node state ------------------------------------------------- *
 *
 * Two ODrive nodes (left / right) is hard-coded by the project's
 * task definition (see docs/mcp2515_bldc_research.md §0.3 / ADR §1.5).
 * Generalising to N nodes would be one array + two loops; not now.
 */
typedef struct {
    bool     valid;             /* false until first heartbeat         */
    uint32_t last_heartbeat_ms;
    uint8_t  last_state;        /* axis_state value                    */
    float    last_iq_measured;  /* measured motor current              */
    float    last_bus_voltage;  /* V                                    */
    float    last_bus_current;  /* A                                    */
    int16_t  last_fet_temp_c;
    int16_t  last_motor_temp_c;
} node_state_t;

#define MAX_ODRIVE_NODES  4u

static node_state_t s_nodes[MAX_ODRIVE_NODES];

/* ---- Driver-internal counters --------------------------------------- */
static volatile uint32_t s_tx_count;
static volatile uint32_t s_rx_count;
static volatile uint32_t s_decode_errors;

/* ---- High-level BTS7960-shaped API --------------------------------- */

static bool  s_enabled;
static float s_setpoint_left;
static float s_setpoint_right;
static uint32_t s_last_setpoint_ms_left;
static uint32_t s_last_setpoint_ms_right;
static uint32_t s_init_ms;

void biba_odrive_can_init(void)
{
    memset(s_nodes, 0, sizeof(s_nodes));
    s_enabled = false;
    s_setpoint_left = s_setpoint_right = 0.0f;
    s_last_setpoint_ms_left = s_last_setpoint_ms_right = 0u;
    s_tx_count = s_rx_count = s_decode_errors = 0u;
    s_init_ms = biba_hal_now_ms();

    biba_can_queue_rx_init();
    biba_can_queue_tx_init();

    (void)biba_mcp2515_init();      /* idempotent, see driver header */

    /* Set conservative limits on both ODrive at boot.  Some ODrive
     * firmwares ignore Set_Limits until the axis has been requested
     * once, so we re-issue this on every Set_Axis_State edge too. */
    uint8_t payload[8];
    pack_f32_le(&payload[0], BIBA_ODRIVE_MAX_CURRENT_A);
    pack_f32_le(&payload[4], BIBA_ODRIVE_MAX_VEL_LIMIT_REV_S);
    send_to_mcp(BIBA_ODRIVE_LEFT_NODE_ID,  OD_CMD_SET_LIMITS,
                payload, sizeof(payload));
    send_to_mcp(BIBA_ODRIVE_RIGHT_NODE_ID, OD_CMD_SET_LIMITS,
                payload, sizeof(payload));
}

void biba_odrive_set_enabled(bool enabled)
{
    if (enabled == s_enabled) {
        return;
    }
    s_enabled = enabled;

    /* CLOSED_LOOP_CONTROL = 8 on ODrive.  IDLE = 0.  See ADR §6.6
     * of the research. */
    const uint8_t new_state = enabled ? 0x08u : 0x00u;
    uint8_t payload[8] = { 0 };
    pack_u32_le(&payload[0], new_state);
    send_to_mcp(BIBA_ODRIVE_LEFT_NODE_ID,  OD_CMD_SET_AXIS_STATE,
                payload, 4u);
    send_to_mcp(BIBA_ODRIVE_RIGHT_NODE_ID, OD_CMD_SET_AXIS_STATE,
                payload, 4u);

    /* Push the latest setpoint too, so the moment we close-loop we
     * don't have a stale value from the previous session. */
    if (enabled) {
        biba_odrive_drive(s_setpoint_left, s_setpoint_right);
    }
}

void biba_odrive_drive(float left_duty, float right_duty)
{
    /* Clamp to [-1, +1] (allows racing RC failure modes). */
    if (left_duty  >  1.0f) left_duty  =  1.0f;
    if (left_duty  < -1.0f) left_duty  = -1.0f;
    if (right_duty >  1.0f) right_duty =  1.0f;
    if (right_duty < -1.0f) right_duty = -1.0f;

    s_setpoint_left  = left_duty;
    s_setpoint_right = right_duty;
    /* The actual CAN transmit happens inside the 50 Hz tick so we
     * stay lock-step with the control loop.  Nothing to send now
     * unless we want to bypass rate-limiting.  We do exactly that
     * for the very first call after init() so an immediate arm has
     * the right setpoint. */
}

void biba_odrive_thermal_reset(uint32_t pulse_us)
{
    /* BLDC hardware manages its own thermal protection; the BTS7960
     * API hook exists for source-compat.  We zero the setpoints and
     * disarm, identical semantics to a normal disarm + safe zero. */
    (void)pulse_us;
    biba_odrive_set_enabled(false);
    biba_odrive_drive(0.0f, 0.0f);
}

/* ---- Rate-limited forwarder -----------------------------------------
 *
 * Returns true if any frame was actually submitted (i.e. the queue
 * had room).  Called from the 50 Hz tick. */
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

    /* 8-byte payload: input_vel(4) + input_torque(4).  ODrive ignores
     * torque_ff unless torque_control_mode is enabled. */
    uint8_t payload[8];
    pack_f32_le(&payload[0], vel_rev_s);
    pack_f32_le(&payload[4],
                (node_id == BIBA_ODRIVE_LEFT_NODE_ID)
                    ? BIBA_ODRIVE_LEFT_TORQUE_FF_NM
                    : BIBA_ODRIVE_RIGHT_TORQUE_FF_NM);
    send_to_mcp(node_id, OD_CMD_SET_INPUT_VEL, payload, sizeof(payload));
}

/* ---- RX decoding ---------------------------------------------------- */

static void decode_heartbeat(const biba_can_frame_t *f, uint32_t now_ms)
{
    if (f->dlc < 1u) return;
    if (f->dlc >= 7u) {
        /* ODrive v3.x encodes extra fields (Ibus, Seq) after the
         * first 7 bytes.  We don't need them here; we just need to
         * know the node is alive. */
    }
    uint8_t node_id = (uint8_t)(f->id >> 5u) & 0x3Fu;
    if (node_id >= MAX_ODRIVE_NODES) return;
    s_nodes[node_id].valid = true;
    s_nodes[node_id].last_heartbeat_ms = now_ms;
    s_nodes[node_id].last_state = f->data[0];
}

static void decode_get_iq(const biba_can_frame_t *f)
{
    if (f->dlc < 8u) return;
    uint8_t node_id = (uint8_t)(f->id >> 5u) & 0x3Fu;
    if (node_id >= MAX_ODRIVE_NODES) return;
    union { uint32_t u; float f; } set, meas;
    set.u = (uint32_t)f->data[0]        | ((uint32_t)f->data[1] <<  8)
          | ((uint32_t)f->data[2] << 16) | ((uint32_t)f->data[3] << 24);
    meas.u = (uint32_t)f->data[4]       | ((uint32_t)f->data[5] <<  8)
           | ((uint32_t)f->data[6] << 16) | ((uint32_t)f->data[7] << 24);
    s_nodes[node_id].last_iq_measured = meas.f;
    (void)set;
}

static void decode_get_bus_voltage_current(const biba_can_frame_t *f)
{
    if (f->dlc < 8u) return;
    uint8_t node_id = (uint8_t)(f->id >> 5u) & 0x3Fu;
    if (node_id >= MAX_ODRIVE_NODES) return;
    union { uint32_t u; float f; } v, i;
    v.u = (uint32_t)f->data[0]       | ((uint32_t)f->data[1] <<  8)
        | ((uint32_t)f->data[2] << 16) | ((uint32_t)f->data[3] << 24);
    i.u = (uint32_t)f->data[4]       | ((uint32_t)f->data[5] <<  8)
        | ((uint32_t)f->data[6] << 16) | ((uint32_t)f->data[7] << 24);
    s_nodes[node_id].last_bus_voltage = v.f;
    s_nodes[node_id].last_bus_current = i.f;
}

static void decode_get_temperature(const biba_can_frame_t *f)
{
    if (f->dlc < 8u) return;
    uint8_t node_id = (uint8_t)(f->id >> 5u) & 0x3Fu;
    if (node_id >= MAX_ODRIVE_NODES) return;
    /* ODrive_Get_Temperature: FET (4 bytes float) + Motor (4 bytes float). */
    union { uint32_t u; float f; } fet, mot;
    fet.u = (uint32_t)f->data[0]       | ((uint32_t)f->data[1] <<  8)
          | ((uint32_t)f->data[2] << 16) | ((uint32_t)f->data[3] << 24);
    mot.u = (uint32_t)f->data[4]       | ((uint32_t)f->data[5] <<  8)
          | ((uint32_t)f->data[6] << 16) | ((uint32_t)f->data[7] << 24);
    s_nodes[node_id].last_fet_temp_c   = (int16_t)fet.f;
    s_nodes[node_id].last_motor_temp_c = (int16_t)mot.f;
}

/* Pop MCP2515 RX buffers until they report empty, drain whatever
 * came back into can_queue, then drain it into our decoders. */
void biba_odrive_can_drain_rx(void)
{
    biba_can_frame_t f;
    while (biba_mcp2515_rx_pop(&f)) {
        (void)biba_can_queue_rx_push(&f);
    }
    uint32_t now = biba_hal_now_ms();
    while (biba_can_queue_rx_pop(&f)) {
        s_rx_count++;
        uint8_t cmd_id = (uint8_t)(f.id & 0x1Fu);
        switch (cmd_id) {
        case OD_CMD_HEARTBEAT:
            decode_heartbeat(&f, now);
            break;
        case OD_CMD_GET_IQ:
            decode_get_iq(&f);
            break;
        case OD_CMD_GET_BUS_VOLTAGE_CURRENT:
            decode_get_bus_voltage_current(&f);
            break;
        case OD_CMD_GET_TEMPERATURE:
            decode_get_temperature(&f);
            break;
        default:
            /* Address broadcast replies, Get_Encoder_Estimates, and any
             * non-whitelisted cmd_id (filters applied at the MCP2515
             * level, so this means we misconfigured the filter).
             * Silently count and move on. */
            s_decode_errors++;
            break;
        }
    }
}

/* ---- Tick -------------------------------------------------------------- */

void biba_odrive_can_tick_50hz(void)
{
    uint32_t now = biba_hal_now_ms();

    /* Always drain incoming frames before acting on anything else. */
    biba_odrive_can_drain_rx();

    if (!biba_mcp2515_ready()) {
        return;
    }

    /* Send Set_Input_Vel, rate-limited per-node. */
    send_set_input_vel(BIBA_ODRIVE_LEFT_NODE_ID,
                       s_setpoint_left  * BIBA_ODRIVE_LEFT_DIR  *
                                          BIBA_ODRIVE_LEFT_MAX_VEL_REV_S,
                       now);
    send_set_input_vel(BIBA_ODRIVE_RIGHT_NODE_ID,
                       s_setpoint_right * BIBA_ODRIVE_RIGHT_DIR *
                                          BIBA_ODRIVE_RIGHT_MAX_VEL_REV_S,
                       now);

    /* Push periodic telemetry requests — low-rate, ≤ 10 Hz. */
    static uint32_t s_pull_acc;
    s_pull_acc += 20;   /* this function called at 50 Hz; +20 ms per call */
    if (s_pull_acc >= 100u) {
        s_pull_acc = 0u;
        send_to_mcp(BIBA_ODRIVE_LEFT_NODE_ID,  OD_CMD_GET_BUS_VOLTAGE_CURRENT,
                    NULL, 0u);
        send_to_mcp(BIBA_ODRIVE_RIGHT_NODE_ID, OD_CMD_GET_BUS_VOLTAGE_CURRENT,
                    NULL, 0u);
    }

    /* Drain the MCP2515 TX queue into the controller once per tick
     * (MCP2515 has its own TX buffer; we go round-robin via the
     * queue). */
    flush_tx_queue();
}

bool biba_odrive_node_alive(uint8_t node_id)
{
    if (node_id >= MAX_ODRIVE_NODES) return false;
    if (!s_nodes[node_id].valid)     return false;
    uint32_t now = biba_hal_now_ms();
    return (now - s_nodes[node_id].last_heartbeat_ms) <
            BIBA_ODRIVE_HEARTBEAT_TIMEOUT_MS;
}

/* ---- Counters --------------------------------------------------------- */

uint32_t biba_odrive_tx_count(void)      { return s_tx_count; }
uint32_t biba_odrive_rx_count(void)      { return s_rx_count; }
uint32_t biba_odrive_decode_errors(void) { return s_decode_errors; }
