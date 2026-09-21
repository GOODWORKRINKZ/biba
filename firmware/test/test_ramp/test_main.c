#include <stdbool.h>
#include <stdint.h>

#include "ramp.h"
#include "biba_config.h"
#include "biba_test_support.h"

/* -----------------------------------------------------------------------
 * Test 1: biba_ramp_init starts at zero
 * ----------------------------------------------------------------------- */
static void test_init_starts_at_zero(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, r.current);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, r.hold_remaining_s);
}

/* -----------------------------------------------------------------------
 * Test 2: biba_ramp_reset zeroes running state
 * ----------------------------------------------------------------------- */
static void test_reset_zeroes_running_state(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);
    /* Advance current to ~0.4f */
    biba_ramp_update(&r, 1.0f, 0.2f);  /* 2.0 * 0.2 = 0.4 */
    biba_ramp_reset(&r);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, r.current);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, r.hold_remaining_s);
}

/* -----------------------------------------------------------------------
 * Test 3: dt <= 0 guard returns current unchanged (Pitfall 1)
 * ----------------------------------------------------------------------- */
static void test_dt_zero_returns_current_unchanged(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);
    r.current = 0.5f;
    float out = biba_ramp_update(&r, 1.0f, 0.0f);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.5f, out);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.5f, r.current);
}

/* -----------------------------------------------------------------------
 * Test 4: Acceleration toward positive target
 * ACCEL_RATE=2.0, dt=0.1 → step=0.2, expected=0.2f from current=0
 * ----------------------------------------------------------------------- */
static void test_acceleration_toward_positive_target(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);
    float out = biba_ramp_update(&r, 1.0f, 0.1f);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.2f, out);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.2f, r.current);
}

static void test_custom_accel_rate_limits_soft_start(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);

    float out = biba_ramp_update_with_rates(&r, 1.0f, 0.1f,
                                            0.6f, 2.0f, 0.5f, 150u);

    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.06f, out);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.06f, r.current);
}

/* -----------------------------------------------------------------------
 * Test 5: Deceleration from positive current
 * DECEL_RATE=2.0, current=1.0, target=0, dt=0.1 → step=0.2 → 0.8f
 * ----------------------------------------------------------------------- */
static void test_deceleration_from_positive(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);
    r.current = 1.0f;
    float out = biba_ramp_update(&r, 0.0f, 0.1f);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.8f, out);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.8f, r.current);
}

/* -----------------------------------------------------------------------
 * Test 6: Direction change uses REVERSE_DECEL_RATE, not accel/decel rate
 * Derived from the config so a retune does not need a test edit; the rates
 * are distinct enough that accel/decel would give a different answer.
 * ----------------------------------------------------------------------- */
static void test_direction_change_uses_reverse_decel_rate(void)
{
    /* Explicit rates: reverse 0.5, distinct from accel 2.0 and decel 3.0,
     * so only the reversal branch can produce this answer. */
    biba_ramp_t r;
    biba_ramp_init(&r);
    r.current = 0.5f;
    float out = biba_ramp_update_with_rates(&r, -1.0f, 0.1f,
                                            2.0f, 3.0f, 0.5f, 150u);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.45f, out);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.45f, r.current);
}

/* -----------------------------------------------------------------------
 * Test 6a: reverse_decel_rate <= 0 means "no reversal slew limit" — the
 * output lands on zero in a single tick from any duty.
 * ----------------------------------------------------------------------- */
static void test_zero_reverse_rate_crosses_immediately(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);
    r.current = 1.0f;
    float out = biba_ramp_update_with_rates(&r, -1.0f, 0.002f,
                                            2.0f, 2.0f, 0.0f, 0u);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, out);

    out = biba_ramp_update_with_rates(&r, -1.0f, 0.002f,
                                      2.0f, 2.0f, 0.0f, 0u);
    TEST_ASSERT_TRUE(out < 0.0f);
}

/* -----------------------------------------------------------------------
 * Test 6b: The reversal path is not slower than plain deceleration.
 * Regression guard for the 2026-09-20 field report: REVERSE_DECEL_RATE used
 * to be 4x slower than DECEL_RATE, so a wheel asked to flip sign sat at the
 * old duty for seconds while the other wheel kept pulling the robot around.
 * ----------------------------------------------------------------------- */
static void test_reverse_is_not_slower_than_decel(void)
{
    TEST_ASSERT_TRUE(BIBA_RAMP_REVERSE_DECEL_RATE >= BIBA_RAMP_DECEL_RATE);
}

/* -----------------------------------------------------------------------
 * Test 6c: Steering through a reversal never costs more than stopping and
 * driving off again.  Regression guard for the 2026-09-20 field report,
 * where REVERSE_DECEL_RATE was half DECEL_RATE and the hold was 400 ms, so
 * a wheel asked to flip sign sat at the old duty for seconds while the
 * other wheel kept pulling the robot around.
 * Budget is derived, so a retune needs no test edit.
 * ----------------------------------------------------------------------- */
static void test_full_reversal_latency_within_budget(void)
{
    const float dt     = 1.0f / (float)BIBA_CONTROL_LOOP_HZ;
    /* full duty down to zero at the ordinary decel rate, plus the hold,
     * plus a couple of ticks of slack for the discrete stepping. */
    const float budget = 1.0f / BIBA_RAMP_DECEL_RATE
                       + (float)BIBA_RAMP_ZERO_HOLD_MS / 1000.0f
                       + 2.0f * dt;
    biba_ramp_t r;
    biba_ramp_init(&r);
    r.current  = 1.0f;
    r.last_dir = 1;

    float elapsed = 0.0f;
    while (elapsed <= budget) {
        float out = biba_ramp_update(&r, -1.0f, dt);
        elapsed += dt;
        if (out < 0.0f) break;
    }
    TEST_ASSERT_TRUE(r.current < 0.0f);
    TEST_ASSERT_TRUE(elapsed <= budget);
}

