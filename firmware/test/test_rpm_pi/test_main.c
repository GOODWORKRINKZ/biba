/* Unity tests for firmware/src/app/rpm_pi.c (FF+PI RPM controller).
 *
 * Runs under both pio test -e native_test (full Unity runtime) and the
 * standalone gcc shim (BIBA_TEST_STANDALONE). */

#include <math.h>

#include "rpm_pi.h"
#include "biba_test_support.h"

static biba_rpm_pi_config_t make_default_cfg(void)
{
    biba_rpm_pi_config_t c = {
        .kp             = BIBA_RPM_PI_KP,
        .ki             = BIBA_RPM_PI_KI,
        .ki_low         = BIBA_RPM_PI_KI_LOW,
        .ki_low_thresh  = BIBA_RPM_PI_KI_LOW_THRESH,
        .ff_slope       = BIBA_RPM_PI_FF_SLOPE,
        .ff_dead        = BIBA_RPM_PI_FF_DEAD,
        .stiction_floor = BIBA_RPM_PI_STICTION,
        .p_clamp        = BIBA_RPM_PI_P_CLAMP,
        .dt_s           = BIBA_RPM_PI_DT_S,
    };
    return c;
}

/* --------------------------------------------------------------------- */

static void test_reset_zeroes_state(void)
{
    biba_rpm_pi_state_t s = {
        .integral = 9.0f, .meas_ema = 123.0f, .prev_duty = 0.5f, .primed = true,
    };
    biba_rpm_pi_reset(&s);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, s.integral);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, s.meas_ema);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, s.prev_duty);
    TEST_ASSERT_FALSE(s.primed);
}

static void test_ff_only_duty(void)
{
    /* Disable P and I; verify pure feed-forward output for target=400 Hz.
     * Expected: (400 + 74.6) / (10.13 * 100) ≈ 0.4685. */
    biba_rpm_pi_config_t cfg = make_default_cfg();
    cfg.kp = 0.0f;
    cfg.ki = 0.0f;
    cfg.ki_low = 0.0f;
    cfg.stiction_floor = 0.0f;

    biba_rpm_pi_state_t s;
    biba_rpm_pi_reset(&s);

    float duty = biba_rpm_pi_step(&s, &cfg, 400.0f, 0.0f);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.4685f, duty);
}

static void test_reverse_ff_only_returns_signed_duty(void)
{
    biba_rpm_pi_config_t cfg = make_default_cfg();
    cfg.kp = 0.0f;
    cfg.ki = 0.0f;
    cfg.ki_low = 0.0f;
    cfg.stiction_floor = 0.0f;

    biba_rpm_pi_state_t forward;
    biba_rpm_pi_state_t reverse;
    biba_rpm_pi_reset(&forward);
    biba_rpm_pi_reset(&reverse);

    float duty_forward = biba_rpm_pi_step(&forward, &cfg, 400.0f, 0.0f);
    float duty_reverse = biba_rpm_pi_step(&reverse, &cfg, -400.0f, 0.0f);

    TEST_ASSERT_FLOAT_WITHIN(1e-4f, duty_forward, -duty_reverse);
    TEST_ASSERT_TRUE(duty_reverse < 0.0f);
}

static void test_reverse_p_term_uses_signed_measurement(void)
{
    biba_rpm_pi_config_t cfg = make_default_cfg();
    cfg.kp = 0.001f;
    cfg.ki = 0.0f;
    cfg.ki_low = 0.0f;
    cfg.ff_slope = 0.0f;
    cfg.p_clamp = 0.05f;
    cfg.stiction_floor = 0.0f;

    biba_rpm_pi_state_t s;
    biba_rpm_pi_reset(&s);

    float duty = biba_rpm_pi_step(&s, &cfg, -300.0f, -250.0f);

    TEST_ASSERT_FLOAT_WITHIN(1e-4f, -0.05f, duty);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 175.0f, s.meas_ema);
}

