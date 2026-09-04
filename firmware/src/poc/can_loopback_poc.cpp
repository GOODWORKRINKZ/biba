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
#include "hardware/spi.h"
#include "hardware/gpio.h"

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

/* Raw MCP2515 register read (READ 0x03) — 3-byte full-duplex. */
static uint8_t raw_reg(uint8_t addr)
{
    uint8_t tx[3] = { 0x03u, addr, 0x00u };
    uint8_t rx[3];
    gpio_put(BIBA_PIN_SPI0_CS_GPIO, 0);
    spi_write_read_blocking(BIBA_MCP2515_SPI_INST, tx, rx, 3);
    gpio_put(BIBA_PIN_SPI0_CS_GPIO, 1);
    return rx[2];
}

/* MCP2515 READ STATUS (0xA0) — one instruction byte + one status byte. */
static uint8_t raw_status(void)
{
    uint8_t tx[2] = { 0xA0u, 0x00u };
    uint8_t rx[2];
    gpio_put(BIBA_PIN_SPI0_CS_GPIO, 0);
    spi_write_read_blocking(BIBA_MCP2515_SPI_INST, tx, rx, 2);
    gpio_put(BIBA_PIN_SPI0_CS_GPIO, 1);
    return rx[1];
}

/* Dump the MCP2515 register bank over SPI for diagnostics. */
static void dump_regs(void)
{
    struct { uint8_t a; const char *n; } regs[] = {
        {0x0E, "CANSTAT "}, {0x0F, "CANCTRL "}, {0x2A, "CNF1    "},
        {0x29, "CNF2    "}, {0x28, "CNF3    "}, {0x2B, "CANINTE "},
        {0x2C, "CANINTF "}, {0x2D, "EFLG    "}, {0x1C, "TEC     "},
        {0x1D, "REC     "}, {0x30, "TXB0CTRL"}, {0x31, "TXB0SIDH"},
        {0x32, "TXB0SIDL"}, {0x35, "TXB0DLC "}, {0x36, "TXB0D0  "},
        {0x40, "TXB1CTRL"}, {0x50, "TXB2CTRL"}, {0x60, "RXB0CTRL"},
        {0x70, "RXB1CTRL"}, {0x20, "RXM0SIDH"}, {0x21, "RXM0SIDL"},
    };
    printf("[biba] --- MCP2515 register dump ---\r\n");
    for (unsigned i = 0; i < sizeof(regs)/sizeof(regs[0]); ++i) {
        printf("[biba] %s (0x%02X) = 0x%02X\r\n",
               regs[i].n, regs[i].a, raw_reg(regs[i].a));
    }
    printf("[biba] READ_STATUS (0xA0) = 0x%02X\r\n", raw_status());
}

