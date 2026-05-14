#include "ramp.h"
#include "biba_config.h"
#include <stddef.h>

void biba_ramp_init(biba_ramp_t *r)
{
    if (r == NULL) return;
    r->current          = 0.0f;
    r->hold_remaining_s = 0.0f;
}

void biba_ramp_reset(biba_ramp_t *r)
{
    /* D-04: hard reset — emergency stop, no gradual decel */
    if (r == NULL) return;
    r->current          = 0.0f;
    r->hold_remaining_s = 0.0f;
}

float biba_ramp_update(biba_ramp_t *r, float target, float dt)
{
    /* Guard: first tick or clock wrap — return current unchanged (Pitfall 1). */
    if (dt <= 0.0f) return r->current;

    /* Clamp target to valid range. */
    if (target >  1.0f) target =  1.0f;
    if (target < -1.0f) target = -1.0f;

    /* Zero-hold: stay frozen at zero until hold timer expires. */
    if (r->hold_remaining_s > 0.0f) {
        r->hold_remaining_s -= dt;
        if (r->hold_remaining_s > 0.0f) {
            return r->current;  /* still holding at 0.0 */
        }
        r->hold_remaining_s = 0.0f;
    }

    /* Direction change: decelerate toward zero, do NOT cross it.
     * Uses BIBA_RAMP_REVERSE_DECEL_RATE (slower than normal decel). */
    if ((r->current > 0.0f && target < 0.0f) ||
        (r->current < 0.0f && target > 0.0f)) {

        float max_step = BIBA_RAMP_REVERSE_DECEL_RATE * dt;
        float abs_cur  = (r->current < 0.0f) ? -r->current : r->current;

        if (abs_cur <= max_step) {
            /* Reached zero: arm the hold timer. */
            r->current          = 0.0f;
            r->hold_remaining_s = (float)BIBA_RAMP_ZERO_HOLD_MS / 1000.0f;
        } else if (r->current > 0.0f) {
            r->current -= max_step;
        } else {
            r->current += max_step;
        }
        return r->current;
    }

    /* Same sign (or zero → nonzero): accelerate or decelerate. */
    float diff     = target - r->current;
    float abs_diff = (diff < 0.0f) ? -diff : diff;

    if (abs_diff < 1e-9f) {
        return r->current;
    }

    float abs_target  = (target    < 0.0f) ? -target    : target;
    float abs_current = (r->current < 0.0f) ? -r->current : r->current;
    int   accelerating = (abs_target > abs_current);
    float rate         = accelerating ? BIBA_RAMP_ACCEL_RATE : BIBA_RAMP_DECEL_RATE;
    float max_step     = rate * dt;

    if (abs_diff <= max_step) {
        r->current = target;
    } else {
        r->current += (diff > 0.0f) ? max_step : -max_step;
    }

    /* Final output clamp. */
    if (r->current >  1.0f) r->current =  1.0f;
    if (r->current < -1.0f) r->current = -1.0f;

    return r->current;
}
