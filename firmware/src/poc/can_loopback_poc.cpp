/* CAN-loopback PoC for the RPICO_RP2040_BLDC target.
 *
 * This is a minimal self-test that exercises the full MCP2515 +
 * ODrive driver stack without requiring a second ODrive on the bus.
 *
 * Behaviour:
 *   1. Bring up the MCP2515 (SPI0, 250 kbps, ODrive CANSimple filter
 *      set per ADR-0001 §1.3).
 *   2. Send a canned Heartbeat-shaped frame every 200 ms:
 *         frame_id = (0x3F << 5) | 0x01   = 0x7E1
 *         dlc      = 1
 *         data[0]  = 0x08   (ODrive CLOSED_LOOP_CONTROL)
 *      This pretends to be an ODrive-side Heartbeat broadcast; on a
 *      real bus ODrive itself sends this frame and we'd see it via
 *      RX.  Sending it from the host is harmless — the receiving
 *      decoder (decode_heartbeat()) just records node 0x3F as alive
 *      which we don't watch.
 *   3. Send a Set_Input_Vel (cmd_id 0x0D) once a second — the same
 *      shape that biba_odrive_drive() would emit, but with a fixed
 *      1.0 rev/s velocity so the loopback log is deterministic.
 *   4. Drain RX frames and print each one over USB CDC.
 *   5. Print a 1 Hz status line with TX/RX counters.
 *
 * Without a wire between CANH/CANL (and a second ODrive or a CAN
 * analyser), no RX frames will arrive — that's expected.  This PoC
 * still validates that the SPI bus, MCP2515 init, configuration
 * registers, filters, TX path, and the ring-queue bridge all work
 * end-to-end.
 *
 * With a second ODrive on the bus (or a TX↔RX jumper on the TJA1050
 * module), this PoC also validates the RX path because every
 * Heartbeat frame the ODrive emits will be printed.
 *
 * Wired into the existing PoC build via `[rp2040_bldc_poc_src_filter]`
 * (see platformio.ini) and through the BIBA_IS_POC=1 compile gate.
 */

#include <Arduino.h>

extern "C" {
#include "biba_board.h"
#include "biba_config.h"
#include "drivers/mcp2515.h"
#include "drivers/odrive_can.h"
#include "drivers/can_queue.h"
#include "hal/biba_hal.h"

#include <stdio.h>
#include <stdint.h>
#include <string.h>
}

/* The PoC build (rp2040_bldc_poc_src_filter) does not pull in
 * biba_hal_rp2040.c — odrive_can.c references biba_hal_now_ms() so
 * we forward-declare an Arduino-backed implementation here.  This
 * keeps the PoC self-contained and avoids the heavy bring-up
 * sequence in biba_hal_init(). */
extern "C" uint32_t biba_hal_now_ms(void) { return millis(); }
extern "C" void     biba_hal_delay_ms(uint32_t ms) { delay(ms); }
extern "C" void     biba_hal_delay_us(uint32_t us) { delayMicroseconds(us); }

/* Frame id helpers (same as odrive_can.c internal layout). */
static inline uint32_t can_id(uint8_t node_id, uint8_t cmd_id)
{
    return ((uint32_t)(node_id & 0x3Fu) << 5u) |
           (uint32_t)(cmd_id  & 0x1Fu);
}

static void pack_f32_le(uint8_t *dst, float v)
{
    union { float f; uint32_t u; } x;
    x.f = v;
    dst[0] = (uint8_t)(x.u        & 0xFFu);
    dst[1] = (uint8_t)((x.u >>  8) & 0xFFu);
    dst[2] = (uint8_t)((x.u >> 16) & 0xFFu);
    dst[3] = (uint8_t)((x.u >> 24) & 0xFFu);
}

static void send_set_input_vel(uint8_t node_id, float vel_rev_s,
                               float torque_ff_nm)
{
    uint8_t payload[8];
    pack_f32_le(&payload[0], vel_rev_s);
    pack_f32_le(&payload[4], torque_ff_nm);
    biba_can_frame_t f = {
        .id  = can_id(node_id, OD_CMD_SET_INPUT_VEL),
        .dlc = 8,
    };
    memcpy(f.data, payload, sizeof(payload));
    (void)biba_mcp2515_tx(&f);
}

static void send_heartbeat_like(uint8_t node_id, uint8_t state)
{
    /* Stand-in for an ODrive Heartbeat (cmd_id 0x01).  The decoder in
     * odrive_can.c only reads data[0] and treats it as the axis
     * state; everything else is ignored. */
    biba_can_frame_t f = {
        .id  = can_id(node_id, OD_CMD_HEARTBEAT),
        .dlc = 1,
    };
    f.data[0] = state;
    (void)biba_mcp2515_tx(&f);
}

