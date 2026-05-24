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
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f);
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
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f);
    TEST_ASSERT_TRUE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(35.0f, 300.0f, result.freq_hz);
}

static void test_returns_invalid_when_only_out_of_band_parasite_exists(void)
{
    static uint16_t buf[512];
    fill_sine(buf, 512, 10000u, 430.0f, 2048u, 800u);
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 700.0f);
    TEST_ASSERT_FALSE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, result.freq_hz);
    TEST_ASSERT_TRUE(result.candidate_hz > 0.0f);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW, result.invalid_reason);
}

static void test_returns_invalid_for_dc_window(void)
{
    static uint16_t buf[512];
    for (uint16_t i = 0; i < 512u; ++i) buf[i] = 2048u;
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f);
    TEST_ASSERT_FALSE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, result.freq_hz);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW, result.invalid_reason);
}

static void test_low_target_reports_target_low_reason(void)
{
    static uint16_t buf[512];
    fill_sine(buf, 512, 10000u, 60.0f, 2048u, 500u);
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 60.0f);
    TEST_ASSERT_FALSE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, result.freq_hz);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_TARGET_LOW, result.invalid_reason);
}

static void test_low_quality_candidate_is_still_returned(void)
{
    static uint16_t buf[512];
    fill_noisy_two_sines(buf, 512, 10000u, 300.0f, 350.0f, 340.0f, 500.0f, 100u);
    biba_rpm_spectral_result_t result = biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f);
    TEST_ASSERT_TRUE(result.peak_amp_lsb > BIBA_RPM_SPECTRAL_MIN_PEAK_AMP_LSB);
    TEST_ASSERT_TRUE(result.quality < BIBA_RPM_SPECTRAL_MIN_QUALITY);
    TEST_ASSERT_TRUE(result.valid);
    TEST_ASSERT_FLOAT_WITHIN(45.0f, 300.0f, result.freq_hz);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, result.candidate_hz, result.freq_hz);
    TEST_ASSERT_EQUAL(BIBA_RPM_SPECTRAL_INVALID_NONE, result.invalid_reason);
}

static void run_all(void)
{
    RUN_TEST(test_512_sample_sine_tracks_target);
    RUN_TEST(test_ignores_strong_out_of_band_parasite);
    RUN_TEST(test_returns_invalid_when_only_out_of_band_parasite_exists);
    RUN_TEST(test_returns_invalid_for_dc_window);
    RUN_TEST(test_low_target_reports_target_low_reason);
    RUN_TEST(test_low_quality_candidate_is_still_returned);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif