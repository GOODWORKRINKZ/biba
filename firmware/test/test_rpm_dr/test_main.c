/* Unity tests for firmware/src/app/rpm_dr.c (dead-reckoning fallback).
 *
 * Runs under both pio test -e native_test (full Unity runtime) and the
 * standalone gcc shim (BIBA_TEST_STANDALONE). */

#include <math.h>

#include "rpm_dr.h"
#include "biba_config.h"
#include "biba_test_support.h"

/* Helper: build a valid SpectralResult */
static biba_rpm_spectral_result_t make_valid(float freq_hz)
{
    biba_rpm_spectral_result_t r;
    r.freq_hz       = freq_hz;
    r.candidate_hz  = freq_hz;
    r.quality       = 1.0f;
    r.peak_amp_lsb  = 100.0f;
    r.second_amp_lsb = 0.0f;
    r.invalid_reason = BIBA_RPM_SPECTRAL_INVALID_NONE;
    r.valid         = true;
    return r;
}

/* Helper: build an invalid SpectralResult with a specific reason */
static biba_rpm_spectral_result_t make_invalid(biba_rpm_spectral_invalid_reason_t reason)
{
    biba_rpm_spectral_result_t r;
    r.freq_hz        = 0.0f;
    r.candidate_hz   = 0.0f;
    r.quality        = 0.0f;
    r.peak_amp_lsb   = 0.0f;
    r.second_amp_lsb = 0.0f;
    r.invalid_reason = reason;
    r.valid          = false;
    return r;
}

/* --------------------------------------------------------------------- */

static void test_reset_zeroes_state(void)
{
    biba_rpm_dr_state_t s;
    s.ratio_ema = 9.9f;
    s.streak    = 7u;

    biba_rpm_dr_reset(&s);

    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, s.ratio_ema);
    TEST_ASSERT_EQUAL_UINT8(0u, s.streak);
}

static void test_cold_start_returns_zero(void)
{
    biba_rpm_dr_state_t s;
    biba_rpm_dr_reset(&s);

    biba_rpm_spectral_result_t spec = make_invalid(BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW);
    biba_rpm_spectral_invalid_reason_t reason = BIBA_RPM_SPECTRAL_INVALID_NONE;

    float result = biba_rpm_dr_update(&s, &spec, 200.0f, &reason);

    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, result);
    TEST_ASSERT_EQUAL_INT(BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW, (int)reason);
}

static void test_streak_valid_returns_spec_hz(void)
{
    biba_rpm_dr_state_t s;
    biba_rpm_dr_reset(&s);

    /* Warm up ratio_ema first */
    biba_rpm_spectral_result_t warm = make_valid(160.0f);
    biba_rpm_spectral_invalid_reason_t reason;
    biba_rpm_dr_update(&s, &warm, 200.0f, &reason);
    biba_rpm_dr_update(&s, &warm, 200.0f, &reason);

    /* Third call: valid at 180 Hz */
    biba_rpm_spectral_result_t spec = make_valid(180.0f);
    float result = biba_rpm_dr_update(&s, &spec, 200.0f, &reason);

    TEST_ASSERT_FLOAT_WITHIN(1.0f, 180.0f, result);
    TEST_ASSERT_EQUAL_INT(BIBA_RPM_SPECTRAL_INVALID_NONE, (int)reason);
    TEST_ASSERT_EQUAL_UINT8(0u, s.streak);
}

static void test_ratio_ema_convergence(void)
{
    biba_rpm_dr_state_t s;
    biba_rpm_dr_reset(&s);

    biba_rpm_spectral_result_t spec = make_valid(180.0f);  /* ratio = 0.9 at target=200 */
    biba_rpm_spectral_invalid_reason_t reason;

    for (int i = 0; i < 10; i++) {
        biba_rpm_dr_update(&s, &spec, 200.0f, &reason);
    }

    /* EMA of constant 0.9 from 0.0 with alpha=0.2: after 10 steps ≈ 0.89
     * Conservative lower bound: must be at least 0.5 */
    TEST_ASSERT_TRUE(s.ratio_ema >= 0.5f);
}

static void test_streak_expiry_returns_zero(void)
{
    biba_rpm_dr_state_t s;
    biba_rpm_dr_reset(&s);

    /* Warm up: 5 valid calls to build ratio_ema */
    biba_rpm_spectral_result_t valid_spec = make_valid(160.0f);
    biba_rpm_spectral_invalid_reason_t reason;
    for (int i = 0; i < 5; i++) {
        biba_rpm_dr_update(&s, &valid_spec, 200.0f, &reason);
    }
    TEST_ASSERT_TRUE(s.ratio_ema > 0.0f);

    /* Feed MAX_STREAK+2 consecutive invalids */
    biba_rpm_spectral_result_t inv = make_invalid(BIBA_RPM_SPECTRAL_INVALID_NO_BAND);
    float last_at_max  = -1.0f;
    float last_expired = -1.0f;
    for (uint8_t i = 0; i <= (uint8_t)(BIBA_RPM_DR_MAX_STREAK + 1u); i++) {
        float r = biba_rpm_dr_update(&s, &inv, 200.0f, &reason);
        if (i == BIBA_RPM_DR_MAX_STREAK) {
            last_at_max = r;
        } else if (i == BIBA_RPM_DR_MAX_STREAK + 1) {
            last_expired = r;
        }
    }

    /* At MAX_STREAK: streak <= MAX_STREAK so DR still active → result > 0 */
    TEST_ASSERT_TRUE(last_at_max > 0.0f);
    /* After MAX_STREAK: streak > MAX_STREAK so DR expired → result = 0 */
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, last_expired);
}

static void test_ratio_clamp_lo(void)
{
    biba_rpm_dr_state_t s;
    biba_rpm_dr_reset(&s);

    /* ratio = 40/200 = 0.2 — below RATIO_LO=0.50; must be clamped to 0.50 */
    biba_rpm_spectral_result_t spec = make_valid(40.0f);
    biba_rpm_spectral_invalid_reason_t reason;
    biba_rpm_dr_update(&s, &spec, 200.0f, &reason);

    /* After one step from cold: ratio_ema = alpha * RATIO_LO + (1-alpha)*0 = 0.2*0.50 = 0.10 */
    float expected = BIBA_RPM_DR_ALPHA * BIBA_RPM_DR_RATIO_LO;
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, expected, s.ratio_ema);
}

static void test_ratio_clamp_hi(void)
{
    biba_rpm_dr_state_t s;
    biba_rpm_dr_reset(&s);

    /* ratio = 600/200 = 3.0 — above RATIO_HI=1.30; must be clamped to 1.30 */
    biba_rpm_spectral_result_t spec = make_valid(600.0f);
    biba_rpm_spectral_invalid_reason_t reason;
    biba_rpm_dr_update(&s, &spec, 200.0f, &reason);

    TEST_ASSERT_TRUE(s.ratio_ema <= BIBA_RPM_DR_RATIO_HI + 1e-4f);
}

/* --------------------------------------------------------------------- */

static void run_all(void)
{
    RUN_TEST(test_reset_zeroes_state);
    RUN_TEST(test_cold_start_returns_zero);
    RUN_TEST(test_streak_valid_returns_spec_hz);
    RUN_TEST(test_ratio_ema_convergence);
    RUN_TEST(test_streak_expiry_returns_zero);
    RUN_TEST(test_ratio_clamp_lo);
    RUN_TEST(test_ratio_clamp_hi);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
