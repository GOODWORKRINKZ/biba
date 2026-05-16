#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "biba_test_support.h"
#include "biba_config.h"
#include "drivers/bts7960.h"

/* Build this driver into test_bts7960 only, avoiding global native_test link impact. */
#include "../../src/drivers/bts7960.c"

enum {
    EVT_PWM_LEFT_ZERO = 1,
    EVT_PWM_RIGHT_ZERO,
    EVT_LEFT_ENABLE_LOW,
    EVT_RIGHT_ENABLE_LOW,
    EVT_DELAY_US,
    EVT_LEFT_ENABLE_HIGH,
    EVT_RIGHT_ENABLE_HIGH,
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

static void reset_fakes(void)
{
    memset(s_events, 0, sizeof(s_events));
    s_event_count = 0;
    s_last_delay_us = 0u;
}

static void test_thermal_reset_enforces_minimum_pulse_and_sequence(void)
{
    const int expected[] = {
        EVT_PWM_LEFT_ZERO,
        EVT_PWM_RIGHT_ZERO,
        EVT_LEFT_ENABLE_LOW,
        EVT_RIGHT_ENABLE_LOW,
        EVT_DELAY_US,
        EVT_LEFT_ENABLE_HIGH,
        EVT_RIGHT_ENABLE_HIGH,
    };

    reset_fakes();
    biba_bts7960_thermal_reset(BIBA_BTS7960_RESET_PULSE_US - 1u);

    TEST_ASSERT_EQUAL_UINT32(BIBA_BTS7960_RESET_PULSE_US, s_last_delay_us);
    TEST_ASSERT_EQUAL_INT((int)(sizeof(expected) / sizeof(expected[0])), s_event_count);
    TEST_ASSERT_EQUAL_INT_ARRAY(expected, s_events, s_event_count);
}

static void test_thermal_reset_preserves_larger_caller_pulse(void)
{
    const uint32_t pulse_us = BIBA_BTS7960_RESET_PULSE_US + 200u;

    reset_fakes();
    biba_bts7960_thermal_reset(pulse_us);

    TEST_ASSERT_EQUAL_UINT32(pulse_us, s_last_delay_us);
}

static void run_all(void)
{
    RUN_TEST(test_thermal_reset_enforces_minimum_pulse_and_sequence);
    RUN_TEST(test_thermal_reset_preserves_larger_caller_pulse);
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
