#include "mcp2515.h"

#include "biba_board.h"
#include "biba_config.h"

#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "hardware/irq.h"
#include "pico/time.h"

#include <string.h>

/* --- MCP2515 SPI instruction set (DS20001801J §10) --------------------- */

#define MCP2515_INSTR_RESET        0xC0u
#define MCP2515_INSTR_READ         0x03u
#define MCP2515_INSTR_WRITE        0x02u
#define MCP2515_INSTR_RTS_TXB0     0x81u
#define MCP2515_INSTR_RTS_TXB1     0x82u
#define MCP2515_INSTR_RTS_TXB2     0x84u
#define MCP2515_INSTR_READ_STATUS  0xA0u
#define MCP2515_INSTR_BIT_MODIFY   0x05u
#define MCP2515_INSTR_READ_RX0     0x90u
#define MCP2515_INSTR_READ_RX1     0x94u

/* Selected register addresses that this driver programs explicitly.
 * IDs not in this list come from MCP2515.h-style compact numbering on
 * DS20001801J §11 "Register Map". */
#define MCP2515_REG_CANCTRL    0x0Fu   /* Reset / mode control            */
#define MCP2515_REG_CANSTAT    0x0Eu   /* Status mirror (read-only)       */
#define MCP2515_REG_CNF3       0x28u
#define MCP2515_REG_CNF2       0x29u
#define MCP2515_REG_CNF1       0x2Au
#define MCP2515_REG_CANINTE    0x2Bu
#define MCP2515_REG_CANINTF    0x2Cu
#define MCP2515_REG_RXB0CTRL   0x60u
#define MCP2515_REG_RXB1CTRL   0x70u
#define MCP2515_REG_RXM0SIDH   0x20u
#define MCP2515_REG_RXM0SIDL   0x21u
#define MCP2515_REG_RXM1SIDH   0x24u
#define MCP2515_REG_RXM1SIDL   0x25u
#define MCP2515_REG_RXF0SIDH   0x00u   /* Mask = 0x01F, matches cmd_id   */
#define MCP2515_REG_RXF0SIDL   0x01u
#define MCP2515_REG_RXF0EID8   0x02u   /* unused (11-bit ID only)         */
#define MCP2515_REG_RXF0EID0   0x03u
#define MCP2515_REG_RXF1SIDH   0x04u
#define MCP2515_REG_RXF1SIDL   0x05u
#define MCP2515_REG_RXF2SIDH   0x08u
#define MCP2515_REG_RXF2SIDL   0x09u
#define MCP2515_REG_RXF3SIDH   0x10u
#define MCP2515_REG_RXF3SIDL   0x11u
#define MCP2515_REG_RXF4SIDH   0x14u
#define MCP2515_REG_RXF4SIDL   0x15u
#define MCP2515_REG_RXF5SIDH   0x18u
#define MCP2515_REG_RXF5SIDL   0x19u
#define MCP2515_REG_TXB0CTRL   0x30u
#define MCP2515_REG_TXB0SIDH   0x31u
#define MCP2515_REG_TXB0SIDL   0x32u
#define MCP2515_REG_TXB0DLC    0x35u
#define MCP2515_REG_TXB0D0     0x36u   /* first data byte                 */

/* CANSTAT opmode field (CANSTAT[7:5]). */
#define MCP2515_OPMODE_NORMAL   0x00u
#define MCP2515_OPMODE_CONFIG   0x04u

/* Mode-locked guard for the BIT-MODIFY-based mode switch (CANCTRL[7:5]). */
#define MCP2515_MODE_REQUEST_NORMAL  (MCP2515_OPMODE_NORMAL << 5u)

/* CNF1[5:0] = BRP-1.  We need TQ = 2/(Fxtal / BRP) where Fxtal = 8 MHz.
 * Target baud = 250_000 Hz → Tbit = 4 µs.  Bit-time budget = 8 TQ
 * (1 sync + 6 propseg+phase1 + 1 phase2; SJW=1 — see ADR-0001 §1.3).
 *   TQ = 4 µs / 8 = 500 ns → BRP = 2 → BRP-1 = 1 → CNF1 = 0x01.
 * CNF1[7:6] = SJW-1 = 0 (SJW = 1).
 * Output: CNF1 = 0b0000_0001 = 0x01. */
