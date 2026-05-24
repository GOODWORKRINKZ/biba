#ifndef BIBA_RAMP_H
#define BIBA_RAMP_H

/* Output slew-rate limiter for motor speed commands.
 *
 * Port of biba-controller/motors/ramping.py::SpeedRamp.
 * Per-motor state is owned by the caller (mode_standalone.c).
 * Config constants live in biba_config.h (BIBA_RAMP_*). */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float current;           /* _current in Python SpeedRamp */
    float hold_remaining_s;  /* _hold_remaining in Python SpeedRamp */
} biba_ramp_t;

/* Initialise the ramp state to zero. */
void  biba_ramp_init(biba_ramp_t *r);

/* Hard-reset to zero — emergency stop, no gradual decel (D-04). */
void  biba_ramp_reset(biba_ramp_t *r);

/* Compute the next ramped output value given target in [-1, 1] and dt in seconds.
 * Returns the new current value (also stored in r->current). */
float biba_ramp_update(biba_ramp_t *r, float target, float dt);

/* Same ramp logic with caller-provided rates. Useful when a control mode needs
 * a softer command shaper than the global open-loop motor ramp constants. */
float biba_ramp_update_with_rates(biba_ramp_t *r, float target, float dt,
                                  float accel_rate, float decel_rate,
                                  float reverse_decel_rate,
                                  uint32_t zero_hold_ms);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_RAMP_H */
