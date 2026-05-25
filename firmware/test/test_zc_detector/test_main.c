/* Unity tests for the portable A2 Sub-window Schmitt ZC detector
 * (firmware/src/app/zc_detector.c). Runs under both pio test -e native_test
 * and the standalone gcc shim (BIBA_TEST_STANDALONE). */

#include <math.h>
#include <stdint.h>
#include <stdbool.h>

#include "zc_detector.h"
#include "biba_test_support.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* Fill buf with `n` samples of a 12-bit-DC-centered sine wave at `freq_hz`,
 * sampled at `sps`. dc is the midline (e.g. 2048), amp is peak amplitude
 * in ADC LSBs. Clamped to [0, 4095]. */
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

/* -----------------------------------------------------------------------
 * Test 1: 300 Hz sine at 10 kSPS → within ±15 Hz of 300
 * ----------------------------------------------------------------------- */
static void test_pure_sine_300hz(void)
{
    static uint16_t buf[1024];
    fill_sine(buf, 1024, 10000u, 300.0f, 2048, 800);
    float hz = zc_freq_hz(buf, 1024, 10000u);
    TEST_ASSERT_FLOAT_WITHIN(15.0f, 300.0f, hz);
}

/* -----------------------------------------------------------------------
 * Test 2: 500 Hz sine at 10 kSPS → within ±25 Hz of 500
 * ----------------------------------------------------------------------- */
static void test_pure_sine_500hz(void)
{
    static uint16_t buf[1024];
    fill_sine(buf, 1024, 10000u, 500.0f, 2048, 800);
    float hz = zc_freq_hz(buf, 1024, 10000u);
    TEST_ASSERT_FLOAT_WITHIN(25.0f, 500.0f, hz);
}

static void test_analyze_matches_frequency_api(void)
{
    static uint16_t buf[1024];
    fill_sine(buf, 1024, 10000u, 300.0f, 2048, 800);
    float hz = zc_freq_hz(buf, 1024, 10000u);
    zc_detector_result_t result = zc_freq_analyze(buf, 1024, 10000u);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, hz, result.freq_hz);
    TEST_ASSERT_GREATER_OR_EQUAL_UINT16(2u, result.active_blocks);
    TEST_ASSERT_GREATER_OR_EQUAL_UINT16(2u, result.total_crossings);
    TEST_ASSERT_GREATER_THAN_UINT16(ZC_SUBWIN_MIN_PKPK, result.max_pkpk);
    TEST_ASSERT_TRUE(result.max_std >= ZC_SUBWIN_MIN_STD);
}

/* -----------------------------------------------------------------------
 * Test 3: DC-only buffer → 0.0f (no active blocks)
 * ----------------------------------------------------------------------- */
static void test_dc_only_returns_zero(void)
{
    static uint16_t buf[1024];
    for (uint16_t i = 0; i < 1024; ++i) buf[i] = 2048;
    float hz = zc_freq_hz(buf, 1024, 10000u);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, hz);
}

/* -----------------------------------------------------------------------
 * Test 4: Sparse switching spikes can have high pkpk, but low per-block
 * std-dev.  They are PWM/EMI evidence, not wheel rotation.
 * ----------------------------------------------------------------------- */
static void test_sparse_switching_noise_returns_zero(void)
{
    static uint16_t buf[1024];
    for (uint16_t i = 0; i < 1024; ++i) {
        buf[i] = (i % 64u == 0u) ? 2190u : 2048u;
    }
    float hz = zc_freq_hz(buf, 1024, 10000u);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, hz);
}

/* -----------------------------------------------------------------------
 * Test 5: Too-short input (n < ZC_SUBWIN_K * 4 = 32) → 0.0f
 * ----------------------------------------------------------------------- */
static void test_too_short_returns_zero(void)
{
    uint16_t buf[16];
    for (uint16_t i = 0; i < 16; ++i) buf[i] = (uint16_t)(2048 + (i % 2 ? 500 : -500));
    float hz = zc_freq_hz(buf, 16, 10000u);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, hz);
}

/* -----------------------------------------------------------------------
 * Test 6: EMA update on a valid in-range reading
 * meas_raw=300, ema=0, target=300 → alpha=0.7 → 0.7*300 + 0.3*0 = 210
 * ----------------------------------------------------------------------- */
static void test_ema_update_valid_range(void)
{
    float ema = 0.0f;
    float out = zc_ema_update(&ema, 300.0f, 300.0f);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 210.0f, out);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 210.0f, ema);
}

/* -----------------------------------------------------------------------
 * Runner
 * ----------------------------------------------------------------------- */
static void run_all(void)
{
    RUN_TEST(test_pure_sine_300hz);
    RUN_TEST(test_pure_sine_500hz);
    RUN_TEST(test_analyze_matches_frequency_api);
    RUN_TEST(test_dc_only_returns_zero);
    RUN_TEST(test_sparse_switching_noise_returns_zero);
    RUN_TEST(test_too_short_returns_zero);
    RUN_TEST(test_ema_update_valid_range);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