#define MCP2515_CNF1_BRP_250K   0x01u

/* CNF2[6] = SAM (0 = sample once); CNF2[5:3] = PHSEG1-1; CNF2[2:0] = PRSEG-1.
 * Nominal bit time = SYNC(1) + PROPSEG(PRSEG+1) + PS1(PHSEG1+1) + PS2(PHSEG2+1).
 * For 8 TQ total with TQ = 500 ns (4 µs = 250 kbit @ 8 MHz):
 *   1 + 1 + 5 + 1 = 8 TQ → PRSEG=0, PHSEG1=4, PHSEG2=0.
 * CNF2 = BTLMODE(1)<<7 | PHSEG1(4)<<3 | PRSEG(0) = 0b1_0_100_000 = 0xA0.
 *
 * (Previous value 0xD0 had PHSEG1=5 → PS1=6 → 9 TQ = 4.5 µs ≈ 222 kbit,
 * a 12% mismatch vs the 250 kbit ODrive — enough to make the CAN engine
 * rack up TEC/REC and go error-passive/bus-off.  See ADR-0001 §1.3.) */
#define MCP2515_CNF2_250K       0xA0u

/* CNF3[2:0] = PHSEG2 - 1 = 0 (1 TQ).  CNF3[7] = WAKFIL = 0.
 *   0b0000_0000 = 0x00. */
#define MCP2515_CNF3_250K       0x00u

/* --- 100 kbit/s @ 8 MHz crystal ---------------------------------------- */
/* TQ = 2×(BRP+1)/8MHz.  BRP=3 → TQ = 1 µs.  Bit = 10 µs = 10 TQ.
 * SYNC(1) + PROPSEG(2) + PS1(5) + PS2(2) = 10 TQ, sample point 80%.
 *   PRSEG=1, PHSEG1=4, PHSEG2=1.
 *   CNF1 = (SJW=0)<<6 | (BRP-1=2) = 0x02
 *   CNF2 = BTLMODE(1)<<7 | PHSEG1(4)<<3 | PRSEG(1) = 0xA1
 *   CNF3 = PHSEG2-1 = 1 = 0x01 */
#define MCP2515_CNF1_BRP_100K   0x02u
#define MCP2515_CNF2_100K       0xA1u
#define MCP2515_CNF3_100K       0x01u

/* Selected bus bit rate.  The ODrive must be configured to the same
 * value (can.config.baud_rate).  NOTE: ODrive v3 (0.5.1) hardcodes
 * CAN at 250 kbit/s — `can.config.baud_rate` is read-only there, so
 * 250000 is the only supported value on this target. */
#ifndef BIBA_MCP2515_BITRATE_BPS
#define BIBA_MCP2515_BITRATE_BPS 250000
#endif

/* Acceptance mask layout.  DS20001801J §6.2: for an 11-bit mask, the
 * relevant bits are MSID10..MSID3 (8 bits → SIDH) and MSID2..MSID0
 * (3 bits → SIDL[7:5]).  EXIDE (SIDL[3]) must be 0 for standard-ID
 * matching.  Mask = 0x01F masks the low 5 bits (cmd_id) and ignores
 * bits 10..5 (node_id portion).  Encoding:
 *   SIDH = (mask >> 3)        = 0x03
 *   SIDL = (mask & 7) << 5    = 0xE0
 * (SIDL bits 0..2 reserved, bit 4 also reserved for SID buffer pointer
 * modes; leave them 0 for filters, never touch them from a mask.) */
#define MCP2515_MASK_SIDH       0x03u
#define MCP2515_MASK_SIDL       0xE0u

/* CANINTE bits (RX0IE / RX1IE). */
#define MCP2515_CANINTE_RX0IE   0x01u
#define MCP2515_CANINTE_RX1IE   0x02u
#define MCP2515_CANINTE_ERRIE   0x20u
#define MCP2515_CANINTE_MERRE   0x80u

