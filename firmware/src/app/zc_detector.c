/* A2 Sub-window Schmitt-trigger ZC detector implementation.
 * Extracted verbatim from firmware/src/poc/is_rpm_poc_main.cpp.
 * Portable C99 — no pico-sdk, no HAL. Compiles under native_test. */

#include "zc_detector.h"

#include <math.h>

zc_detector_result_t zc_freq_analyze(const uint16_t *buf, uint16_t n, uint32_t sps)
{
    zc_detector_result_t result = { 0.0f, 0u, 0u, 0u, 0.0f };
    if (n < ZC_SUBWIN_K * 4u) return result;
    uint16_t blk = n / (uint16_t)ZC_SUBWIN_K;
    uint16_t total = 0;
    uint16_t active_blocks = 0;
    for (uint16_t b = 0; b < ZC_SUBWIN_K; ++b) {
        const uint16_t *seg = buf + (uint32_t)b * blk;
        uint16_t mn = seg[0], mx = seg[0];
        uint64_t sum = seg[0];
        uint64_t sum_sq = (uint64_t)seg[0] * (uint64_t)seg[0];
        for (uint16_t i = 1; i < blk; ++i) {
            uint16_t v = seg[i];
            if (v < mn) mn = v;
            if (v > mx) mx = v;
            sum += v;
            sum_sq += (uint64_t)v * (uint64_t)v;
        }
        uint16_t pkpk = (uint16_t)(mx - mn);
        if (pkpk > result.max_pkpk) result.max_pkpk = pkpk;
        if (pkpk < ZC_SUBWIN_MIN_PKPK) continue;
        /* Per-block std-dev gate: rejects PWM/EMI noise that has high pkpk
         * (single switching edges) but low overall variability. */
        float mean_f = (float)sum / (float)blk;
        float var_f  = ((float)sum_sq / (float)blk) - (mean_f * mean_f);
        if (var_f < 0.0f) var_f = 0.0f;
        float std_f  = sqrtf(var_f);
        if (std_f > result.max_std) result.max_std = std_f;
        if (std_f < ZC_SUBWIN_MIN_STD) continue;
        active_blocks++;
        int32_t mid  = ((int32_t)mn + (int32_t)mx) / 2;
        int32_t hyst = (int32_t)pkpk / 4;
        int32_t up = mid + hyst, dn = mid - hyst;
        int state = (seg[0] > (uint16_t)mid) ? 1 : -1;
        for (uint16_t i = 1; i < blk; ++i) {
            int32_t v = (int32_t)seg[i];
            if (state > 0 && v < dn) { state = -1; total++; }
            else if (state < 0 && v > up) { state = 1; total++; }
        }
    }
    /* Require evidence from at least 2 blocks to call it real signal. */
    result.active_blocks = active_blocks;
    result.total_crossings = total;
    if (active_blocks < 2u || total < 2u) return result;
    result.freq_hz = (float)total * 0.5f * (float)sps / (float)n;
    return result;
}

float zc_freq_hz(const uint16_t *buf, uint16_t n, uint32_t sps)
{
    return zc_freq_analyze(buf, n, sps).freq_hz;
}

float zc_ema_update(float *ema, float meas_raw, float target_hz)
{
    /* Two-sided validity window. Low side: 80 Hz floor (below stiction).
     * High side: target_hz * 2.5 + 300 — anything above this is physically
     * impossible at the commanded duty point (stall ripple, PWM aliasing). */
    const float hi = target_hz * 2.5f + 300.0f;
    if (meas_raw >= ZC_MIN_VALID_HZ && meas_raw <= hi) {
        *ema = ZC_EMA_ALPHA * meas_raw + (1.0f - ZC_EMA_ALPHA) * (*ema);
    } else if (meas_raw == 0.0f) {
        /* Wheel stopped / no ZC: decay slowly toward 0 so the controller
         * can eventually recover if the wheel truly stalls.
         * Factor 0.9 per cycle (100 ms) → half-life ≈ 660 ms. */
        *ema *= 0.9f;
    }
    /* else: out-of-range noise spike — hold current EMA unchanged. */
    return *ema;
}
