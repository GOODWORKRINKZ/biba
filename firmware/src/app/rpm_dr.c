#include "app/rpm_dr.h"
#include "biba_config.h"   /* BIBA_RPM_DR_MAX_STREAK, BIBA_RPM_DR_RATIO_LO/HI/ALPHA */

void biba_rpm_dr_reset(biba_rpm_dr_state_t *state)
{
    state->ratio_ema = 0.0f;
    state->streak    = 0u;
}

float biba_rpm_dr_update(biba_rpm_dr_state_t                *state,
                         const biba_rpm_spectral_result_t   *spec,
                         float                               target_hz,
                         biba_rpm_spectral_invalid_reason_t *out_reason)
{
    if (spec->valid) {
        /* Valid measurement: update ratio EMA, reset streak. */
        state->streak = 0u;
        if (target_hz >= BIBA_RPM_SPECTRAL_MIN_TARGET_HZ) {
            float ratio = spec->freq_hz / target_hz;
            /* Clamp before EMA update to prevent unconstrained initial ratio. */
            if (ratio < BIBA_RPM_DR_RATIO_LO) { ratio = BIBA_RPM_DR_RATIO_LO; }
            if (ratio > BIBA_RPM_DR_RATIO_HI) { ratio = BIBA_RPM_DR_RATIO_HI; }
            state->ratio_ema = BIBA_RPM_DR_ALPHA * ratio
                             + (1.0f - BIBA_RPM_DR_ALPHA) * state->ratio_ema;
        }
        *out_reason = BIBA_RPM_SPECTRAL_INVALID_NONE;
        return spec->freq_hz;
    }

    /* Invalid measurement: attempt dead-reckoning. */
    if (state->streak <= BIBA_RPM_DR_MAX_STREAK
        && state->ratio_ema > 0.0f
        && target_hz >= BIBA_RPM_SPECTRAL_MIN_TARGET_HZ)
    {
        *out_reason = BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED;
        /* Clamp streak at 255 to prevent uint8_t overflow. */
        if (state->streak < 255u) { state->streak++; }
        return state->ratio_ema * target_hz;
    }

    /* Cold start (ratio_ema == 0) or streak expired: return 0. */
    *out_reason = spec->invalid_reason;
    if (state->streak < 255u) { state->streak++; }
    return 0.0f;
}
