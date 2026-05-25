#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "biba_config.h"
#include "biba_test_support.h"
#include "app/motor_bridge.h"

/* Native test env excludes drivers/, so pull the portable implementation
 * into this test binary explicitly. */
#include "../../src/drivers/bts7960.c"

enum {
    EVT_PWM_LEFT_ZERO = 1,
    EVT_PWM_RIGHT_ZERO,
    EVT_LEFT_ENABLE_LOW,
    EVT_RIGHT_ENABLE_LOW,
    EVT_DELAY_US,
    EVT_LEFT_ENABLE_HIGH,
    EVT_RIGHT_ENABLE_HIGH,
    EVT_SSR_HIGH,
};

static int s_events[16];
static int s_event_count;
static uint32_t s_last_delay_us;

static void record_event(int evt)
{
    if (s_event_count < (int)(sizeof(s_events) / sizeof(s_events[0]))) {
        s_events[s_event_count++] = evt;
    }
}

void biba_hal_motor_pwm_left(float duty)
{
    if (duty == 0.0f) {
        record_event(EVT_PWM_LEFT_ZERO);
    }
}

void biba_hal_motor_pwm_right(float duty)
{
    if (duty == 0.0f) {
        record_event(EVT_PWM_RIGHT_ZERO);
    }
}

void biba_hal_left_enable(bool enabled)
{
    record_event(enabled ? EVT_LEFT_ENABLE_HIGH : EVT_LEFT_ENABLE_LOW);
}

void biba_hal_right_enable(bool enabled)
{
    record_event(enabled ? EVT_RIGHT_ENABLE_HIGH : EVT_RIGHT_ENABLE_LOW);
}

void biba_hal_delay_us(uint32_t us)
{
    s_last_delay_us = us;
    record_event(EVT_DELAY_US);
}

void biba_hal_ssr_set(bool enabled)
{
    if (enabled) {
        record_event(EVT_SSR_HIGH);
    }
}

static void reset_fakes(void)
{
    memset(s_events, 0, sizeof(s_events));
    s_event_count = 0;
    s_last_delay_us = 0u;
}

static void test_rearm_mirrors_standalone_arm_edge_reset(void)
{
    const int expected[] = {
        EVT_PWM_LEFT_ZERO,
        EVT_PWM_RIGHT_ZERO,
        EVT_LEFT_ENABLE_LOW,
        EVT_RIGHT_ENABLE_LOW,
        EVT_DELAY_US,
        EVT_LEFT_ENABLE_HIGH,
        EVT_RIGHT_ENABLE_HIGH,
        EVT_SSR_HIGH,
    };

    reset_fakes();
    biba_motor_bridge_rearm();

    TEST_ASSERT_EQUAL_UINT32(BIBA_BTS7960_RESET_PULSE_US, s_last_delay_us);
    TEST_ASSERT_EQUAL_INT((int)(sizeof(expected) / sizeof(expected[0])), s_event_count);
    TEST_ASSERT_EQUAL_INT_ARRAY(expected, s_events, s_event_count);
}

static void run_all(void)
{
    RUN_TEST(test_rearm_mirrors_standalone_arm_edge_reset);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void)
{
    UNITY_BEGIN();
    run_all();
    return UNITY_END();
}
#endif