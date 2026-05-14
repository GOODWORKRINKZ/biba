#include "control_loop.h"

#include <math.h>
#include <string.h>

float biba_clamp_unit(float value)
{
    if (value > 1.0f) return 1.0f;
    if (value < -1.0f) return -1.0f;
    return value;
}

static float clamp_abs(float value, float limit)
{
    if (limit <= 0.0f) return value;
    if (value > limit) return limit;
    if (value < -limit) return -limit;
    return value;
}

static float apply_one_motor(float requested,
                             biba_motor_current_t sample,
                             biba_motor_limit_t cfg,
                             bool *out_limited)
{
    *out_limited = false;
    float output = biba_clamp_unit(requested);
    if (output == 0.0f) {
        return 0.0f;
    }
    if (!sample.valid) {
        /* Fail-open: keep requested output when the sensor is bad. */
        return output;
    }

    float current_a = sample.current_a;
    if (current_a < 0.0f) current_a = -current_a;

    float scale = 1.0f;

    if (cfg.current_limit_a > 0.0f && current_a > cfg.current_limit_a) {
        float s = cfg.current_limit_a / current_a;
        if (s < scale) scale = s;
    }
    if (cfg.power_limit_w > 0.0f && cfg.supply_voltage_v > 0.0f) {
        float power = cfg.supply_voltage_v * current_a;
        if (power > cfg.power_limit_w) {
            float s = cfg.power_limit_w / power;
            if (s < scale) scale = s;
        }
    }

    if (scale >= 1.0f) {
        return output;
    }

    *out_limited = true;
    return biba_clamp_unit(output * scale);
}

biba_limit_result_t biba_apply_motor_limits(float requested_left,
                                            float requested_right,
                                            biba_motor_current_t left_sample,
                                            biba_motor_current_t right_sample,
                                            biba_motor_limit_t left_cfg,
                                            biba_motor_limit_t right_cfg)
{
    biba_limit_result_t result;
    result.left = apply_one_motor(requested_left, left_sample, left_cfg, &result.left_limited);
    result.right = apply_one_motor(requested_right, right_sample, right_cfg, &result.right_limited);
    return result;
}

void biba_pid_reset(biba_pid_state_t *state)
{
    if (state == NULL) return;
    state->integral = 0.0f;
    state->last_error = 0.0f;
    state->primed = false;
}

float biba_pid_step(biba_pid_state_t *state,
                    const biba_pid_config_t *config,
                    float error,
                    float dt_s)
{
    if (state == NULL || config == NULL) return 0.0f;

    float derivative = 0.0f;
    if (dt_s > 0.0f) {
        state->integral += error * dt_s;
        state->integral = clamp_abs(state->integral, config->integral_limit);
        if (state->primed) {
            derivative = (error - state->last_error) / dt_s;
        }
    }
    state->last_error = error;
    state->primed = true;

    float output = config->kp * error
                 + config->ki * state->integral
                 + config->kd * derivative;
    return clamp_abs(output, config->output_limit);
}

biba_mix_output_t biba_mix_differential(float throttle, float steer)
{
    throttle = biba_clamp_unit(throttle);
    steer = biba_clamp_unit(steer);
    biba_mix_output_t out;
    out.left = biba_clamp_unit(throttle + steer);
    out.right = biba_clamp_unit(throttle - steer);
    return out;
}
