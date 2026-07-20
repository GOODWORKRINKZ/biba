#include "rpm_spectral_estimator.h"
#include "biba_config.h"

#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static float clampf_local(float value, float lo, float hi)
{
    if (value < lo) return lo;
    if (value > hi) return hi;
    return value;
}

static float goertzel_amp_lsb(const uint16_t *buf, uint16_t n, float mean, uint16_t bin)
{
    float omega = 2.0f * (float)M_PI * (float)bin / (float)n;
    float coeff = 2.0f * cosf(omega);
    float q1 = 0.0f;
    float q2 = 0.0f;
    for (uint16_t i = 0; i < n; ++i) {
        float sample = (float)buf[i] - mean;
        float q0 = sample + coeff * q1 - q2;
        q2 = q1;
        q1 = q0;
    }
    float power = q1 * q1 + q2 * q2 - coeff * q1 * q2;
    if (power <= 0.0f) return 0.0f;
    return 2.0f * sqrtf(power) / (float)n;
}

biba_rpm_spectral_result_t biba_rpm_spectral_estimate(const uint16_t *buf,
                                                      uint16_t n,
                                                      uint32_t sps,
                                                      float target_hz,
                                                      float hint_hz)
{
    biba_rpm_spectral_result_t result = {
        0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
        BIBA_RPM_SPECTRAL_INVALID_NONE,
        false
    };
    if (!buf || n < 64u || sps == 0u) return result;
    if (target_hz < BIBA_RPM_SPECTRAL_MIN_TARGET_HZ) {
        result.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_TARGET_LOW;
        return result;
    }

    target_hz = clampf_local(target_hz,
                             BIBA_RPM_SPECTRAL_MIN_TARGET_HZ,
                             BIBA_RPM_SPECTRAL_MAX_TARGET_HZ);
    float half_band = target_hz * BIBA_RPM_SPECTRAL_REL_BAND;
    if (half_band < BIBA_RPM_SPECTRAL_ABS_BAND_HZ) {
        half_band = BIBA_RPM_SPECTRAL_ABS_BAND_HZ;
    }
    float f_lo = clampf_local(target_hz - half_band,
                              BIBA_RPM_SPECTRAL_MIN_TARGET_HZ,
                              BIBA_RPM_SPECTRAL_MAX_TARGET_HZ);
    float f_hi = clampf_local(target_hz + half_band,
                              BIBA_RPM_SPECTRAL_MIN_TARGET_HZ,
                              BIBA_RPM_SPECTRAL_MAX_TARGET_HZ);
    float bin_hz = (float)sps / (float)n;
    uint16_t k_lo = (uint16_t)ceilf(f_lo / bin_hz);
    uint16_t k_hi = (uint16_t)floorf(f_hi / bin_hz);
    uint16_t k_max = (uint16_t)(n / 2u);
    if (k_lo < 1u) k_lo = 1u;
    if (k_hi > k_max) k_hi = k_max;
    if (k_hi < k_lo) {
        result.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_NO_BAND;
        return result;
    }

    float sum = 0.0f;
    for (uint16_t i = 0; i < n; ++i) sum += (float)buf[i];
    float mean = sum / (float)n;
    result.mean_adc = mean;

    uint16_t best_bin = k_lo;
    float best_amp = 0.0f;
    float second_amp = 0.0f;
    for (uint16_t k = k_lo; k <= k_hi; ++k) {
        float amp = goertzel_amp_lsb(buf, n, mean, k);
        if (amp > best_amp) {
            second_amp = best_amp;
            best_amp = amp;
            best_bin = k;
        } else if (amp > second_amp) {
            second_amp = amp;
        }
    }

    float noise_sum = 0.0f;
    uint16_t noise_count = 0u;
    for (uint16_t k = k_lo; k <= k_hi; ++k) {
        int dk = (int)k - (int)best_bin;
        if (dk >= -1 && dk <= 1) continue;
        noise_sum += goertzel_amp_lsb(buf, n, mean, k);
        noise_count++;
    }
    float noise_amp = noise_count > 0u ? noise_sum / (float)noise_count : 0.0f;

    result.peak_amp_lsb = best_amp;
    result.second_amp_lsb = second_amp;
    result.quality = best_amp / (noise_amp + 1.0f);

    float delta = 0.0f;
    if (best_bin > 1u && best_bin < k_max) {
        float left = goertzel_amp_lsb(buf, n, mean, (uint16_t)(best_bin - 1u));
        float mid = best_amp;
        float right = goertzel_amp_lsb(buf, n, mean, (uint16_t)(best_bin + 1u));
        float denom = left - 2.0f * mid + right;
        if (denom != 0.0f) {
            delta = 0.5f * (left - right) / denom;
            if (delta < -0.5f) delta = -0.5f;
            if (delta >  0.5f) delta =  0.5f;
        }
    }

    result.candidate_hz = ((float)best_bin + delta) * bin_hz;

    if (best_amp < BIBA_RPM_SPECTRAL_MIN_PEAK_AMP_LSB) {
        result.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW;
        return result;
    }

    result.freq_hz = result.candidate_hz;
    result.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_NONE;
    result.valid = true;

    /* --- Dual-window hint search ---
     * If a previous valid frequency (hint_hz) is provided and lies outside
     * the plant-model search band, run a second Goertzel search centred on
     * hint_hz.  Take the result with the higher peak amplitude.
     * hint_hz == 0.0f is the backward-compatible sentinel: suppresses the
     * second window entirely.
     */
    if (hint_hz > 0.0f &&
        fabsf(hint_hz - target_hz) > BIBA_RPM_SPECTRAL_ABS_BAND_HZ * 0.5f) {

        float h_target = clampf_local(hint_hz,
                                      BIBA_RPM_SPECTRAL_MIN_TARGET_HZ,
                                      BIBA_RPM_SPECTRAL_MAX_TARGET_HZ);
        float h_half = h_target * BIBA_RPM_SPECTRAL_REL_BAND;
        if (h_half < BIBA_RPM_SPECTRAL_ABS_BAND_HZ) h_half = BIBA_RPM_SPECTRAL_ABS_BAND_HZ;
        float h_f_lo = clampf_local(h_target - h_half,
                                    BIBA_RPM_SPECTRAL_MIN_TARGET_HZ,
                                    BIBA_RPM_SPECTRAL_MAX_TARGET_HZ);
        float h_f_hi = clampf_local(h_target + h_half,
                                    BIBA_RPM_SPECTRAL_MIN_TARGET_HZ,
                                    BIBA_RPM_SPECTRAL_MAX_TARGET_HZ);
        uint16_t h_k_lo = (uint16_t)ceilf(h_f_lo / bin_hz);
        uint16_t h_k_hi = (uint16_t)floorf(h_f_hi / bin_hz);
        if (h_k_lo < 1u) h_k_lo = 1u;
        if (h_k_hi > k_max) h_k_hi = k_max;

        if (h_k_hi >= h_k_lo) {
            uint16_t h_best_bin = h_k_lo;
            float h_best_amp = 0.0f;
            for (uint16_t k = h_k_lo; k <= h_k_hi; ++k) {
                float amp = goertzel_amp_lsb(buf, n, mean, k);
                if (amp > h_best_amp) {
                    h_best_amp = amp;
                    h_best_bin = k;
                }
            }

            /* Take hint result only if its peak exceeds the plant result */
            if (h_best_amp > result.peak_amp_lsb) {
                /* Parabolic interpolation for hint peak */
                float h_delta = 0.0f;
                if (h_best_bin > 1u && h_best_bin < k_max) {
                    float h_left  = goertzel_amp_lsb(buf, n, mean,
                                                     (uint16_t)(h_best_bin - 1u));
                    float h_mid   = h_best_amp;
                    float h_right = goertzel_amp_lsb(buf, n, mean,
                                                     (uint16_t)(h_best_bin + 1u));
                    float h_denom = h_left - 2.0f * h_mid + h_right;
                    if (h_denom != 0.0f) {
                        h_delta = 0.5f * (h_left - h_right) / h_denom;
                        if (h_delta < -0.5f) h_delta = -0.5f;
                        if (h_delta >  0.5f) h_delta =  0.5f;
                    }
                }
                result.peak_amp_lsb  = h_best_amp;
                result.candidate_hz  = ((float)h_best_bin + h_delta) * bin_hz;
                result.freq_hz       = result.candidate_hz;
                result.invalid_reason = BIBA_RPM_SPECTRAL_HINT_MEASURED;
                result.valid = true;
            }
        }
    }

    return result;
}