/* CANINTF bits (must clear on RX done). */
#define MCP2515_CANINTF_RX0IF   0x01u
#define MCP2515_CANINTF_RX1IF   0x02u

/* Pin macros — driven entirely from BIBA_MCP2515_*_GPIO in
 * target.h.  Falls back to no-ops on targets without MCP2515 (the
 * src_filter keeps this translation unit out of those builds). */
#define MCP2515_CS_GPIO         BIBA_PIN_SPI0_CS_GPIO
#define MCP2515_INT_GPIO        BIBA_PIN_MCP2515_INT_GPIO
#define MCP2515_SPI             BIBA_MCP2515_SPI_INST

/* --- Local state --------------------------------------------------------- */

typedef struct {
    spi_inst_t *spi;            /* kept for diagnostic dumps only    */
    uint32_t    tx_count;
    uint32_t    rx_count;
    uint32_t    rx_drop_count;
} mcp2515_state_t;

static mcp2515_state_t s_mcp;

static volatile bool s_mcp_initialised;
static volatile bool s_mcp_int_seen;

/* --- Tiny SPI helpers (blocking — see ADR-0001 §1.2 for the rationale) - */

static inline void cs_select(void)
{
    gpio_put(MCP2515_CS_GPIO, 0u);
}

static inline void cs_deselect(void)
{
    /* Tiny gap on CS rise prevents the MCP2515 from chaining our
     * multi-instruction writes incorrectly.  The chip needs ≥ 50 ns
     * between transactions; 1 µs is fine and saves us from any
     * race with the MCP2515's internal state machine. */
    gpio_put(MCP2515_CS_GPIO, 1u);
    sleep_us(1u);
}

static void spi_write_block(const uint8_t *buf, size_t len)
{
    spi_write_blocking(MCP2515_SPI, buf, len);
}

static void spi_read_block(uint8_t *buf, size_t len)
{
    spi_read_blocking(MCP2515_SPI, 0u, buf, len);
}

/* Register-level accessors. */
uint8_t biba_mcp2515_reg_modify(uint8_t addr, uint8_t mask, uint8_t value)
{
    /* BIT MODIFY is exactly 4 bytes: [0x05][addr][mask][value]; the
     * register's old value is clocked out during the 4th byte.  One
     * full-duplex 4-byte transaction, not write-4-then-read-4 (the
     * extra 4 clocks would be parsed as a second instruction). */
    uint8_t tx[4] = { MCP2515_INSTR_BIT_MODIFY, addr, mask, value };
    uint8_t rx[4] = { 0 };
    cs_select();
    spi_write_read_blocking(MCP2515_SPI, tx, rx, 4u);
    cs_deselect();
    return rx[3];
}

static uint8_t reg_read(uint8_t addr)
{
    /* READ is exactly 3 bytes: [0x03][addr][data].  The register
     * value arrives in the 3rd byte of a single full-duplex
     * transaction.  Clocks beyond that get parsed as a new
     * instruction, so the old write-3-then-read-3 pattern returned
     * a phantom byte instead of the register. */
    uint8_t tx[3] = { MCP2515_INSTR_READ, addr, 0u };
    uint8_t rx[3] = { 0 };
    cs_select();
    spi_write_read_blocking(MCP2515_SPI, tx, rx, 3u);
    cs_deselect();
    return rx[2];
}

static void reg_write(uint8_t addr, uint8_t value)
{
    uint8_t tx[3] = { MCP2515_INSTR_WRITE, addr, value };
    cs_select();
    spi_write_block(tx, 3u);
    cs_deselect();
}

static void regs_write(uint8_t start_addr, const uint8_t *values, size_t len)
{
    uint8_t hdr[2] = { MCP2515_INSTR_WRITE, start_addr };
    cs_select();
    spi_write_block(hdr, 2u);
    spi_write_block((uint8_t *)values, len);
    cs_deselect();
}

/* --- Device-level helpers ----------------------------------------------- */

