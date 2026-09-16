#include "pwm2crsf.h"

#include <string.h>

void pwm2crsf_init(pwm2crsf_state_t *state)
{
    if (state == NULL) return;
    memset(state, 0, sizeof(*state));
}

void pwm2crsf_reset_on_link_loss(pwm2crsf_state_t *state)
{
    if (state == NULL) return;
    memset(state->buttons, 0, sizeof(state->buttons));
    state->arm_ready = false;
}

uint8_t pwm2crsf_button_step(const pwm2crsf_state_t *state, uint8_t slot)
{
    if (state == NULL || slot >= PWM2CRSF_MAX_BUTTONS) return 0;
    return state->buttons[slot].step;
}

static bool input_valid(const pwm2crsf_config_t *cfg, int8_t input)
{
    return input >= 0
        && (uint8_t)input < cfg->input_count
        && (uint8_t)input < PWM2CRSF_MAX_INPUTS;
}

static bool button_enabled(const pwm2crsf_config_t *cfg, const pwm2crsf_button_t *b)
{
    return input_valid(cfg, b->input)
        && b->steps >= 2
        && b->crsf_ch < CRSF_RC_CHANNEL_COUNT;
}

/* Pulse width after the per-input invert. */
static uint32_t effective_width(const pwm2crsf_config_t *cfg, uint8_t input, uint32_t width)
{
    if (cfg->invert_mask & (1u << input)) {
        uint32_t sum = (uint32_t)cfg->min_us + cfg->max_us;
        width = (width < sum) ? sum - width : 0u;
    }
    return width;
}

static uint32_t apply_center_deadband(const pwm2crsf_config_t *cfg, uint8_t input, uint32_t width)
{
    if (!(cfg->center_deadband_mask & (1u << input)) || cfg->center_deadband_us == 0
            || cfg->max_us <= cfg->min_us) {
        return width;
    }
    int32_t centre = ((int32_t)cfg->min_us + cfg->max_us) / 2;
    int32_t half   = ((int32_t)cfg->max_us - cfg->min_us) / 2;
    int32_t db     = cfg->center_deadband_us;
    int32_t d      = (int32_t)width - centre;
    int32_t mag    = d < 0 ? -d : d;
    if (mag <= db || db >= half) return (uint32_t)centre;

    /* Stretch the remaining travel back over the full half-range. */
    int32_t span = half - db;
    int32_t out  = ((mag - db) * half + span / 2) / span;
    return (uint32_t)(d < 0 ? centre - out : centre + out);
}

static void button_on_pulse(pwm2crsf_button_state_t *bs,
                            const pwm2crsf_button_t *b,
                            const pwm2crsf_config_t *cfg,
                            uint32_t width_us,
                            uint64_t now_us)
{
    bool high;
    if (width_us >= cfg->button_high_us) {
        high = true;
    } else if (width_us <= cfg->button_low_us) {
        high = false;
    } else {
        return;   /* inside the hysteresis band: keep the old level */
    }

    if (!bs->primed) {
        /* First reading after boot / link loss is the baseline, not a press. */
        bs->primed = true;
        bs->high   = high;
        return;
    }
    if (high == bs->high) return;
    bs->high = high;

    if (!high && !b->count_both_edges) return;
    if (bs->last_edge_us != 0
            && now_us - bs->last_edge_us < cfg->button_min_interval_us) {
        return;
    }
    bs->last_edge_us = now_us;
    bs->step = (uint8_t)((bs->step + 1u) % b->steps);
}

bool pwm2crsf_on_pulse(pwm2crsf_state_t *state,
                       const pwm2crsf_config_t *cfg,
                       uint8_t input,
                       uint32_t width_us,
                       uint64_t now_us)
{
    if (state == NULL || cfg == NULL) return false;
    if (input >= cfg->input_count || input >= PWM2CRSF_MAX_INPUTS) return false;
    if (width_us < cfg->valid_min_us || width_us > cfg->valid_max_us) {
        state->glitches++;
        return false;
    }
    state->width_us[input]      = (uint16_t)width_us;
    state->last_valid_us[input] = now_us;
    state->seen[input]          = true;

    uint32_t eff = effective_width(cfg, input, width_us);
    for (unsigned i = 0; i < PWM2CRSF_MAX_BUTTONS; ++i) {
        const pwm2crsf_button_t *b = &cfg->buttons[i];
        if (button_enabled(cfg, b) && (uint8_t)b->input == input) {
            button_on_pulse(&state->buttons[i], b, cfg, eff, now_us);
        }
    }
    if (input_valid(cfg, cfg->arm_input) && (uint8_t)cfg->arm_input == input
            && eff <= cfg->button_low_us) {
        state->arm_ready = true;
    }
    return true;
}

bool pwm2crsf_input_fresh(const pwm2crsf_state_t *state,
                          const pwm2crsf_config_t *cfg,
                          uint8_t input,
                          uint64_t now_us)
{
    if (state == NULL || cfg == NULL) return false;
    if (input >= cfg->input_count || input >= PWM2CRSF_MAX_INPUTS) return false;
    if (!state->seen[input]) return false;
    if (now_us < state->last_valid_us[input]) return true;   /* stamped after `now` was sampled */
    return (now_us - state->last_valid_us[input]) <= cfg->input_timeout_us;
}