static void test_gain_scheduling_below_200(void)
{
    /* At target < ki_low_thresh, the integrator clamp uses ki_low (0.005),
     * which yields i_clamp_pos = 0.03 / 0.005 = 6.0. Under regular ki
     * (0.010) the clamp would be 3.0. One step at target=150, meas_raw=150
     * gives err = 150 - (0.7*150) = 45 Hz, integral += 45*0.104 = 4.68 —
     * which fits inside the 6.0 ki_low clamp but would be cut to 3.0 by
     * the regular ki clamp. Catching integral ≈ 4.68 proves ki_low was
     * the active branch. */
    biba_rpm_pi_config_t cfg = make_default_cfg();
    cfg.kp = 0.0f;
    cfg.stiction_floor = 0.0f;
    cfg.p_clamp = 1.0f;

    biba_rpm_pi_state_t s;
    biba_rpm_pi_reset(&s);

    (void)biba_rpm_pi_step(&s, &cfg, 150.0f, 150.0f);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 4.68f, s.integral);
}

static void test_antiwindup_no_growth_at_saturation(void)
{
    /* prev_duty = 1.0 (saturated high); a positive error must NOT push the
     * integrator further into saturation. */
    biba_rpm_pi_config_t cfg = make_default_cfg();
    biba_rpm_pi_state_t s;
    biba_rpm_pi_reset(&s);
    s.prev_duty = 1.0f;

    const float before = s.integral;
    (void)biba_rpm_pi_step(&s, &cfg, 500.0f, 400.0f);
    const float after = s.integral;
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, before, after);
}

static void test_p_clamp_limits_p_term(void)
{
    /* With a huge kp, the raw P-term is enormous; the clamp must cap its
     * contribution to ±p_clamp. Disable FF and I so duty == p_term. */
    biba_rpm_pi_config_t cfg = make_default_cfg();
    cfg.kp = 1.0f;
    cfg.ki = 0.0f;
    cfg.ki_low = 0.0f;
    cfg.ff_slope = 0.0f;       /* disable FF                          */
    cfg.p_clamp = 0.05f;
    cfg.stiction_floor = 0.0f;

    biba_rpm_pi_state_t s;
    biba_rpm_pi_reset(&s);

    float duty = biba_rpm_pi_step(&s, &cfg, 100.0f, 80.0f);
    /* meas_ema = 0.7*80 = 56 (>50, P-term active). err = 44. p_term raw
     * = 44; must be clamped to 0.05. duty = 0 + 0.05 + 0 = 0.05. */
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 0.05f, duty);
}

static void test_stiction_floor_applied(void)
{
    /* Choose ff_slope so large that ff_duty rounds to a sub-stiction value;
     * the stiction floor must snap the output up to cfg.stiction_floor. */
    biba_rpm_pi_config_t cfg = make_default_cfg();
    cfg.kp = 0.0f;
    cfg.ki = 0.0f;
    cfg.ki_low = 0.0f;
    cfg.ff_slope = 10000.0f;     /* tiny ff_duty                      */
    cfg.stiction_floor = 0.20f;

    biba_rpm_pi_state_t s;
    biba_rpm_pi_reset(&s);

    float duty = biba_rpm_pi_step(&s, &cfg, 10.0f, 0.0f);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 0.20f, duty);
}

/* --------------------------------------------------------------------- */

static void run_all(void)
{
    RUN_TEST(test_reset_zeroes_state);
    RUN_TEST(test_ff_only_duty);
    RUN_TEST(test_reverse_ff_only_returns_signed_duty);
    RUN_TEST(test_reverse_p_term_uses_signed_measurement);
    RUN_TEST(test_gain_scheduling_below_200);
    RUN_TEST(test_antiwindup_no_growth_at_saturation);
    RUN_TEST(test_p_clamp_limits_p_term);
    RUN_TEST(test_stiction_floor_applied);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
