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
    float  current;           /* _current in Python SpeedRamp */
    float  hold_remaining_s;  /* pause left before driving the other way (info) */
    float  zero_time_s;       /* time the output has been sitting at zero */
    int8_t last_dir;          /* sign of the last non-zero output, 0 = none */
} biba_ramp_t;

/* Initialise the ramp state to zero. */
void  biba_ramp_init(biba_ramp_t *r);

/* Hard-reset to zero — emergency stop, no gradual decel (D-04).
 * Keeps the last direction, so a reversal right after the reset still
 * waits the zero hold. */
void  biba_ramp_reset(biba_ramp_t *r);

/* Compute the next ramped output value given target in [-1, 1] and dt in seconds.
 * Returns the new current value (also stored in r->current).
 *
 * Direction change: the output first decays to zero at reverse_decel_rate,
 * then stays at zero until it has been there for zero_hold_ms — also when
 * the command passed through zero (stick centred) before reversing — and
 * only then accelerates the other way.
 * Divergence from Python SpeedRamp: there the hold only follows a sign flip
 * while the output is still non-zero.
 *
 * Reversal latency is therefore |current| / reverse_decel_rate + zero_hold_ms;
 * keep that budget under ~0.3 s or steering through a sign flip feels like the
 * wheel dropped out (field test 2026-09-20). A reverse_decel_rate <= 0 means
 * "no reversal slew limit" — cross zero on the next tick.
 *
 * Steering does NOT always take that path. With the throttle held the mixer
 * asks the inner wheel for a smaller duty of the SAME sign, so the latency is
 * (current - target) / decel_rate with no hold at all. Both paths are steering,
 * so decel_rate carries the same ~0.3 s budget; keeping the two rates equal is
 * enforced by a _Static_assert in ramp.c (field test 2026-09-21, where only
 * the reversal path had been made fast and the machine would not change course
 * until the operator released the throttle). */
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