/* Raw BIT MODIFY (0x05): [instr][addr][mask][value]. */
static void raw_modify(uint8_t addr, uint8_t mask, uint8_t value)
{
    uint8_t tx[4] = { 0x05u, addr, mask, value };
    uint8_t rx[4];
    gpio_put(BIBA_PIN_SPI0_CS_GPIO, 0);
    spi_write_read_blocking(BIBA_MCP2515_SPI_INST, tx, rx, 4);
    gpio_put(BIBA_PIN_SPI0_CS_GPIO, 1);
}

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

    /* Same USB-CDC fixes as main_rp2040.cpp: without ignoreFlowControl
     * SerialUSB::write() drops data until the host asserts DTR, and
     * newlib fully buffers stdout because the core's _isatty() = 0.
     * Without these, the "MCP2515 init FAILED" line is lost when the
     * host connects after boot. */
    Serial.ignoreFlowControl(true);
    setvbuf(stdout, NULL, _IONBF, 0);

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
        /* Raw SPI probe: read CANSTAT (READ 0x03, addr 0x0E) and dump
         * the bytes.  Interpretation:
         *   ~0x80 (CONFIG mode) → chip answers, driver logic bug
         *   0xFF → MISO floating high (SO wire off / chip unpowered)
         *   0x00 → MISO held low (short / SO wired to GND)
         *   stable other value → chip partially alive (mode/clock issue)
         * Re-print everything every second because the host may open
         * the CDC port only after boot. */
        uint8_t txb[3] = { 0x03u, 0x0Eu, 0x00u };   /* READ CANSTAT */
        uint8_t rxb[3];
        for (;;) {
            printf("[biba] MCP2515 init FAILED (status=%d) — PoC halts\r\n",
                   (int)st);
            gpio_put(BIBA_PIN_SPI0_CS_GPIO, 0);
            spi_write_read_blocking(BIBA_MCP2515_SPI_INST, txb, rxb, 3);
            gpio_put(BIBA_PIN_SPI0_CS_GPIO, 1);
            printf("[biba] raw CANSTAT: %02X %02X %02X\r\n",
                   rxb[0], rxb[1], rxb[2]);

            /* Instrumented reset: same sequence as mcp2515.c
             * reset_and_wait() but printing CANSTAT every 10 ms. */
            gpio_put(BIBA_PIN_SPI0_CS_GPIO, 0);
            uint8_t rst = 0xC0u;                    /* RESET */
            spi_write_blocking(BIBA_MCP2515_SPI_INST, &rst, 1);
            gpio_put(BIBA_PIN_SPI0_CS_GPIO, 1);
            delay(1);
            for (int i = 0; i < 10; ++i) {
                uint8_t tr[3] = { 0x03u, 0x0Eu, 0x00u };
                uint8_t rr[3];
                gpio_put(BIBA_PIN_SPI0_CS_GPIO, 0);
                spi_write_read_blocking(BIBA_MCP2515_SPI_INST, tr, rr, 3);
                gpio_put(BIBA_PIN_SPI0_CS_GPIO, 1);
                printf("[biba] t=%dms CANSTAT=%02X\r\n", 1 + i * 10, rr[2]);
                delay(10);
            }
        }
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
    static bool s_tx_pause;   /* stop periodic TX while switching modes */

    /* Drain whatever the bus returned (typically nothing without a
     * second ODrive, but a TX↔RX loopback jumper makes this print
     * the heartbeat we sent). */
    drain_rx();

    /* Console: 'L' = pause TX + abort + loopback (REQOP=0b010),
     * 'T' = send one frame now (loopback echo test), 'A' = abort TX,
     * 'N' = normal mode + resume periodic TX.  A pending TXREQ blocks
     * mode transitions, so abort + pause first. */
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == 'A') {
            raw_modify(0x30u, 0x08u, 0x00u);   /* TXB0CTRL: clear TXREQ */
            printf("[biba] TX aborted\r\n");
        } else if (c == 'L') {
            s_tx_pause = true;
            raw_modify(0x30u, 0x08u, 0x00u);   /* clear TXREQ first */
            raw_modify(0x0Fu, 0xE0u, 0x40u);   /* REQOP = loopback */
            printf("[biba] mode: LOOPBACK (TX paused)\r\n");
        } else if (c == 'T') {
            send_heartbeat_like(BIBA_ODRIVE_LEFT_NODE_ID, 0x08u);
            printf("[biba] manual TX sent\r\n");
        } else if (c == 'N') {
            raw_modify(0x30u, 0x08u, 0x00u);   /* clear TXREQ first */
            raw_modify(0x0Fu, 0xE0u, 0x00u);   /* REQOP = normal */
            s_tx_pause = false;
            printf("[biba] mode: NORMAL (TX resumed)\r\n");
        } else if (c == 'X') {
            /* RXM = 0b11 on both RX buffers: turn mask/filters OFF,
             * receive ANY message.  RXM lives in RXBxCTRL bits 6:5
             * (bit 7 is reserved) — so the mask is 0x60, not 0xC0. */
            raw_modify(0x60u, 0x60u, 0x60u);   /* RXB0CTRL: RXM=11 */
            raw_modify(0x70u, 0x60u, 0x60u);   /* RXB1CTRL: RXM=11 */
            printf("[biba] RX filters OFF (accept all)\r\n");
        } else if (c == 'Y') {
            /* Restore RXM = 0b00 (filters active, default). */
            raw_modify(0x60u, 0x60u, 0x00u);   /* RXB0CTRL: RXM=00 */
            raw_modify(0x70u, 0x60u, 0x00u);   /* RXB1CTRL: RXM=00 */
            printf("[biba] RX filters ON (default)\r\n");
        } else if (c == 'D') {
            dump_regs();
        }
    }

    uint32_t now = millis();

    if (!s_tx_pause && now - s_last_hb_ms >= 200u) {
        s_last_hb_ms = now;
        send_heartbeat_like(BIBA_ODRIVE_LEFT_NODE_ID, 0x08u);
    }

    if (!s_tx_pause && now - s_last_vel_ms >= 1000u) {
        s_last_vel_ms = now;
        /* Slow ramp up — at 1 rev/s the ODrive (if present) will
         * move, so this is a bench-friendly default. */
        send_set_input_vel(BIBA_ODRIVE_LEFT_NODE_ID,
                           1.0f /* vel_rev_s */,
                           0.0f /* torque_ff_nm */);
    }

    if (now - s_last_status_ms >= 1000u) {
        s_last_status_ms = now;
        /* MCP2515 CAN-side health: TEC/REC error counters, EFLG error
         * flags, TXB0CTRL (TXREQ=0x08 stuck = frame not ACKed). */
        uint8_t tec   = raw_reg(0x1Cu);
        uint8_t rec   = raw_reg(0x1Du);
        uint8_t eflg  = raw_reg(0x2Du);
        uint8_t txb0  = raw_reg(0x30u);
        uint8_t cstat = raw_reg(0x0Eu);   /* CANSTAT: OPMOD[7:5] */
        uint8_t cctrl = raw_reg(0x0Fu);   /* CANCTRL: REQOP[7:5] */
        uint8_t intf  = raw_reg(0x2Cu);   /* CANINTF interrupt flags */
        uint8_t gp15  = gpio_get(BIBA_PIN_MCP2515_INT_GPIO) ? 1u : 0u;
        printf("[biba] status t=%lu tx=%lu rx=%lu rx_drop=%lu "
               "q_rx_push=%lu q_rx_pop=%lu q_tx_push=%lu q_tx_pop=%lu "
               "od_tx=%lu od_rx=%lu decode_err=%lu "
               "tec=%u rec=%u eflg=0x%02X txb0=0x%02X "
               "canstat=0x%02X canctrl=0x%02X intf=0x%02X gp15=%u\r\n",
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
               (unsigned long)biba_odrive_decode_errors(),
               tec, rec, eflg, txb0, cstat, cctrl, intf, gp15);
    }

    /* No delay() — we want a tight loop so the RX ISR (when wired)
     * sees its queue drained promptly. */
}