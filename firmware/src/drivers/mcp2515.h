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
 * Anything higher-level — actual ODrive protocol encoding, periodic
 * heartbeat tracking, ODrive-side discovery — lives in
 * `drivers/odrive_can.c`.  Keeping these split matches the ADR-0001 §4
 * table ("drivers/mcp2515.c ~400 LoC, drivers/odrive_can.c ~300 LoC").
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* CAN frame representation.  Matches the ODrive CANSimple envelope
 * (11-bit ID, ≤8 bytes data).  See ADR-0001 §1.3. */
typedef struct {
    uint32_t id;       /* 11-bit identifier (top bits ignored). */
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
 * sequence, configures 250 kbps with 87.5 % sample point (see
 * ADR-0001 §1.3 / §1.5), enables RX0 + RX1 rollover with the standard
 * ODrive CANSimple acceptance filters (Heartbeat + Set_Input_Vel + the
 * broadcast slot) and enters Normal mode.
 *
 * Idempotent: calling twice is a no-op.  Safe to call from `setup()`
 * before `biba_odrive_can_init()`. */
biba_mcp2515_status_t biba_mcp2515_init(void);

/* True once biba_mcp2515_init() has returned BIBA_MCP2515_OK. */
bool biba_mcp2515_ready(void);

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
