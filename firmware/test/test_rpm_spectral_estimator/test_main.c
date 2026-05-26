/* Unity tests for the target-bounded spectral RPM estimator. */

#include <math.h>
#include <stdint.h>

#include "rpm_spectral_estimator.h"
#include "biba_test_support.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static void fill_sine(uint16_t *buf, uint16_t n, uint32_t sps,
                      float freq_hz, uint16_t dc, uint16_t amp)
{
    for (uint16_t i = 0; i < n; ++i) {
        float t = (float)i / (float)sps;
        float v = (float)dc + sinf(2.0f * (float)M_PI * freq_hz * t) * (float)amp;
        int32_t iv = (int32_t)(v + 0.5f);
        if (iv < 0) iv = 0;
        if (iv > 4095) iv = 4095;
        buf[i] = (uint16_t)iv;
    }
}

static void fill_two_sines(uint16_t *buf, uint16_t n, uint32_t sps,
                           float f1_hz, float amp1,
                           float f2_hz, float amp2)
{
    for (uint16_t i = 0; i < n; ++i) {
        float t = (float)i / (float)sps;
        float v = 2048.0f
                + sinf(2.0f * (float)M_PI * f1_hz * t) * amp1
                + sinf(2.0f * (float)M_PI * f2_hz * t) * amp2;
        int32_t iv = (int32_t)(v + 0.5f);
        if (iv < 0) iv = 0;
        if (iv > 4095) iv = 4095;
        buf[i] = (uint16_t)iv;
    }
}

static void fill_noisy_two_sines(uint16_t *buf, uint16_t n, uint32_t sps,
                                 float f1_hz, float amp1,
                                 float f2_hz, float amp2,
                                 uint16_t noise_amp)
{
    uint32_t rng = 42u;
    for (uint16_t i = 0; i < n; ++i) {
        rng = rng * 1664525u + 1013904223u;
        int32_t noise = (int32_t)((rng >> 16) % (uint32_t)(noise_amp * 2u + 1u)) - (int32_t)noise_amp;
        float t = (float)i / (float)sps;
        float v = 2048.0f
                + sinf(2.0f * (float)M_PI * f1_hz * t) * amp1
                + sinf(2.0f * (float)M_PI * f2_hz * t) * amp2
                + (float)noise;
        int32_t iv = (int32_t)(v + 0.5f);
        if (iv < 0) iv = 0;
        if (iv > 4095) iv = 4095;
        buf[i] = (uint16_t)iv;
    }
}

static void test_512_sample_sine_tracks_target(void)
{
    static uint16_t buf[512];
    fill_sine(buf, 512, 10000u, 300.0f, 2048u, 500u);
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f, 0.0f);
    TEST_ASSERT_TRUE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(25.0f, 300.0f, result.freq_hz);
    TEST_ASSERT_FLOAT_WITHIN(25.0f, result.freq_hz, result.candidate_hz);
    TEST_ASSERT_TRUE(result.quality >= 3.0f);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_NONE, result.invalid_reason);
}

static void test_ignores_strong_out_of_band_parasite(void)
{
    static uint16_t buf[512];
    fill_two_sines(buf, 512, 10000u, 300.0f, 350.0f, 430.0f, 900.0f);
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f, 0.0f);
    TEST_ASSERT_TRUE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(35.0f, 300.0f, result.freq_hz);
}

static void test_returns_invalid_when_only_out_of_band_parasite_exists(void)
{
    static uint16_t buf[512];
    fill_sine(buf, 512, 10000u, 430.0f, 2048u, 800u);
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 700.0f, 0.0f);
    TEST_ASSERT_FALSE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, result.freq_hz);
    TEST_ASSERT_TRUE(result.candidate_hz > 0.0f);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW, result.invalid_reason);
}

static void test_returns_invalid_for_dc_window(void)
{
    static uint16_t buf[512];
    for (uint16_t i = 0; i < 512u; ++i) buf[i] = 2048u;
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f, 0.0f);
    TEST_ASSERT_FALSE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, result.freq_hz);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW, result.invalid_reason);
}

static void test_low_target_reports_target_low_reason(void)
{
    static uint16_t buf[512];
    fill_sine(buf, 512, 10000u, 40.0f, 2048u, 500u);
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 40.0f, 0.0f);
    TEST_ASSERT_FALSE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, result.freq_hz);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_TARGET_LOW, result.invalid_reason);
}

