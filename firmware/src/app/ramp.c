#include "ramp.h"
#include "biba_config.h"
#include <stddef.h>

/* Cap for zero_time_s so it never overflows float precision. */
#define ZERO_TIME_CAP_S  1000.0f

void biba_ramp_init(biba_ramp_t *r)
{
    if (r == NULL) return;
    r->current          = 0.0f;
    r->hold_remaining_s = 0.0f;
    r->zero_time_s      = ZERO_TIME_CAP_S;
    r->last_dir         = 0;
}

void biba_ramp_reset(biba_ramp_t *r)
{
    /* D-04: hard reset — emergency stop, no gradual decel */
    if (r == NULL) return;
    if (r->current != 0.0f) {
        r->zero_time_s = 0.0f;
    }
    r->current          = 0.0f;
    r->hold_remaining_s = 0.0f;
}

float biba_ramp_update_with_rates(biba_ramp_t *r, float target, float dt,
                                  float accel_rate, float decel_rate,
                                  float reverse_decel_rate,
                                  uint32_t zero_hold_ms)
{
    /* Guard: first tick or clock wrap — return current unchanged (Pitfall 1). */
    if (dt <= 0.0f) return r->current;

    /* Clamp target to valid range. */
    if (target >  1.0f) target =  1.0f;
    if (target < -1.0f) target = -1.0f;

    const float hold_s = (float)zero_hold_ms / 1000.0f;

    if (r->current > 0.0f) {
        r->last_dir = 1;
    } else if (r->current < 0.0f) {
        r->last_dir = -1;
    } else if (r->zero_time_s < ZERO_TIME_CAP_S) {
        r->zero_time_s += dt;
    }
    r->hold_remaining_s = 0.0f;

    /* Zero hold: the output is at zero and the command asks for the other
     * direction — wait until the output has rested at zero long enough. */
    if (r->current == 0.0f && r->last_dir != 0 &&
        ((r->last_dir > 0 && target < 0.0f) || (r->last_dir < 0 && target > 0.0f))) {
        if (r->zero_time_s < hold_s) {
            r->hold_remaining_s = hold_s - r->zero_time_s;
            return r->current;  /* still holding at 0.0 */
        }
    }

    /* Direction change: decelerate toward zero, do NOT cross it.
     * Uses reverse_decel_rate (slower than normal decel). */
    if ((r->current > 0.0f && target < 0.0f) ||
        (r->current < 0.0f && target > 0.0f)) {

        float max_step = reverse_decel_rate * dt;
        float abs_cur  = (r->current < 0.0f) ? -r->current : r->current;

        if (abs_cur <= max_step) {
            /* Reached zero: start the hold. */
            r->current          = 0.0f;
            r->zero_time_s      = 0.0f;
            r->hold_remaining_s = hold_s;
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
    float rate         = accelerating ? accel_rate : decel_rate;
    float max_step     = rate * dt;
    bool  was_moving   = (r->current != 0.0f);

    if (abs_diff <= max_step) {
        r->current = target;
    } else {
        r->current += (diff > 0.0f) ? max_step : -max_step;
    }

    /* Final output clamp. */
    if (r->current >  1.0f) r->current =  1.0f;
    if (r->current < -1.0f) r->current = -1.0f;

    if (r->current > 0.0f) {
        r->last_dir = 1;
    } else if (r->current < 0.0f) {
        r->last_dir = -1;
    } else if (was_moving) {
        r->zero_time_s = 0.0f;  /* just came to rest */
    }

    return r->current;
}

float biba_ramp_update(biba_ramp_t *r, float target, float dt)
{
    return biba_ramp_update_with_rates(r, target, dt,
                                       BIBA_RAMP_ACCEL_RATE,
                                       BIBA_RAMP_DECEL_RATE,
                                       BIBA_RAMP_REVERSE_DECEL_RATE,
                                       BIBA_RAMP_ZERO_HOLD_MS);
}
