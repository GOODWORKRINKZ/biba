#ifndef BIBA_CONTROL_LOOP_H
#define BIBA_CONTROL_LOOP_H

/* Shared control math for BiBa: motor limiter, heading-hold PID, and
 * the final mixer output. Kept portable (no HAL dependency) so it can be
 * tested with plain gcc in test/test_control_loop.
 *
 * The limiter behaviour intentionally mirrors
 * biba-controller/motors/current_control.py: per-motor scaling by the
 * worst-case current or power excess, fail-open on invalid samples. */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float current_a;   /* measured motor current in amps, positive magnitude */
    bool  valid;       /* false to request fail-open behaviour */
} biba_motor_current_t;

typedef struct {
    float current_limit_a;   /* per-motor current clamp (A), <=0 disables */
    float power_limit_w;     /* per-motor power clamp (W), <=0 disables */
    float supply_voltage_v;  /* V used for power calc; <=0 disables power limit */
} biba_motor_limit_t;

typedef struct {
    float left;
    float right;
    bool  left_limited;
    bool  right_limited;
} biba_limit_result_t;

/* Clamp `value` into [-1.0, 1.0]. Exposed for tests. */
float biba_clamp_unit(float value);

/* Apply independent current/power limits to a pair of motor commands. */
biba_limit_result_t biba_apply_motor_limits(float requested_left,
                                            float requested_right,
                                            biba_motor_current_t left_sample,
                                            biba_motor_current_t right_sample,
                                            biba_motor_limit_t left_cfg,
                                            biba_motor_limit_t right_cfg);

/* --- Heading-hold PID --------------------------------------------------- */

typedef struct {
    float kp;
    float ki;
    float kd;
    float output_limit;   /* clamp absolute PID output (normalized steer) */
    float integral_limit; /* anti-windup clamp on the integral term */
} biba_pid_config_t;

typedef struct {
    float integral;
    float last_error;
    bool  primed;
} biba_pid_state_t;

/* Reset PID to zero. Called on disarm/failsafe transitions. */
void biba_pid_reset(biba_pid_state_t *state);

/* Run one step of the PID.
 * `dt_s` must be >0; if <=0 the derivative term is skipped.
 * Returns a steering correction in [-output_limit, +output_limit]. */
float biba_pid_step(biba_pid_state_t *state,
                    const biba_pid_config_t *config,
                    float error,
                    float dt_s);

/* --- Differential mixer ------------------------------------------------- */

typedef struct {
    float left;
    float right;
} biba_mix_output_t;

/* Differential drive mixer. `throttle` and `steer` are both in [-1, 1]. */
biba_mix_output_t biba_mix_differential(float throttle, float steer);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_CONTROL_LOOP_H */
