#include <stdbool.h>
#include <stdint.h>

#include "ramp.h"
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
 * REVERSE_DECEL_RATE=0.5, current=0.5, target=-1.0, dt=0.1 → step=0.05 → 0.45f
 * (accel would give 0.3f, decel would give 0.4f — wrong)
 * ----------------------------------------------------------------------- */
static void test_direction_change_uses_reverse_decel_rate(void)
{
    biba_ramp_t r;
    biba_ramp_init(&r);
    r.current = 0.5f;
    float out = biba_ramp_update(&r, -1.0f, 0.1f);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.45f, out);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.45f, r.current);
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
    /* hold_remaining_s = 150ms = 0.15f */
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 0.15f, r.hold_remaining_s);

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
 * Runner
 * ----------------------------------------------------------------------- */
static void run_all(void)
{
    RUN_TEST(test_init_starts_at_zero);
    RUN_TEST(test_reset_zeroes_running_state);
    RUN_TEST(test_dt_zero_returns_current_unchanged);
    RUN_TEST(test_acceleration_toward_positive_target);
    RUN_TEST(test_deceleration_from_positive);
    RUN_TEST(test_direction_change_uses_reverse_decel_rate);
    RUN_TEST(test_direction_change_triggers_zero_hold);
    RUN_TEST(test_clamp_output_to_unit);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
