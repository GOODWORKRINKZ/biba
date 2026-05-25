#include <math.h>
#include <stdint.h>
#include <string.h>

#include "control_loop.h"
#include "failsafe.h"
#include "biba_test_support.h"

static biba_motor_current_t ok_sample(float amps)
{
    biba_motor_current_t s = { .current_a = amps, .valid = true };
    return s;
}

static biba_motor_current_t bad_sample(void)
{
    biba_motor_current_t s = { .current_a = 0.0f, .valid = false };
    return s;
}

static biba_motor_limit_t limit(float cur, float pwr, float vol)
{
    biba_motor_limit_t c = { .current_limit_a = cur,
                              .power_limit_w = pwr,
                              .supply_voltage_v = vol };
    return c;
}

static void test_clamp_unit_bounds(void)
{
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 1.0f, biba_clamp_unit(1.5f));
    TEST_ASSERT_FLOAT_WITHIN(1e-6, -1.0f, biba_clamp_unit(-2.0f));
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.3f, biba_clamp_unit(0.3f));
}

static void test_deadband_zeroes_stuck_neutral_input(void)
{
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.0f, biba_apply_deadband(0.19f, 0.20f));
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.0f, biba_apply_deadband(0.20f, 0.20f));
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.0f, biba_apply_deadband(-0.20f, 0.20f));
}

static void test_deadband_rescales_remaining_range_proportionally(void)
{
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.5f, biba_apply_deadband(0.60f, 0.20f));
    TEST_ASSERT_FLOAT_WITHIN(1e-6, -0.5f, biba_apply_deadband(-0.60f, 0.20f));
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 1.0f, biba_apply_deadband(1.0f, 0.20f));
}

static void test_limiter_passes_through_when_below_limits(void)
{
    biba_limit_result_t r = biba_apply_motor_limits(
        0.6f, -0.4f,
        ok_sample(5.0f), ok_sample(4.0f),
        limit(20.0f, 240.0f, 24.0f), limit(20.0f, 240.0f, 24.0f));
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.6f, r.left);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, -0.4f, r.right);
    TEST_ASSERT_FALSE(r.left_limited);
    TEST_ASSERT_FALSE(r.right_limited);
}

static void test_limiter_scales_each_motor_independently_by_current(void)
{
    biba_limit_result_t r = biba_apply_motor_limits(
        0.8f, 0.7f,
        ok_sample(24.0f), ok_sample(10.0f),
        limit(12.0f, 400.0f, 24.0f), limit(12.0f, 400.0f, 24.0f));
    TEST_ASSERT_FLOAT_WITHIN(1e-5, 0.4f, r.left);   /* 0.8 * (12/24) */
    TEST_ASSERT_FLOAT_WITHIN(1e-5, 0.7f, r.right);
    TEST_ASSERT_TRUE(r.left_limited);
    TEST_ASSERT_FALSE(r.right_limited);
}

static void test_limiter_scales_by_power_using_supply_voltage(void)
{
    /* Mirror test_current_control.py::test_apply_motor_limits_scales_by_power */
    biba_limit_result_t r = biba_apply_motor_limits(
        -0.9f, 0.2f,
        ok_sample(10.0f), ok_sample(3.0f),
        limit(30.0f, 120.0f, 30.0f), limit(30.0f, 120.0f, 30.0f));
    TEST_ASSERT_FLOAT_WITHIN(1e-4, -0.36f, r.left); /* -0.9 * (120 / 300) */
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.2f, r.right);
    TEST_ASSERT_TRUE(r.left_limited);
    TEST_ASSERT_FALSE(r.right_limited);
}

static void test_limiter_fails_open_when_sample_invalid(void)
{
    biba_limit_result_t r = biba_apply_motor_limits(
        0.9f, -0.9f,
        bad_sample(), bad_sample(),
        limit(5.0f, 50.0f, 24.0f), limit(5.0f, 50.0f, 24.0f));
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.9f, r.left);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, -0.9f, r.right);
    TEST_ASSERT_FALSE(r.left_limited);
    TEST_ASSERT_FALSE(r.right_limited);
}

static void test_pid_applies_proportional_term(void)
{
    biba_pid_config_t cfg = { .kp = 0.5f, .ki = 0.0f, .kd = 0.0f,
                              .output_limit = 1.0f, .integral_limit = 1.0f };
    biba_pid_state_t state;
    biba_pid_reset(&state);
    float out = biba_pid_step(&state, &cfg, 0.4f, 0.01f);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.2f, out);
}

static void test_pid_clamps_output(void)
{
    biba_pid_config_t cfg = { .kp = 10.0f, .ki = 0.0f, .kd = 0.0f,
                              .output_limit = 0.5f, .integral_limit = 1.0f };
    biba_pid_state_t state;
    biba_pid_reset(&state);
    float out = biba_pid_step(&state, &cfg, 10.0f, 0.01f);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.5f, out);
    out = biba_pid_step(&state, &cfg, -10.0f, 0.01f);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, -0.5f, out);
}

static void test_pid_integral_anti_windup(void)
{
    biba_pid_config_t cfg = { .kp = 0.0f, .ki = 1.0f, .kd = 0.0f,
                              .output_limit = 10.0f, .integral_limit = 0.25f };
    biba_pid_state_t state;
    biba_pid_reset(&state);
    for (int i = 0; i < 100; ++i) {
        biba_pid_step(&state, &cfg, 1.0f, 0.01f); /* would integrate to 1.0 */
    }
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.25f, state.integral);
}

static void test_pid_reset_clears_state(void)
{
    biba_pid_config_t cfg = { .kp = 0.5f, .ki = 1.0f, .kd = 0.0f,
                              .output_limit = 1.0f, .integral_limit = 5.0f };
    biba_pid_state_t state;
    biba_pid_reset(&state);
    biba_pid_step(&state, &cfg, 0.5f, 0.02f);
    TEST_ASSERT_TRUE(state.primed);
    biba_pid_reset(&state);
    TEST_ASSERT_FALSE(state.primed);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.0f, state.integral);
}

static void test_mixer_splits_throttle_and_steer(void)
{
    biba_mix_output_t m = biba_mix_differential(0.5f, 0.2f);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.7f, m.left);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.3f, m.right);
    m = biba_mix_differential(0.8f, -0.3f);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.5f, m.left);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 1.0f, m.right);
}

static void test_mixer_clamps_to_unit(void)
{
    biba_mix_output_t m = biba_mix_differential(0.9f, 0.5f);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 1.0f, m.left);
    TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.4f, m.right);
}

static void test_failsafe_starts_active_until_first_frame(void)
{
    biba_failsafe_t fs;
    biba_failsafe_init(&fs, 200);
    TEST_ASSERT_TRUE(biba_failsafe_is_active(&fs));
    TEST_ASSERT_TRUE(biba_failsafe_tick(&fs, 50));
}

static void test_failsafe_clears_on_fresh_frame(void)
{
    biba_failsafe_t fs;
    biba_failsafe_init(&fs, 200);
    biba_failsafe_mark_fresh(&fs, 100);
    TEST_ASSERT_FALSE(biba_failsafe_is_active(&fs));
    TEST_ASSERT_FALSE(biba_failsafe_tick(&fs, 250));   /* 150 ms since fresh */
}

static void test_failsafe_reactivates_after_timeout(void)
{
    biba_failsafe_t fs;
    biba_failsafe_init(&fs, 200);
    biba_failsafe_mark_fresh(&fs, 100);
    TEST_ASSERT_TRUE(biba_failsafe_tick(&fs, 301));   /* 201 ms since fresh */
    TEST_ASSERT_TRUE(biba_failsafe_is_active(&fs));
    biba_failsafe_mark_fresh(&fs, 400);
    TEST_ASSERT_FALSE(biba_failsafe_is_active(&fs));
}

static void run_all(void)
{
    RUN_TEST(test_clamp_unit_bounds);
    RUN_TEST(test_deadband_zeroes_stuck_neutral_input);
    RUN_TEST(test_deadband_rescales_remaining_range_proportionally);
    RUN_TEST(test_limiter_passes_through_when_below_limits);
    RUN_TEST(test_limiter_scales_each_motor_independently_by_current);
    RUN_TEST(test_limiter_scales_by_power_using_supply_voltage);
    RUN_TEST(test_limiter_fails_open_when_sample_invalid);
    RUN_TEST(test_pid_applies_proportional_term);
    RUN_TEST(test_pid_clamps_output);
    RUN_TEST(test_pid_integral_anti_windup);
    RUN_TEST(test_pid_reset_clears_state);
    RUN_TEST(test_mixer_splits_throttle_and_steer);
    RUN_TEST(test_mixer_clamps_to_unit);
    RUN_TEST(test_failsafe_starts_active_until_first_frame);
    RUN_TEST(test_failsafe_clears_on_fresh_frame);
    RUN_TEST(test_failsafe_reactivates_after_timeout);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