static void print_can_frame(const char *prefix, const biba_can_frame_t *f)
{
    char hex[32];
    int n = 0;
    for (unsigned i = 0; i < f->dlc && i < 8u; ++i) {
        n += snprintf(hex + n, sizeof(hex) - (size_t)n,
                      " %02X", f->data[i]);
    }
    printf("[can] %s id=0x%03lX dlc=%u data=%s\r\n",
           prefix,
           (unsigned long)f->id, (unsigned)f->dlc, hex);
}

static void drain_rx(void)
{
    biba_can_frame_t f;
    while (biba_mcp2515_rx_pop(&f)) {
        print_can_frame("RX", &f);
    }
}

void setup()
{
    Serial.begin(115200);

    /* Tiny grace period so the USB-CDC port can enumerate on the
     * host.  300 ms is plenty for a Linux box and short enough that
     * the bring-up log is still useful on a bench. */
    delay(300);

    printf("\r\n[biba] RPICO_RP2040_BLDC CAN-loopback PoC\r\n");
    printf("[biba] build: " __DATE__ " " __TIME__ "\r\n");
    printf("[biba] target: %s @ %lu MHz, MCP2515 SPI @ %lu Hz\r\n",
           BIBA_TARGET_NAME,
           (unsigned long)(BIBA_SYS_CLOCK_HZ / 1000000u),
           (unsigned long)BIBA_MCP2515_SPI_BAUD_HZ);

    biba_mcp2515_status_t st = biba_mcp2515_init();
    if (st != BIBA_MCP2515_OK) {
        printf("[biba] MCP2515 init FAILED (status=%d) — PoC halts\r\n",
               (int)st);
        for (;;) { tight_loop_contents(); }
    }
    printf("[biba] MCP2515 up @ %lu bps\r\n",
           (unsigned long)biba_mcp2515_bitrate_bps());

    /* Seed the queues so we can call into the ODrive protocol layer
     * (which drains RX via can_queue). */
    biba_can_queue_rx_init();
    biba_can_queue_tx_init();

    /* Boot-time Set_Limits so a real ODrive applies our safe envelope
     * the moment it sees us on the bus. */
    biba_odrive_can_init();

    /* One initial broadcast heartbeat so a logic analyser / ODrive
     * can immediately tell "host alive". */
    send_heartbeat_like(BIBA_ODRIVE_LEFT_NODE_ID, 0x00u);

    printf("[biba] PoC running: TX Heartbeat @ 5 Hz, Set_Input_Vel @ 1 Hz\r\n");
}

void loop()
{
    static uint32_t s_last_hb_ms;
    static uint32_t s_last_vel_ms;
    static uint32_t s_last_status_ms;

    /* Drain whatever the bus returned (typically nothing without a
     * second ODrive, but a TX↔RX loopback jumper makes this print
     * the heartbeat we sent). */
    drain_rx();

    uint32_t now = millis();

    if (now - s_last_hb_ms >= 200u) {
        s_last_hb_ms = now;
        send_heartbeat_like(BIBA_ODRIVE_LEFT_NODE_ID, 0x08u);
    }

    if (now - s_last_vel_ms >= 1000u) {
        s_last_vel_ms = now;
        /* Slow ramp up — at 1 rev/s the ODrive (if present) will
         * move, so this is a bench-friendly default. */
        send_set_input_vel(BIBA_ODRIVE_LEFT_NODE_ID,
                           1.0f /* vel_rev_s */,
                           0.0f /* torque_ff_nm */);
    }

    if (now - s_last_status_ms >= 1000u) {
        s_last_status_ms = now;
        printf("[biba] status t=%lu tx=%lu rx=%lu rx_drop=%lu "
               "q_rx_push=%lu q_rx_pop=%lu q_tx_push=%lu q_tx_pop=%lu "
               "od_tx=%lu od_rx=%lu decode_err=%lu\r\n",
               (unsigned long)now,
               (unsigned long)biba_mcp2515_tx_count(),
               (unsigned long)biba_mcp2515_rx_count(),
               (unsigned long)biba_mcp2515_rx_drop_count(),
               (unsigned long)biba_can_queue_rx_push_count(),
               (unsigned long)biba_can_queue_rx_pop_count(),
               (unsigned long)biba_can_queue_tx_push_count(),
               (unsigned long)biba_can_queue_tx_pop_count(),
               (unsigned long)biba_odrive_tx_count(),
               (unsigned long)biba_odrive_rx_count(),
               (unsigned long)biba_odrive_decode_errors());
    }

    /* No delay() — we want a tight loop so the RX ISR (when wired)
     * sees its queue drained promptly. */
}