/* -----------------------------------------------------------------------
 * Test 7: Direction change triggers zero-hold and hold freezes output
 * current=0.1, target=-1.0, dt=1.0 → large step → reaches zero → hold set
 * Second call with dt=0.05 (during hold): returns 0.0 (frozen)
 * ----------------------------------------------------------------------- */
static void test_direction_change_triggers_zero_hold(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);
    r.current = 0.1f;
    /* Large dt forces current to reach zero, hold timer should arm */
    float out = biba_ramp_update(&r, -1.0f, 1.0f);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.0f, out);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f,
                             (float)BIBA_RAMP_ZERO_HOLD_MS / 1000.0f,
                             r.hold_remaining_s);

    /* Tick during hold: output must remain frozen at 0.0 */
    float out2 = biba_ramp_update(&r, -1.0f, 0.05f);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.0f, out2);
}

/* -----------------------------------------------------------------------
 * Test 8: Output is clamped to [-1.0, 1.0]
 * current=0.9, target=1.0, dt=10.0 (enormous step) → must clamp at 1.0
 * current=-0.9, target=-1.0, dt=10.0 → must clamp at -1.0
 * ----------------------------------------------------------------------- */
static void test_clamp_output_to_unit(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);

    r.current = 0.9f;
    float pos = biba_ramp_update(&r, 1.0f, 10.0f);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 1.0f, pos);

    biba_ramp_init(&r);
    r.current = -0.9f;
    float neg = biba_ramp_update(&r, -1.0f, 10.0f);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, -1.0f, neg);
}

/* -----------------------------------------------------------------------
 * Test 9: Reversal through a centred stick still waits the zero hold
 * current=1.0 → target 0 (reaches zero), then target -1:
 * held at 0 until ZERO_HOLD_MS has passed since the output reached zero.
 * ----------------------------------------------------------------------- */
static void test_reversal_through_zero_waits_hold(void)
{
    const float hold_s = (float)BIBA_RAMP_ZERO_HOLD_MS / 1000.0f;
    const float step   = hold_s * 0.6f;
    biba_ramp_t r;
    biba_ramp_init(&r);
    r.current = 1.0f;

    float out = biba_ramp_update(&r, 0.0f, 10.0f);          /* to rest */
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, out);

    out = biba_ramp_update(&r, -1.0f, step);                /* 0.6 hold */
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, out);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, hold_s - step, r.hold_remaining_s);

    out = biba_ramp_update(&r, -1.0f, step);                /* 1.2 hold */
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, -BIBA_RAMP_ACCEL_RATE * step, out);
}

/* -----------------------------------------------------------------------
 * Test 10: After resting at zero longer than the hold, reversal is immediate
 * ----------------------------------------------------------------------- */
static void test_reversal_after_long_rest_is_immediate(void)
{
    const float hold_s = (float)BIBA_RAMP_ZERO_HOLD_MS / 1000.0f;
    biba_ramp_t r;
    biba_ramp_init(&r);
    r.current = 1.0f;

    (void)biba_ramp_update(&r, 0.0f, 10.0f);                /* to rest */
    (void)biba_ramp_update(&r, 0.0f, hold_s * 2.0f);        /* rest */
    float out = biba_ramp_update(&r, -1.0f, 0.01f);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, -BIBA_RAMP_ACCEL_RATE * 0.01f, out);
}

/* -----------------------------------------------------------------------
 * Test 11: Restarting in the same direction after a stop has no hold
 * ----------------------------------------------------------------------- */
static void test_same_direction_restart_has_no_hold(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);
    r.current = 1.0f;

    (void)biba_ramp_update(&r, 0.0f, 10.0f);                /* to rest */
    float out = biba_ramp_update(&r, 1.0f, 0.01f);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, BIBA_RAMP_ACCEL_RATE * 0.01f, out);
}

/* -----------------------------------------------------------------------
 * Test 12: A hard reset while moving still enforces the hold on reversal
 * ----------------------------------------------------------------------- */
static void test_reset_while_moving_keeps_direction_for_hold(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);
    r.current = 0.8f;
    (void)biba_ramp_update(&r, 0.8f, 0.01f);                /* record direction */

    biba_ramp_reset(&r);
    float out = biba_ramp_update(&r, -1.0f, 0.01f);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, out);
    TEST_ASSERT_TRUE(r.hold_remaining_s > 0.0f);
}

/* -----------------------------------------------------------------------
 * Runner
 * ----------------------------------------------------------------------- */
static void run_all(void)
{
    RUN_TEST(test_init_starts_at_zero);
    RUN_TEST(test_reset_zeroes_running_state);
    RUN_TEST(test_dt_zero_returns_current_unchanged);
    RUN_TEST(test_acceleration_toward_positive_target);
    RUN_TEST(test_custom_accel_rate_limits_soft_start);
    RUN_TEST(test_deceleration_from_positive);
    RUN_TEST(test_direction_change_uses_reverse_decel_rate);
    RUN_TEST(test_zero_reverse_rate_crosses_immediately);
    RUN_TEST(test_reverse_is_not_slower_than_decel);
    RUN_TEST(test_full_reversal_latency_within_budget);
    RUN_TEST(test_direction_change_triggers_zero_hold);
    RUN_TEST(test_clamp_output_to_unit);
    RUN_TEST(test_reversal_through_zero_waits_hold);
    RUN_TEST(test_reversal_after_long_rest_is_immediate);
    RUN_TEST(test_same_direction_restart_has_no_hold);
    RUN_TEST(test_reset_while_moving_keeps_direction_for_hold);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