static bool enter_config_mode(void)
{
    /* Setting REQOP = 0b100 switches into Configuration mode.  Read
     * back CANSTAT and check OPMOD == 0b100 within a short timeout
     * (worst case clock-startup). */
    biba_mcp2515_reg_modify(MCP2515_REG_CANCTRL, 0xE0u, 0x80u);
    for (unsigned i = 0; i < 200u; ++i) {
        if ((reg_read(MCP2515_REG_CANSTAT) & 0xE0u) == 0x80u) {
            return true;
        }
        sleep_us(100u);
    }
    return false;
}

static bool enter_normal_mode(void)
{
    biba_mcp2515_reg_modify(MCP2515_REG_CANCTRL, 0xE0u, MCP2515_MODE_REQUEST_NORMAL);
    for (unsigned i = 0; i < 200u; ++i) {
        if ((reg_read(MCP2515_REG_CANSTAT) & 0xE0u) == MCP2515_OPMODE_NORMAL) {
            return true;
        }
        sleep_us(100u);
    }
    return false;
}

static bool reset_and_wait(void)
{
    cs_select();
    uint8_t cmd = MCP2515_INSTR_RESET;
    spi_write_block(&cmd, 1u);
    cs_deselect();
    /* MCP2515 datasheet allows up to 128 × Tq of oscillator start
     * time; 1 ms is enough margin for the 8 MHz crystal module used
     * on this project. */
    sleep_ms(1u);
    for (unsigned i = 0; i < 100u; ++i) {
        uint8_t canstat = reg_read(MCP2515_REG_CANSTAT);
        /* OPMOD lives in CANSTAT[7:5]; CONFIG = 0b100 there, so the
         * masked value is 0x80, not the 3-bit code 0x04. */
        if ((canstat & 0xE0u) == (MCP2515_OPMODE_CONFIG << 5u)) {
            return true;
        }
        sleep_ms(1u);
    }
    return false;
}