bool pwm2crsf_link_ok(const pwm2crsf_state_t *state,
                      const pwm2crsf_config_t *cfg,
                      uint64_t now_us)
{
    if (state == NULL || cfg == NULL) return false;

    uint8_t required = cfg->required_mask;
    if (required == 0) {
        for (unsigned ch = 0; ch < CRSF_RC_CHANNEL_COUNT; ++ch) {
            if (input_valid(cfg, cfg->map[ch])) required |= (uint8_t)(1u << cfg->map[ch]);
        }
    }
    if (required == 0) return false;

    for (uint8_t i = 0; i < PWM2CRSF_MAX_INPUTS; ++i) {
        if ((required & (1u << i)) && !pwm2crsf_input_fresh(state, cfg, i, now_us)) {
            return false;
        }
    }
    return true;
}

uint16_t pwm2crsf_us_to_crsf(const pwm2crsf_config_t *cfg, uint32_t width_us)
{
    if (cfg == NULL || cfg->max_us <= cfg->min_us) return PWM2CRSF_CRSF_MID;
    if (width_us <= cfg->min_us) return PWM2CRSF_CRSF_MIN;
    if (width_us >= cfg->max_us) return PWM2CRSF_CRSF_MAX;

    uint32_t span_in  = (uint32_t)(cfg->max_us - cfg->min_us);
    uint32_t span_out = PWM2CRSF_CRSF_MAX - PWM2CRSF_CRSF_MIN;
    uint32_t offset   = width_us - cfg->min_us;
    /* Round to nearest so the receiver's centre lands on 992. */
    return (uint16_t)(PWM2CRSF_CRSF_MIN + (offset * span_out + span_in / 2u) / span_in);
}

static uint16_t step_to_crsf(uint8_t step, uint8_t steps)
{
    uint32_t span = PWM2CRSF_CRSF_MAX - PWM2CRSF_CRSF_MIN;
    uint32_t last = (uint32_t)steps - 1u;
    if (step > last) step = 0;
    return (uint16_t)(PWM2CRSF_CRSF_MIN + (step * span + last / 2u) / last);
}

void pwm2crsf_channels(const pwm2crsf_state_t *state,
                       const pwm2crsf_config_t *cfg,
                       uint64_t now_us,
                       uint16_t out[CRSF_RC_CHANNEL_COUNT])
{
    if (state == NULL || cfg == NULL || out == NULL) return;

    for (unsigned ch = 0; ch < CRSF_RC_CHANNEL_COUNT; ++ch) {
        int8_t input = cfg->map[ch];
        if (input_valid(cfg, input)
                && pwm2crsf_input_fresh(state, cfg, (uint8_t)input, now_us)) {
            uint32_t width = effective_width(cfg, (uint8_t)input,
                                             state->width_us[(uint8_t)input]);
            width = apply_center_deadband(cfg, (uint8_t)input, width);
            out[ch] = pwm2crsf_us_to_crsf(cfg, width);
        } else {
            out[ch] = cfg->idle[ch];
        }
    }

    /* Step buttons own their channel; the counter survives a stale input. */
    for (unsigned i = 0; i < PWM2CRSF_MAX_BUTTONS; ++i) {
        const pwm2crsf_button_t *b = &cfg->buttons[i];
        if (!button_enabled(cfg, b)) continue;
        out[b->crsf_ch] = step_to_crsf(state->buttons[i].step, b->steps);
    }

    if (input_valid(cfg, cfg->arm_input) && cfg->arm_crsf_ch < CRSF_RC_CHANNEL_COUNT
            && !state->arm_ready) {
        out[cfg->arm_crsf_ch] = PWM2CRSF_CRSF_MIN;
    }
}

size_t pwm2crsf_build_rc_frame(const pwm2crsf_state_t *state,
                               const pwm2crsf_config_t *cfg,
                               uint64_t now_us,
                               uint8_t *out,
                               size_t out_cap)
{
    if (!pwm2crsf_link_ok(state, cfg, now_us)) return 0;

    uint16_t channels[CRSF_RC_CHANNEL_COUNT];
    uint8_t payload[CRSF_RC_PAYLOAD_SIZE];
    pwm2crsf_channels(state, cfg, now_us, channels);
    biba_crsf_pack_channels(channels, payload);
    return biba_crsf_build_frame(CRSF_FRAMETYPE_RC_CHANNELS,
                                 payload, sizeof(payload), out, out_cap);
}

size_t pwm2crsf_build_link_stats_frame(bool link_ok,
                                       uint8_t *out,
                                       size_t out_cap)
{
    biba_crsf_link_stats_t stats;
    memset(&stats, 0, sizeof(stats));
    /* RSSI fields carry -dBm; there is no real measurement behind a PWM
     * receiver, so report a fixed "good" / "none" pair. */
    stats.uplink_rssi_1       = link_ok ? 50u : 130u;
    stats.uplink_rssi_2       = stats.uplink_rssi_1;
    stats.uplink_link_quality = link_ok ? 100u : 0u;
    stats.downlink_rssi       = stats.uplink_rssi_1;
    stats.downlink_link_quality = stats.uplink_link_quality;

    uint8_t payload[CRSF_LINK_STATS_PAYLOAD_SIZE];
    biba_crsf_pack_link_stats(&stats, payload);
    return biba_crsf_build_frame(CRSF_FRAMETYPE_LINK_STATS,
                                 payload, sizeof(payload), out, out_cap);
}
