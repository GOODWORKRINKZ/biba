#ifndef BIBA_MCP2515_H
#define BIBA_MCP2515_H

/* Low-level driver for the Microchip MCP2515 SPI↔CAN bridge plus a thin
 * on-top CAN-frame TX/RX API.  The API mirrors exactly what the
 * `odrive_can` driver needs; the rest of the firmware never touches the
 * MCP2515 registers directly.
 *
 * Scope of this module:
 *   - Initialise SPI0 (RP2040) plus the MCP2515 (reset, configuration
 *     registers, filters, operating mode).
 *   - Submit a TX frame to a free TX buffer and trigger RTS.
 *   - Drain RX frames (one at a time) into a caller-owned buffer.
 *   - Install the GPIO IRQ handler for MCP2515 INT (RX pending / error).
 *
 * Anything higher-level — actual ODrive / VESC protocol encoding,
 * periodic heartbeat tracking, node discovery — lives in
 * `drivers/odrive_can.c` and `drivers/vesc_can.c`.  Keeping these
 * split matches the ADR-0001 §4 table ("drivers/mcp2515.c ~400 LoC,
 * drivers/odrive_can.c ~300 LoC").
 *
 * Two bus dialects share this driver (ADR-0002):
 *   - ODrive CANSimple — 11-bit standard IDs, 250 kbps, six acceptance
 *     filters whitelisting the cmd_ids we consume.
 *   - VESC CAN         — 29-bit extended IDs, 500 kbps, accept-all
 *     (the VESC id lives in the low 8 bits, so a cmd-wise filter would
 *     need the extended mask registers; not worth it for a 2-node bus).
 * Both are selected from the target's target_config.h via
 * BIBA_CAN_BITRATE_BPS and BIBA_MCP2515_ACCEPT_ALL.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* CAN frame representation.  Covers both bus dialects: the ODrive
 * CANSimple envelope (11-bit ID) and the VESC envelope (29-bit
 * extended ID).  See ADR-0001 §1.3 and ADR-0002 §2.
 *
 * `ext == false` → `id` is an 11-bit standard identifier (bits 10:0;
 * higher bits ignored).  `ext == true` → `id` is a 29-bit extended
 * identifier (bits 28:0).  RX fills `ext` from the IDE bit of the
 * received frame, so a caller can tell the two apart on a mixed bus. */
typedef struct {
    uint32_t id;       /* 11-bit std, or 29-bit when `ext` is set. */
    bool     ext;      /* true = 29-bit extended identifier (IDE). */
    uint8_t  dlc;      /* 0..8 */
    uint8_t  data[8];
} biba_can_frame_t;

/* Status returned by mcp2515_init(). */
typedef enum {
    BIBA_MCP2515_OK          =  0,
    BIBA_MCP2515_ERR_SPI     = -1,  /* SPI peripheral setup failed.     */
    BIBA_MCP2515_ERR_RESET   = -2,  /* No response to RESET instruction.*/
    BIBA_MCP2515_ERR_CONFIG  = -3,  /* CNF1/CNF2/CNF3 reject (mode-locked) */
} biba_mcp2515_status_t;

/* One-shot bring-up.  Wires SPI0 + CS + INT, runs the MCP2515 RESET
 * sequence, configures BIBA_CAN_BITRATE_BPS with an 87.5 % sample
 * point (see ADR-0001 §1.3 / §1.5), enables RX0 + RX1 rollover with
 * either the ODrive CANSimple acceptance filters (Heartbeat +
 * Set_Input_Vel + the broadcast slot) or accept-all when
 * BIBA_MCP2515_ACCEPT_ALL is set, and enters Normal mode.
 *
 * Idempotent: calling twice is a no-op.  Safe to call from `setup()`
 * before `biba_bldc_init()`. */
biba_mcp2515_status_t biba_mcp2515_init(void);

/* True once biba_mcp2515_init() has returned BIBA_MCP2515_OK. */
bool biba_mcp2515_ready(void);

/* (Re)program the chip: RESET, config mode, bit timing + filters,
 * normal mode.  Used at bring-up and to recover from a bus-off wedge.
 * Assumes SPI0 is already configured. */
biba_mcp2515_status_t biba_mcp2515_reconfigure(void);

/* True when the controller reports a transmit error-passive/bus-off
 * condition (EFLG TXEP/TXBO).  A bus-off wedge stops TX/RX until the
 * chip is reset. */
bool biba_mcp2515_bus_off(void);

/* If the controller is in bus-off, force a full chip reset +
 * reconfigure.  Returns true when a recovery was actually performed. */
bool biba_mcp2515_recover(void);

/* Number of bits per second the CAN bus runs at.  Defaults to
 * BIBA_CAN_BITRATE_BPS.  Returns 0 if the controller is not configured
 * (i.e. mcp2515_init was never called or failed). */
uint32_t biba_mcp2515_bitrate_bps(void);

/* TX a single frame.  Returns true on acceptance (queued in TX buffer
 * 0); false if no TX slot was free, the bus is bus-passive, or the
 * controller is not yet in Normal mode.
 *
 * The caller must keep `frame.data` alive only until this function
 * returns — the frame is copied into the MCP2515 TX buffer before the
 * SPI transaction finishes. */
bool biba_mcp2515_tx(const biba_can_frame_t *frame);

/* Pop one received frame.  Returns true and fills `*out` if a frame was
 * available; returns false when no frame is buffered.  Called from the
 * main loop (typically right after the INT GPIO IRQ fires). */
bool biba_mcp2515_rx_pop(biba_can_frame_t *out);

/* Approximate counts of TX attempts / RX frames since boot.  Useful
 * for the biba-odrive heartbeat monitor and debug logs.  Both saturate
 * at UINT32_MAX. */
uint32_t biba_mcp2515_tx_count(void);
uint32_t biba_mcp2515_rx_count(void);
uint32_t biba_mcp2515_rx_drop_count(void);
uint32_t biba_mcp2515_recovery_count(void);

/* Bit-modify helper.  Exposed for unit tests only. */
uint8_t biba_mcp2515_reg_modify(uint8_t addr, uint8_t mask, uint8_t value);

/* GPIO IRQ hook — must be called from the falling-edge callback
 * installed by the BLDC HAL-shim on BIBA_PIN_MCP2515_INT_GPIO.  Marks
 * pending RX so biba_mcp2515_rx_pop() knows to drain on the next
 * tick.  No-op when MCP2515 is not initialised.  Re-entrant (safe to
 * call from the GPIO IRQ vector). */
void biba_mcp2515_rx_isr(void);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_MCP2515_H */