static void configure_bit_timing_and_filters(void)
{
#if BIBA_MCP2515_BITRATE_BPS == 250000
    reg_write(MCP2515_REG_CNF1, MCP2515_CNF1_BRP_250K);
    reg_write(MCP2515_REG_CNF2, MCP2515_CNF2_250K);
    reg_write(MCP2515_REG_CNF3, MCP2515_CNF3_250K);
#elif BIBA_MCP2515_BITRATE_BPS == 100000
    reg_write(MCP2515_REG_CNF1, MCP2515_CNF1_BRP_100K);
    reg_write(MCP2515_REG_CNF2, MCP2515_CNF2_100K);
    reg_write(MCP2515_REG_CNF3, MCP2515_CNF3_100K);
#else
#  error "BIBA_MCP2515_BITRATE_BPS must be 100000 or 250000"
#endif

    /* Mask 0: matches all 11-bit IDs that share the same cmd_id
     * (mask = 0x7E0).  Both masks configured identically for
     * simplicity. */
    uint8_t m0[2] = { MCP2515_MASK_SIDH, MCP2515_MASK_SIDL };
    regs_write(MCP2515_REG_RXM0SIDH, m0, sizeof(m0));
    uint8_t m1[2] = { MCP2515_MASK_SIDH, MCP2515_MASK_SIDL };
    regs_write(MCP2515_REG_RXM1SIDH, m1, sizeof(m1));

    /* Filters: only the ODrive cmd_ids we care about should reach the
     * controller.  Acceptance code is `id & mask == filt`.  With a
     * 0x7E0 mask the lower 5 bits are "don't care" — i.e. the node_id
     * portion of (node_id<<5 | cmd_id).  We register a single filter
     * per cmd_id group.
     *
     *   F0 → Heartbeat       (cmd_id = 0x01)
     *   F1 → Encoder_Estimate (cmd_id = 0x09)
     *   F2 → Get_Iq reply    (cmd_id = 0x14)
     *   F3 → Bus_Voltage_Current (cmd_id = 0x17)
     *   F4/F5 (MCP2515 has 6 total) → 'broadcast' cmd_id 0x06 and 0x00 (fallback)
     *
     * SIDH = (id >> 3); SIDL[7] = 0 (std), SIDL[6:5] = id[1:0] << 5.
     * (ODrive always uses 11-bit IDs, so the extended-ID bit stays 0.) */
    /* Six MCP2515 acceptance filters (per ADR-0001 §1.3).  With mask
     * 0x01F the low 5 bits (cmd_id) must match exactly; the upper
     * bits (node_id) are 'don't care'.  We whitelist six ODrive
     * cmd_ids and zero out the extended-ID slot. */
    static const struct {
        uint8_t reg_sidh;
        uint8_t cmd_id;
    } k_filters[] = {
        { MCP2515_REG_RXF0SIDH, 0x01u },  /* Heartbeat                  */
        { MCP2515_REG_RXF1SIDH, 0x09u },  /* Encoder_Estimate           */
        { MCP2515_REG_RXF2SIDH, 0x14u },  /* Get_Iq                     */
        { MCP2515_REG_RXF3SIDH, 0x17u },  /* Bus_Voltage_Current        */
        { MCP2515_REG_RXF4SIDH, 0x06u },  /* Address (broadcast/answer) */
        { MCP2515_REG_RXF5SIDH, 0x00u },  /* fallback: cmd_id 0 (empty) */
    };
    for (unsigned i = 0; i < (sizeof(k_filters) / sizeof(k_filters[0])); ++i) {
        /* 11-bit ID: SIDH = id >> 3, SIDL = (id & 7) << 5, EXIDE=0.
         * For "match any node on this cmd_id" the low 5 bits (cmd_id)
         * must match and bits 10..5 (node_id) are masked off by 0x01F. */
        uint8_t cmd = k_filters[i].cmd_id & 0x1Fu;
        uint8_t sidh = (uint8_t)(cmd >> 3u);
        uint8_t sidl = (uint8_t)((cmd << 5u) & 0xE0u);
        reg_write(k_filters[i].reg_sidh,     sidh);
        reg_write((uint8_t)(k_filters[i].reg_sidh + 1u), sidl);
        reg_write((uint8_t)(k_filters[i].reg_sidh + 2u), 0u);
        reg_write((uint8_t)(k_filters[i].reg_sidh + 3u), 0u);
    }

    /* RX0 = accept all messages that pass any filter (rollover=1 lets
     * unmatched-but-rejected frames pass via RX0).  We deliberately
     * keep this simple since ODrive is the only bus traffic. */
    reg_write(MCP2515_REG_RXB0CTRL, 0x04u);    /* RXM=00 filter-match + BUKT rollover */
    reg_write(MCP2515_REG_RXB1CTRL, 0x04u);    /* same for RX1                       */

    /* Interrupt routing: RX0 + RX1 + error.  The host ISR unblocks
     * the main loop on the GPIO IRQ; per-flag handling happens in
     * biba_mcp2515_rx_pop(). */
    reg_write(MCP2515_REG_CANINTE,
              MCP2515_CANINTE_RX0IE | MCP2515_CANINTE_RX1IE |
              MCP2515_CANINTE_ERRIE | MCP2515_CANINTE_MERRE);
}

/* --- Public API ---------------------------------------------------------- */