void biba_rpm_spectral_apply_load_gate(biba_rpm_spectral_result_t *primary,
                                       biba_rpm_spectral_result_t *secondary)
{
    if (!primary || !secondary) return;

    /* Apply ratio gate to primary channel */
    if (primary->valid) {
        float other_mean = secondary->mean_adc + 1e-6f;
        float ratio = primary->mean_adc / other_mean;
        bool high_ratio = ratio > BIBA_RPM_LOAD_RATIO_THRESH &&
                          primary->quality < BIBA_RPM_LOAD_QUALITY_MAX;
        bool abs_high = primary->mean_adc > (float)BIBA_RPM_LOAD_ABS_THRESH_ADC;
        if (high_ratio || abs_high) {
            primary->valid = false;
            primary->invalid_reason = BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD;
        }
    }

    /* Apply ratio gate to secondary channel (symmetric) */
    if (secondary->valid) {
        float other_mean = primary->mean_adc + 1e-6f;
        float ratio = secondary->mean_adc / other_mean;
        bool high_ratio = ratio > BIBA_RPM_LOAD_RATIO_THRESH &&
                          secondary->quality < BIBA_RPM_LOAD_QUALITY_MAX;
        bool abs_high = secondary->mean_adc > (float)BIBA_RPM_LOAD_ABS_THRESH_ADC;
        if (high_ratio || abs_high) {
            secondary->valid = false;
            secondary->invalid_reason = BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD;
        }
    }
}