static void test_low_quality_candidate_is_still_returned(void)
{
    static uint16_t buf[512];
    fill_noisy_two_sines(buf, 512, 10000u, 300.0f, 350.0f, 340.0f, 500.0f, 100u);
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f, 0.0f);
    TEST_ASSERT_TRUE(result.peak_amp_lsb > BIBA_RPM_SPECTRAL_MIN_PEAK_AMP_LSB);
    TEST_ASSERT_TRUE(result.quality < BIBA_RPM_SPECTRAL_MIN_QUALITY);
    TEST_ASSERT_TRUE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(45.0f, 300.0f, result.freq_hz);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, result.candidate_hz, result.freq_hz);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_NONE, result.invalid_reason);
}

/* --- Phase 10: hint_hz dual-window tests --- */

/* Test 1: hint_hz=0.0f → sentinel, result identical to 4-arg behaviour (AC2) */
static void test_hint_zero_identical_to_no_hint(void)
{
    static uint16_t buf[512];
    fill_sine(buf, 512, 10000u, 300.0f, 2048u, 500u);
    biba_rpm_spectral_result_t r_no_hint = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f, 0.0f);
    biba_rpm_spectral_result_t r_hint    = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f, 0.0f);
    TEST_ASSERT_EQUAL(r_no_hint.valid, r_hint.valid);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, r_no_hint.freq_hz, r_hint.freq_hz);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_NONE, r_hint.invalid_reason);
}

/* Test 2: hint within deadband (|hint - target| <= 40 Hz) → only plant window fires (AC3) */
static void test_hint_within_deadband_uses_plant_window(void)
{
    static uint16_t buf[512];
    fill_sine(buf, 512, 10000u, 300.0f, 2048u, 500u);
    /* hint_hz = 320.0f, |320 - 300| = 20 Hz <= 40 Hz deadband → no second window */
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f, 320.0f);
    TEST_ASSERT_TRUE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(25.0f, 300.0f, result.freq_hz);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_NONE, result.invalid_reason);
}

/* Test 3: hint far from target, hint window has higher amp → HINT_MEASURED (AC3, AC4) */
static void test_hint_far_from_target_hint_wins(void)
{
    static uint16_t buf[512];
    /* Signal at 300 Hz. Plant target = 208 Hz → plant band ~[128, 288 Hz], misses 300 Hz.
     * hint = 300 Hz, |300 - 208| = 92 Hz > 40 Hz → second window fires and finds signal. */
    fill_sine(buf, 512, 10000u, 300.0f, 2048u, 500u);
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 208.0f, 300.0f);
    TEST_ASSERT_TRUE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(25.0f, 300.0f, result.freq_hz);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_HINT_MEASURED, result.invalid_reason);
}

/* Test 4: hint far from target, plant has higher amp → plant wins, reason=INVALID_NONE (AC4) */
static void test_hint_far_but_plant_wins_when_stronger(void)
{
    static uint16_t buf[512];
    /* Strong signal at 300 Hz. Target = 300 Hz (plant window directly on it).
     * hint = 500 Hz, |500 - 300| = 200 Hz > 40 Hz → hint window fires but finds nothing.
     * Plant should win. */
    fill_sine(buf, 512, 10000u, 300.0f, 2048u, 500u);
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f, 500.0f);
    TEST_ASSERT_TRUE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(25.0f, 300.0f, result.freq_hz);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_NONE, result.invalid_reason);
}

/* Test 5: both plant and hint windows below MIN_AMP → valid=false (regression guard) */
static void test_hint_both_below_min_amp_returns_invalid(void)
{
    static uint16_t buf[512];
    /* DC buffer: no AC signal → both windows return peak_low */
    for (uint16_t i = 0; i < 512u; ++i) buf[i] = 2048u;
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f, 500.0f);
    TEST_ASSERT_FALSE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, result.freq_hz);
}

/* Test 6: result.invalid_reason == HINT_MEASURED (=6), not INVALID_NONE (=0) (AC5 analog) */
static void test_hint_measured_reason_does_not_alias_none(void)
{
    static uint16_t buf[512];
    fill_sine(buf, 512, 10000u, 300.0f, 2048u, 500u);
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 208.0f, 300.0f);
    TEST_ASSERT_TRUE(result.valid);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_HINT_MEASURED, result.invalid_reason);
    /* HINT_MEASURED must be distinct from INVALID_NONE to prevent D8 circular feedback */
    TEST_ASSERT_NOT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_NONE, result.invalid_reason);
}