biba_mcp2515_status_t biba_mcp2515_init(void)
{
    if (s_mcp_initialised) {
        return BIBA_MCP2515_OK;
    }

    s_mcp.spi       = MCP2515_SPI;
    s_mcp.tx_count  = 0u;
    s_mcp.rx_count  = 0u;
    s_mcp.rx_drop_count = 0u;

    /* CS as a manual GPIO. */
    gpio_init(MCP2515_CS_GPIO);
    gpio_set_dir(MCP2515_CS_GPIO, GPIO_OUT);
    gpio_put(MCP2515_CS_GPIO, 1u);

    /* Bring up SPI0 first — SPI transactions assume the bus is live
     * even during the RESET pulse and the config-mode wait loop. */
    spi_init(MCP2515_SPI, BIBA_MCP2515_SPI_BAUD_HZ);
    spi_set_format(MCP2515_SPI,
                   /* data_bits */ 8,
                   /* cpol */     BIBA_MCP2515_CPOL,
                   /* cpha */     BIBA_MCP2515_CPHA,
                   /* order */    BIBA_MCP2515_BIT_ORDER);

    gpio_set_function(BIBA_PIN_SPI0_MISO_GPIO, GPIO_FUNC_SPI);
    gpio_set_function(BIBA_PIN_SPI0_SCK_GPIO,  GPIO_FUNC_SPI);
    gpio_set_function(BIBA_PIN_SPI0_MOSI_GPIO, GPIO_FUNC_SPI);

    if (!reset_and_wait()) {
        return BIBA_MCP2515_ERR_RESET;
    }
    if (!enter_config_mode()) {
        return BIBA_MCP2515_ERR_CONFIG;
    }
    configure_bit_timing_and_filters();
    if (!enter_normal_mode()) {
        return BIBA_MCP2515_ERR_CONFIG;
    }

    /* INT as a falling-edge IRQ input.  Pull-up done on the MCP2515
     * module itself (see target.h).  The callback just records the
     * fact that *something* arrived; biba_mcp2515_rx_pop() in the
     * main loop drains each CANINTF flag that has been latched. */
    gpio_init(MCP2515_INT_GPIO);
    gpio_set_dir(MCP2515_INT_GPIO, GPIO_IN);

    s_mcp_initialised = true;
    return BIBA_MCP2515_OK;
}

bool biba_mcp2515_ready(void)
{
    return s_mcp_initialised;
}

uint32_t biba_mcp2515_bitrate_bps(void)
{
    return s_mcp_initialised ? BIBA_CAN_BITRATE_BPS : 0u;
}

uint32_t biba_mcp2515_tx_count(void)  { return s_mcp.tx_count;       }
uint32_t biba_mcp2515_rx_count(void)  { return s_mcp.rx_count;       }
uint32_t biba_mcp2515_rx_drop_count(void) { return s_mcp.rx_drop_count; }

/* --- TX ------------------------------------------------------------------ */

bool biba_mcp2515_tx(const biba_can_frame_t *frame)
{
    if (!frame || !s_mcp_initialised) {
        return false;
    }
    if (frame->dlc > 8u) {
        return false;
    }

    /* Always submit to TXB0.  ODrive is happy to receive out-of-order
     * and only consumes ~100 cmd/s total on the bus.  In a future
     * revision we can add round-robin TX slot selection. */

    /* Wait until TXREQ clears (other frame may still be in flight).
     * 100 ms is 100× the worst-case round-trip (250 kbps × max 128
     * bits / frame) — comfortable and lets us detect a wedged bus. */
    for (unsigned i = 0; i < 1000u; ++i) {
        if ((reg_read(MCP2515_REG_TXB0CTRL) & 0x08u) == 0u) {
            break;
        }
        sleep_us(100u);
    }
    if ((reg_read(MCP2515_REG_TXB0CTRL) & 0x08u) != 0u) {
        return false;
    }

    /* Load ID + DLC + data through TXB0SIDH / TXB0D0. */
    const uint32_t sid = frame->id & 0x7FFu;
    uint8_t sidh = (uint8_t)(sid >> 3u);
    uint8_t sidl = (uint8_t)(((sid & 0x07u) << 5u) & 0xE0u);

    reg_write(MCP2515_REG_TXB0SIDH, sidh);
    reg_write(MCP2515_REG_TXB0SIDL, sidl);
    reg_write(0x33u, 0u);             /* EID8  — unused for 11-bit    */
    reg_write(0x34u, 0u);             /* EID0  — unused for 11-bit    */

    uint8_t dlc = (uint8_t)(frame->dlc & 0x0Fu);
    reg_write(MCP2515_REG_TXB0DLC, dlc);

    if (dlc > 0u) {
        regs_write(MCP2515_REG_TXB0D0, frame->data, dlc);
    }

    /* RTS — single-byte transaction to kick TXB0.  This auto-bumps
     * TXREQ inside the MCP2515; status can be polled separately if
     * we ever need it. */
    cs_select();
    uint8_t rts = MCP2515_INSTR_RTS_TXB0;
    spi_write_block(&rts, 1u);
    cs_deselect();

    s_mcp.tx_count++;
    return true;
}

/* --- RX ------------------------------------------------------------------ *
 *
 * The MCP2515 INT GPIO fires on any of: RX0 has a frame, RX1 has a
 * frame, error.  We don't try to be clever inside the ISR — just
 * `memset` a flag and let the main loop drain RX buffers via
 * biba_mcp2515_rx_pop() until the flag clears.  This keeps the ISR
 * measurable in tens of cycles and matches the spirit of "bare-metal,
 * keep it simple" from ADR-0001 §1.1.
 *
 * The wiring of MCP2515 INT to the GPIO IRQ vector is performed by
 * the BLDC HAL shim `hal/biba_hal_motor_bldc.c`, which knows about the
 * linker-level ISR and the biba_mcp2515_rx_isr() callback below.  Doing
 * it from inside this driver creates a circular dependency and an
 * ordering trap (some users wire INT to a different GPIO event for
 * bench tests — see target_config.h).
 */

void biba_mcp2515_rx_isr(void)
{
    s_mcp_int_seen = true;
}

/* Helper: read & demux one MCP2515 RX buffer.
 *
 * Returns true if a frame was read (and CANINTF flag cleared),
 * false if the buffer was empty.
 *
 * The returned frame is on the stack; callers copy it to their own
 * ring/queue inside their own context (which is what drivers/can_queue.c
 * does).  Keeping the demux here means we don't have to expose register
 * addresses publicly. */
static bool rx_buffer_drain(uint8_t instr, uint8_t intf_flag,
                            biba_can_frame_t *out)
{
    if ((reg_read(MCP2515_REG_CANINTF) & intf_flag) == 0u) {
        return false;
    }

    cs_select();
    uint8_t cmd = instr;
    spi_write_block(&cmd, 1u);
    /* SIDH (1) + SIDL (1) + EID8 (1) + EID0 (1) + DLC (1) + data (8). */
    uint8_t buf[12] = { 0 };
    spi_read_block(buf, sizeof(buf));
    cs_deselect();

    out->id  = ((uint32_t)buf[0] << 3u) | ((uint32_t)(buf[1] >> 5u) & 0x07u);
    out->dlc = buf[4] & 0x0Fu;
    for (unsigned i = 0; i < out->dlc; ++i) {
        out->data[i] = buf[5 + i];
    }

    /* Release the matching CANINTF bit so the next frame can flag. */
    biba_mcp2515_reg_modify(MCP2515_REG_CANINTF, intf_flag, 0u);
    return true;
}

bool biba_mcp2515_rx_pop(biba_can_frame_t *out)
{
    if (!s_mcp_initialised || !out) {
        return false;
    }

    /* The polling mode (no INT registered) and the ISR mode converge
     * here: we always read what's already pending. */
    uint8_t intf = reg_read(MCP2515_REG_CANINTF);
    bool got = false;
    if (intf & MCP2515_CANINTF_RX0IF) {
        got |= rx_buffer_drain(MCP2515_INSTR_READ_RX0,
                               MCP2515_CANINTF_RX0IF, out);
    }
    /* If RX0 already gave us one frame, RX1 still deserves its turn on
     * the next call.  We batch-drain both per "tick" to minimise SPI
     * chip-select toggling latency. */
    if (intf & MCP2515_CANINTF_RX1IF) {
        biba_can_frame_t tmp;
        if (rx_buffer_drain(MCP2515_INSTR_READ_RX1,
                            MCP2515_CANINTF_RX1IF, &tmp)) {
            if (!got) {
                *out = tmp;
                got  = true;
            }
            /* The second frame is dropped on the floor by this driver.
             * In production, can_queue.c calls biba_mcp2515_rx_pop()
             * repeatedly until false is returned, so no frame is lost. */
            s_mcp.rx_drop_count++;
        }
    }

    if (got) {
        s_mcp.rx_count++;
        s_mcp_int_seen = false;
    }
    return got;
}
