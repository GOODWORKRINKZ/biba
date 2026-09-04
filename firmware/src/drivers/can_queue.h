#ifndef BIBA_CAN_QUEUE_H
#define BIBA_CAN_QUEUE_H

/* Tiny single-producer / single-consumer ring queue for biba_can_frame_t.
 *
 * One consumer of RX frames (the application tick — odrive_can.c), and
 * one producer (the ISR-driven MCP2515 drain path).  TX has the
 * reverse topology.
 *
 * Sized at 16 entries.  At 250 kbps with a maximum of ~30 Rx frames
 * per second per ODrive (heartbeat + telemetry pulls), 16 gives well
 * over a second of headroom before we ever need to drop anything.
 *
 * ISR safety: the producer is allowed to run inside a GPIO IRQ; the
 * consumer runs at thread priority.  No locks are used: both indices
 * are unsigned and naturally wrap, and the producer's index is
 * `volatile` so the consumer sees fresh data.  Capacity is a power of
 * two so the wrap is a bit-and.
 */

#include "drivers/mcp2515.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define BIBA_CAN_QUEUE_CAP  16u

void biba_can_queue_rx_init(void);
void biba_can_queue_tx_init(void);

/* ISR-safe push from MCP2515 RX context (or thread context — push
 * is one direction only).  Returns false only if the queue is full. */
bool biba_can_queue_rx_push(const biba_can_frame_t *frame);
/* Thread-safe pull from the application tick.  Returns false if the
 * queue is empty. */
bool biba_can_queue_rx_pop(biba_can_frame_t *out);

/* TX queue: application pushes here; the BLDC HAL-shim drains into
 * the MCP2515 in the same tick. */
bool biba_can_queue_tx_push(const biba_can_frame_t *frame);
bool biba_can_queue_tx_pop(biba_can_frame_t *out);

/* Diagnostic counters — saturating. */
uint32_t biba_can_queue_rx_push_count(void);
uint32_t biba_can_queue_rx_pop_count(void);
uint32_t biba_can_queue_rx_overflow_count(void);
uint32_t biba_can_queue_tx_push_count(void);
uint32_t biba_can_queue_tx_pop_count(void);
uint32_t biba_can_queue_tx_overflow_count(void);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_CAN_QUEUE_H */