/* --- Phase 11: IS-pin DC load gate tests --- */

static void test_load_gate_rejects_high_ratio_low_quality(void)
{
    /* win3 analog: DC_L=2588, DC_R=1383, quality=3.7 → should be REJECTED */
    biba_rpm_spectral_result_t prim = {0};
    prim.mean_adc = 2588.0f; prim.quality = 3.7f; prim.valid = true;
    prim.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_NONE;
    biba_rpm_spectral_result_t sec = {0};
    sec.mean_adc = 1383.0f; sec.quality = 27.5f; sec.valid = true;
    sec.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_NONE;
    biba_rpm_spectral_apply_load_gate(&prim, &sec);
    TEST_ASSERT_FALSE(prim.valid);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD, prim.invalid_reason);
    /* secondary (free-running) should remain valid */
    TEST_ASSERT_TRUE(sec.valid);
}

static void test_load_gate_rejects_pre_latch(void)
{
    /* win18 analog: DC_L=3586, DC_R=1503, quality=9.4 → should be REJECTED */
    biba_rpm_spectral_result_t prim = {0};
    prim.mean_adc = 3586.0f; prim.quality = 9.4f; prim.valid = true;
    prim.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_NONE;
    biba_rpm_spectral_result_t sec = {0};
    sec.mean_adc = 1503.0f; sec.quality = 15.0f; sec.valid = true;
    sec.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_NONE;
    biba_rpm_spectral_apply_load_gate(&prim, &sec);
    TEST_ASSERT_FALSE(prim.valid);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD, prim.invalid_reason);
}

static void test_load_gate_keeps_light_load(void)
{
    /* win14 analog: DC_L=1139, DC_R=860, quality=11.1 → should be KEPT */
    biba_rpm_spectral_result_t prim = {0};
    prim.mean_adc = 1139.0f; prim.quality = 11.1f; prim.valid = true;
    prim.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_NONE;
    biba_rpm_spectral_result_t sec = {0};
    sec.mean_adc = 860.0f; sec.quality = 18.0f; sec.valid = true;
    sec.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_NONE;
    biba_rpm_spectral_apply_load_gate(&prim, &sec);
    TEST_ASSERT_TRUE(prim.valid);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_NONE, prim.invalid_reason);
}

static void test_load_gate_noop_when_both_invalid(void)
{
    /* Both channels already invalid → gate must not modify them */
    biba_rpm_spectral_result_t prim = {0};
    prim.mean_adc = 3800.0f; prim.quality = 0.0f; prim.valid = false;
    prim.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW;
    biba_rpm_spectral_result_t sec = {0};
    sec.mean_adc = 4000.0f; sec.quality = 0.0f; sec.valid = false;
    sec.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW;
    biba_rpm_spectral_apply_load_gate(&prim, &sec);
    TEST_ASSERT_FALSE(prim.valid);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW, prim.invalid_reason);
    TEST_ASSERT_FALSE(sec.valid);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW, sec.invalid_reason);
}

static void run_all(void)
{
    RUN_TEST(test_512_sample_sine_tracks_target);
    RUN_TEST(test_ignores_strong_out_of_band_parasite);
    RUN_TEST(test_returns_invalid_when_only_out_of_band_parasite_exists);
    RUN_TEST(test_returns_invalid_for_dc_window);
    RUN_TEST(test_low_target_reports_target_low_reason);
    RUN_TEST(test_low_quality_candidate_is_still_returned);
    /* --- Phase 10: hint_hz dual-window tests --- */
    RUN_TEST(test_hint_zero_identical_to_no_hint);
    RUN_TEST(test_hint_within_deadband_uses_plant_window);
    RUN_TEST(test_hint_far_from_target_hint_wins);
    RUN_TEST(test_hint_far_but_plant_wins_when_stronger);
    RUN_TEST(test_hint_both_below_min_amp_returns_invalid);
    RUN_TEST(test_hint_measured_reason_does_not_alias_none);
    /* --- Phase 11: load gate tests --- */
    RUN_TEST(test_load_gate_rejects_high_ratio_low_quality);
    RUN_TEST(test_load_gate_rejects_pre_latch);
    RUN_TEST(test_load_gate_keeps_light_load);
    RUN_TEST(test_load_gate_noop_when_both_invalid);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif