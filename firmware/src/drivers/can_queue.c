#include "can_queue.h"

#include <string.h>

/* Power-of-two capacity makes wrap arithmetic a bit-and. */
#define CAP      BIBA_CAN_QUEUE_CAP
#define MASK     (CAP - 1u)

typedef struct {
    biba_can_frame_t buf[CAP];
    /* Both heads/tails are uint8_t so they wrap on their own; the
     * "producer side" index is volatile so the consumer never reads
     * stale data after the producer returns from push. */
    volatile uint8_t head;       /* producer inserts here */
    uint8_t          tail;       /* consumer removes from here */
} ring_t;

static ring_t  s_rx_ring;
static ring_t  s_tx_ring;

static volatile uint32_t s_rx_push, s_rx_pop, s_rx_overflow;
static volatile uint32_t s_tx_push, s_tx_pop, s_tx_overflow;

static inline bool ring_full(uint8_t head, uint8_t tail)
{
    return (uint8_t)(head - tail) == (uint8_t)CAP;
}

static inline bool ring_empty(uint8_t head, uint8_t tail)
{
    return head == tail;
}

static void rx_init(void)
{
    memset(&s_rx_ring, 0, sizeof(s_rx_ring));
}
static void tx_init(void)
{
    memset(&s_tx_ring, 0, sizeof(s_tx_ring));
}

void biba_can_queue_rx_init(void) { rx_init(); }
void biba_can_queue_tx_init(void) { tx_init(); }

bool biba_can_queue_rx_push(const biba_can_frame_t *frame)
{
    if (!frame) return false;
    uint8_t h = s_rx_ring.head;
    uint8_t t = s_rx_ring.tail;
    if (ring_full(h, t)) {
        s_rx_overflow++;
        return false;
    }
    s_rx_ring.buf[h & MASK] = *frame;
    /* Publish: write through `s_rx_ring.head` last so the consumer
     * cannot read garbage.  Compiler cannot reorder past volatile. */
    s_rx_ring.head = (uint8_t)(h + 1u);
    s_rx_push++;
    return true;
}

bool biba_can_queue_rx_pop(biba_can_frame_t *out)
{
    if (!out) return false;
    uint8_t t = s_rx_ring.tail;
    uint8_t h = s_rx_ring.head;
    if (ring_empty(h, t)) {
        return false;
    }
    *out = s_rx_ring.buf[t & MASK];
    s_rx_ring.tail = (uint8_t)(t + 1u);
    s_rx_pop++;
    return true;
}

bool biba_can_queue_tx_push(const biba_can_frame_t *frame)
{
    if (!frame) return false;
    uint8_t h = s_tx_ring.head;
    uint8_t t = s_tx_ring.tail;
    if (ring_full(h, t)) {
        s_tx_overflow++;
        return false;
    }
    s_tx_ring.buf[h & MASK] = *frame;
    s_tx_ring.head = (uint8_t)(h + 1u);
    s_tx_push++;
    return true;
}

bool biba_can_queue_tx_pop(biba_can_frame_t *out)
{
    if (!out) return false;
    uint8_t t = s_tx_ring.tail;
    uint8_t h = s_tx_ring.head;
    if (ring_empty(h, t)) {
        return false;
    }
    *out = s_tx_ring.buf[t & MASK];
    s_tx_ring.tail = (uint8_t)(t + 1u);
    s_tx_pop++;
    return true;
}

uint32_t biba_can_queue_rx_push_count(void)      { return s_rx_push; }
uint32_t biba_can_queue_rx_pop_count(void)       { return s_rx_pop; }
uint32_t biba_can_queue_rx_overflow_count(void)  { return s_rx_overflow; }
uint32_t biba_can_queue_tx_push_count(void)      { return s_tx_push; }
uint32_t biba_can_queue_tx_pop_count(void)       { return s_tx_pop; }
uint32_t biba_can_queue_tx_overflow_count(void)  { return s_tx_overflow; }
