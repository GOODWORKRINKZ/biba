#include "pwm2crsf.h"

#include <string.h>

void pwm2crsf_init(pwm2crsf_state_t *state)
{
    if (state == NULL) return;
    memset(state, 0, sizeof(*state));
}

void pwm2crsf_reset_cycle(pwm2crsf_state_t *state)
{
    if (state == NULL) return;
    state->cycle_primed       = false;
    state->cycle_btn_high     = false;
    state->cycle_step         = 0;
    state->cycle_last_edge_us = 0;
}

static bool cycle_enabled(const pwm2crsf_config_t *cfg)
{
    return cfg->cycle_input >= 0
        && (uint8_t)cfg->cycle_input < cfg->input_count
        && cfg->cycle_steps >= 2
        && cfg->cycle_crsf_ch < CRSF_RC_CHANNEL_COUNT;
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

static void cycle_on_pulse(pwm2crsf_state_t *state,
                           const pwm2crsf_config_t *cfg,
                           uint32_t width_us,
                           uint64_t now_us)
{
    bool high;
    if (width_us >= cfg->cycle_high_us) {
        high = true;
    } else if (width_us <= cfg->cycle_low_us) {
        high = false;
    } else {
        return;   /* inside the hysteresis band: keep the old level */
    }

    if (!state->cycle_primed) {
        /* First reading after boot / link loss is the baseline, not a press. */
        state->cycle_primed   = true;
        state->cycle_btn_high = high;
        return;
    }
    if (high == state->cycle_btn_high) return;
    state->cycle_btn_high = high;

    if (!high && !cfg->cycle_count_both_edges) return;
    if (state->cycle_last_edge_us != 0
            && now_us - state->cycle_last_edge_us < cfg->cycle_min_interval_us) {
        return;
    }
    state->cycle_last_edge_us = now_us;
    state->cycle_step = (uint8_t)((state->cycle_step + 1u) % cfg->cycle_steps);
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
    if (cycle_enabled(cfg) && input == (uint8_t)cfg->cycle_input) {
        cycle_on_pulse(state, cfg, effective_width(cfg, input, width_us), now_us);
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
    bool any_mapped = false;
    for (unsigned ch = 0; ch < CRSF_RC_CHANNEL_COUNT; ++ch) {
        int8_t input = cfg->map[ch];
        if (input == PWM2CRSF_UNMAPPED) continue;
        any_mapped = true;
        if (input < 0 || !pwm2crsf_input_fresh(state, cfg, (uint8_t)input, now_us)) {
            return false;
        }
    }
    return any_mapped;
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

void pwm2crsf_channels(const pwm2crsf_state_t *state,
                       const pwm2crsf_config_t *cfg,
                       uint16_t out[CRSF_RC_CHANNEL_COUNT])
{
    if (state == NULL || cfg == NULL || out == NULL) return;
    for (unsigned ch = 0; ch < CRSF_RC_CHANNEL_COUNT; ++ch) {
        int8_t input = cfg->map[ch];
        if (cycle_enabled(cfg) && ch == cfg->cycle_crsf_ch) {
            uint32_t span = PWM2CRSF_CRSF_MAX - PWM2CRSF_CRSF_MIN;
            uint32_t last = cfg->cycle_steps - 1u;
            uint8_t  step = state->cycle_step < cfg->cycle_steps ? state->cycle_step : 0u;
            out[ch] = (uint16_t)(PWM2CRSF_CRSF_MIN + (step * span + last / 2u) / last);
        } else if (input >= 0 && (uint8_t)input < cfg->input_count
                && (uint8_t)input < PWM2CRSF_MAX_INPUTS) {
            uint32_t width = effective_width(cfg, (uint8_t)input,
                                             state->width_us[(uint8_t)input]);
            out[ch] = pwm2crsf_us_to_crsf(cfg, width);
        } else {
            out[ch] = cfg->idle[ch];
        }
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
    pwm2crsf_channels(state, cfg, channels);
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
