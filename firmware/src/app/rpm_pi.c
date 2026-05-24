/* FF+PI RPM controller implementation. See rpm_pi.h for API contract. */

#include "rpm_pi.h"
#include "zc_detector.h"

#include <stddef.h>

static float clampf(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static float absf(float v)
{
    return (v < 0.0f) ? -v : v;
}

void biba_rpm_pi_reset(biba_rpm_pi_state_t *s)
{
    if (s == NULL) return;
    s->integral    = 0.0f;
    s->meas_ema    = 0.0f;
    s->prev_duty   = 0.0f;
    s->prev_target = 0.0f;
    s->primed      = false;
}

float biba_rpm_pi_step(biba_rpm_pi_state_t *s,
                       const biba_rpm_pi_config_t *cfg,
                       float target_hz,
                       float meas_raw_hz)
{
    if (s == NULL || cfg == NULL) return 0.0f;

    const float target_sign = (target_hz < 0.0f) ? -1.0f : 1.0f;
    const float target_mag = absf(target_hz);
    const float meas_raw_mag = absf(meas_raw_hz);

    /* Setpoint-change integral rescaling.
     *
     * In steady state with FF+PI the integrator stores the residual FF
     * model error, which is approximately proportional to target_hz.
     * When the operator changes steering (and therefore left/right
     * setpoints) the old integrator value is sized for the old target
     * — leaving it intact creates a transient where one wheel keeps
     * driving harder than the other for several seconds.
     *
     * Scaling the integrator by the target ratio approximates the
     * "correct" steady-state I for the new target, so when steering
     * returns to centre both wheels converge together. */
    if (s->primed && s->prev_target > 1.0f && target_mag > 1.0f) {
        s->integral *= target_mag / s->prev_target;
    } else if (target_mag <= 1.0f) {
        /* Heading to deadband — drop integrator so we don’t coast. */
        s->integral = 0.0f;
    }
    s->prev_target = target_mag;

    /* EMA filter the raw measurement (delegated to zc_detector). */
    (void)zc_ema_update(&s->meas_ema, meas_raw_mag, target_mag);
    const float meas_hz = s->meas_ema;

    /* Feed-forward: duty_ff = (target + dead) / (slope * 100). */
    float ff_duty = 0.0f;
    if (cfg->ff_slope > 0.0f && target_mag > 0.0f) {
        ff_duty = (target_mag + cfg->ff_dead) / (cfg->ff_slope * 100.0f);
        ff_duty = clampf(ff_duty, 0.0f, 1.0f);
    }

    /* Gain scheduling: lower ki below the threshold for stable low-speed hold. */
    const float ki = (target_mag < cfg->ki_low_thresh) ? cfg->ki_low : cfg->ki;

    /* Asymmetric integral clamps: tighter on the negative side to bias
     * the controller toward forward authority near saturation. */
    const float i_clamp_pos = 0.03f / (ki + 1e-6f);
    const float i_clamp_neg = 0.01f / (ki + 1e-6f);

    const float err = target_mag - meas_hz;

    /* Anti-windup: do not integrate further into saturation, and require
     * meas_hz > 50 Hz so the integrator does not run away at startup
     * (matches the PoC cmd_rpmrun gate). */
    const float prev_duty_mag = absf(s->prev_duty);
    const bool sat_high = prev_duty_mag >= 0.999f;
    const bool sat_low  = prev_duty_mag <= 0.001f;
    const bool can_integrate =
        !(sat_high && err > 0.0f) &&
        !(sat_low  && err < 0.0f) &&
        (meas_hz > 50.0f);
    if (can_integrate) {
        s->integral += err * cfg->dt_s;
        s->integral = clampf(s->integral, -i_clamp_neg, i_clamp_pos);
    }

    /* P term: gated off when measurement is exactly zero (PoC pattern: no
     * proportional kick before any valid ZC sample has arrived). */
    float p_term = (meas_hz == 0.0f) ? 0.0f : (cfg->kp * err);
    p_term = clampf(p_term, -cfg->p_clamp, cfg->p_clamp);

    const float i_term = ki * s->integral;

    float duty_mag = ff_duty + p_term + i_term;

    /* Stiction floor: prevent the motor from sitting in the deadband
     * when target > 0 but duty is below the stiction threshold. */
    if (target_mag > 0.0f && duty_mag > 0.0f && duty_mag < cfg->stiction_floor) {
        duty_mag = cfg->stiction_floor;
    }

    duty_mag = clampf(duty_mag, 0.0f, 1.0f);
    const float duty = (target_mag > 0.0f) ? (target_sign * duty_mag) : 0.0f;

    s->prev_duty = duty;
    s->primed    = true;
    return duty;
}
