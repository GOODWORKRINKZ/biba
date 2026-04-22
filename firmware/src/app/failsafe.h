#ifndef BIBA_FAILSAFE_H
#define BIBA_FAILSAFE_H

/* Failsafe helpers shared between standalone and companion modes.
 *
 * Each source (CRSF uplink, SBC SPI link) feeds its own biba_failsafe_t.
 * When the input goes stale the failsafe arms and callers must zero the
 * motor command. Host tests drive this purely through the tick() inputs
 * so no system clock is required in the module itself. */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t timeout_ms;
    uint32_t last_ok_ms;
    bool     primed;
    bool     active;
} biba_failsafe_t;

/* Initialise the failsafe with a grace period. active=false until tick runs. */
void biba_failsafe_init(biba_failsafe_t *fs, uint32_t timeout_ms);

/* Mark that a fresh frame has just been received at now_ms. */
void biba_failsafe_mark_fresh(biba_failsafe_t *fs, uint32_t now_ms);

/* Advance time without a fresh frame. Updates active flag. Returns true
 * iff the failsafe is currently active (i.e. upstream is silent). */
bool biba_failsafe_tick(biba_failsafe_t *fs, uint32_t now_ms);

/* Query current state without advancing time. */
bool biba_failsafe_is_active(const biba_failsafe_t *fs);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_FAILSAFE_H */
