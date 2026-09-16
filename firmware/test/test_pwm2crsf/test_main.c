#include <stdint.h>
#include <string.h>

#include "crsf.h"
#include "pwm2crsf/pwm2crsf.h"
#include "biba_test_support.h"

#define MS  1000u

static pwm2crsf_config_t make_config(void)
{
    pwm2crsf_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.input_count      = 6;
    cfg.min_us           = 1000;
    cfg.max_us           = 2000;
    cfg.valid_min_us     = 800;
    cfg.valid_max_us     = 2200;
    cfg.input_timeout_us = 100 * MS;
    for (unsigned ch = 0; ch < CRSF_RC_CHANNEL_COUNT; ++ch) {
        cfg.map[ch]  = (ch < 6) ? (int8_t)ch : PWM2CRSF_UNMAPPED;
        cfg.idle[ch] = PWM2CRSF_CRSF_MID;
    }
    cfg.idle[6] = PWM2CRSF_CRSF_MIN;
    cfg.button_high_us         = 1700;
    cfg.button_low_us          = 1300;
    cfg.button_min_interval_us = 150 * MS;
    for (unsigned i = 0; i < PWM2CRSF_MAX_BUTTONS; ++i) {
        cfg.buttons[i].input = PWM2CRSF_UNMAPPED;
    }
    cfg.arm_input = PWM2CRSF_UNMAPPED;
    return cfg;
}

static pwm2crsf_config_t make_cycle_config(bool latching)
{
    pwm2crsf_config_t cfg = make_config();
    cfg.buttons[0].input            = 3;   /* PWM4 */
    cfg.buttons[0].crsf_ch          = 5;   /* CH6  */
    cfg.buttons[0].steps            = 3;
    cfg.buttons[0].count_both_edges = latching;
    return cfg;
}

static uint16_t speed_ch(const pwm2crsf_state_t *st, const pwm2crsf_config_t *cfg)
{
    uint16_t ch[CRSF_RC_CHANNEL_COUNT];
    pwm2crsf_channels(st, cfg, 0, ch);
    return ch[5];
}

static void feed_all(pwm2crsf_state_t *st, const pwm2crsf_config_t *cfg,
                     uint32_t width_us, uint64_t now_us)
{
    for (uint8_t i = 0; i < cfg->input_count; ++i) {
        TEST_ASSERT_TRUE(pwm2crsf_on_pulse(st, cfg, i, width_us, now_us));
    }
}

static void test_us_to_crsf_endpoints_and_centre(void)
{
    pwm2crsf_config_t cfg = make_config();
    TEST_ASSERT_EQUAL_UINT16(172,  pwm2crsf_us_to_crsf(&cfg, 1000));
    TEST_ASSERT_EQUAL_UINT16(992,  pwm2crsf_us_to_crsf(&cfg, 1500));
    TEST_ASSERT_EQUAL_UINT16(1811, pwm2crsf_us_to_crsf(&cfg, 2000));
}

static void test_us_to_crsf_clamps_outside_endpoints(void)
{
    pwm2crsf_config_t cfg = make_config();
    TEST_ASSERT_EQUAL_UINT16(172,  pwm2crsf_us_to_crsf(&cfg, 900));
    TEST_ASSERT_EQUAL_UINT16(1811, pwm2crsf_us_to_crsf(&cfg, 2150));
}

static void test_us_to_crsf_is_monotonic(void)
{
    pwm2crsf_config_t cfg = make_config();
    uint16_t prev = 0;
    for (uint32_t us = 950; us <= 2050; ++us) {
        uint16_t v = pwm2crsf_us_to_crsf(&cfg, us);
        TEST_ASSERT_TRUE(v >= prev);
        prev = v;
    }
}

static void test_no_frame_before_any_pulse(void)
{
    pwm2crsf_config_t cfg = make_config();
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    uint8_t buf[CRSF_MAX_FRAME_SIZE];
    TEST_ASSERT_FALSE(pwm2crsf_link_ok(&st, &cfg, 0));
    TEST_ASSERT_EQUAL_INT(0, (int)pwm2crsf_build_rc_frame(&st, &cfg, 0, buf, sizeof(buf)));
}

static void test_frame_carries_mapped_and_idle_channels(void)
{
    pwm2crsf_config_t cfg = make_config();
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    feed_all(&st, &cfg, 1500, 10 * MS);
    TEST_ASSERT_TRUE(pwm2crsf_on_pulse(&st, &cfg, 1, 2000, 10 * MS));   /* CH2 throttle full */
    TEST_ASSERT_TRUE(pwm2crsf_on_pulse(&st, &cfg, 4, 1000, 10 * MS));   /* CH5 arm low */

    uint8_t buf[CRSF_MAX_FRAME_SIZE];
    size_t len = pwm2crsf_build_rc_frame(&st, &cfg, 20 * MS, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_INT(26, (int)len);

    const uint8_t *payload = NULL;
    size_t payload_len = 0;
    TEST_ASSERT_EQUAL_UINT8(CRSF_FRAMETYPE_RC_CHANNELS,
                            biba_crsf_parse_frame(buf, len, &payload, &payload_len));
    uint16_t ch[CRSF_RC_CHANNEL_COUNT];
    TEST_ASSERT_TRUE(biba_crsf_unpack_channels(payload, payload_len, ch));
    TEST_ASSERT_EQUAL_UINT16(992,  ch[0]);
    TEST_ASSERT_EQUAL_UINT16(1811, ch[1]);
    TEST_ASSERT_EQUAL_UINT16(172,  ch[4]);
    TEST_ASSERT_EQUAL_UINT16(172,  ch[6]);    /* idle value */
    TEST_ASSERT_EQUAL_UINT16(992,  ch[15]);   /* idle value */
}

static void test_remap_routes_inputs(void)
{
    pwm2crsf_config_t cfg = make_config();
    cfg.map[0] = 1;   /* CH1 ← PWM2 */
    cfg.map[1] = 0;   /* CH2 ← PWM1 */
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    feed_all(&st, &cfg, 1500, 0);
    TEST_ASSERT_TRUE(pwm2crsf_on_pulse(&st, &cfg, 0, 1000, 0));
    TEST_ASSERT_TRUE(pwm2crsf_on_pulse(&st, &cfg, 1, 2000, 0));

    uint16_t ch[CRSF_RC_CHANNEL_COUNT];
    pwm2crsf_channels(&st, &cfg, 0, ch);
    TEST_ASSERT_EQUAL_UINT16(1811, ch[0]);
    TEST_ASSERT_EQUAL_UINT16(172,  ch[1]);
}

static void test_invert_mask_mirrors_selected_input(void)
{
    pwm2crsf_config_t cfg = make_config();
    cfg.invert_mask = (uint8_t)(1u << 2);
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    feed_all(&st, &cfg, 1000, 0);
    pwm2crsf_on_pulse(&st, &cfg, 2, 1000, 0);

    uint16_t ch[CRSF_RC_CHANNEL_COUNT];
    pwm2crsf_channels(&st, &cfg, 0, ch);
    TEST_ASSERT_EQUAL_UINT16(172,  ch[0]);   /* not inverted */
    TEST_ASSERT_EQUAL_UINT16(1811, ch[2]);   /* inverted: 1000 → 2000 */

    pwm2crsf_on_pulse(&st, &cfg, 2, 1500, 0);
    pwm2crsf_channels(&st, &cfg, 0, ch);
    TEST_ASSERT_EQUAL_UINT16(992, ch[2]);    /* centre stays centre */
}

static void test_cycle_momentary_steps_on_each_press(void)
{
    pwm2crsf_config_t cfg = make_cycle_config(false);
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    feed_all(&st, &cfg, 1000, 0);                 /* baseline: released */
    TEST_ASSERT_EQUAL_UINT16(172, speed_ch(&st, &cfg));

    const uint16_t expected[] = {992, 1811, 172, 992};
    uint64_t t = 0;
    for (unsigned i = 0; i < 4; ++i) {
        t += 200 * MS;
        pwm2crsf_on_pulse(&st, &cfg, 3, 2000, t);    /* press */
        TEST_ASSERT_EQUAL_UINT16(expected[i], speed_ch(&st, &cfg));
        t += 200 * MS;
        pwm2crsf_on_pulse(&st, &cfg, 3, 1000, t);    /* release: no step */
        TEST_ASSERT_EQUAL_UINT16(expected[i], speed_ch(&st, &cfg));
    }
}

static void test_cycle_latching_steps_on_every_flip(void)
{
    pwm2crsf_config_t cfg = make_cycle_config(true);
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    feed_all(&st, &cfg, 1000, 0);
    pwm2crsf_on_pulse(&st, &cfg, 3, 2000, 200 * MS);
    TEST_ASSERT_EQUAL_UINT16(992, speed_ch(&st, &cfg));
    pwm2crsf_on_pulse(&st, &cfg, 3, 1000, 400 * MS);
    TEST_ASSERT_EQUAL_UINT16(1811, speed_ch(&st, &cfg));
    pwm2crsf_on_pulse(&st, &cfg, 3, 2000, 600 * MS);
    TEST_ASSERT_EQUAL_UINT16(172, speed_ch(&st, &cfg));
}

static void test_cycle_baseline_high_is_not_a_press(void)
{
    pwm2crsf_config_t cfg = make_cycle_config(true);
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    feed_all(&st, &cfg, 2000, 0);                 /* powered up with button "on" */
    pwm2crsf_on_pulse(&st, &cfg, 3, 2000, 20 * MS);
    TEST_ASSERT_EQUAL_UINT16(172, speed_ch(&st, &cfg));
}

static void test_cycle_ignores_hysteresis_band_and_bounce(void)
{
    pwm2crsf_config_t cfg = make_cycle_config(false);
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    feed_all(&st, &cfg, 1000, 0);

    pwm2crsf_on_pulse(&st, &cfg, 3, 1500, 200 * MS);  /* mid-band: no change */
    TEST_ASSERT_EQUAL_UINT16(172, speed_ch(&st, &cfg));

    pwm2crsf_on_pulse(&st, &cfg, 3, 2000, 300 * MS);  /* press → step 2 */
    pwm2crsf_on_pulse(&st, &cfg, 3, 1000, 320 * MS);
    pwm2crsf_on_pulse(&st, &cfg, 3, 2000, 340 * MS);  /* bounce inside 150 ms */
    TEST_ASSERT_EQUAL_UINT16(992, speed_ch(&st, &cfg));
}

static void test_cycle_reset_returns_to_first_step(void)
{
    pwm2crsf_config_t cfg = make_cycle_config(false);
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    feed_all(&st, &cfg, 1000, 0);
    pwm2crsf_on_pulse(&st, &cfg, 3, 2000, 200 * MS);
    TEST_ASSERT_EQUAL_UINT16(992, speed_ch(&st, &cfg));

    pwm2crsf_reset_on_link_loss(&st);
    TEST_ASSERT_EQUAL_UINT16(172, speed_ch(&st, &cfg));
    /* Button still held after the dropout: re-baselined, not a press. */
    pwm2crsf_on_pulse(&st, &cfg, 3, 2000, 900 * MS);
    TEST_ASSERT_EQUAL_UINT16(172, speed_ch(&st, &cfg));
}

static void test_dead_aux_input_keeps_link_and_idles_its_channel(void)
{
    pwm2crsf_config_t cfg = make_config();
    cfg.required_mask = (uint8_t)((1u << 0) | (1u << 1) | (1u << 2));
    cfg.idle[5] = 172;
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    for (uint8_t i = 0; i < 5; ++i) pwm2crsf_on_pulse(&st, &cfg, i, 2000, 0);
    /* PWM6 never pulses (bench: in6=0!). */
    TEST_ASSERT_TRUE(pwm2crsf_link_ok(&st, &cfg, 50 * MS));

    uint8_t buf[CRSF_MAX_FRAME_SIZE];
    TEST_ASSERT_TRUE(pwm2crsf_build_rc_frame(&st, &cfg, 50 * MS, buf, sizeof(buf)) > 0);
    uint16_t ch[CRSF_RC_CHANNEL_COUNT];
    pwm2crsf_channels(&st, &cfg, 50 * MS, ch);
    TEST_ASSERT_EQUAL_UINT16(1811, ch[4]);
    TEST_ASSERT_EQUAL_UINT16(172,  ch[5]);   /* dead input → idle */

    /* A required input dying still drops the link. */
    TEST_ASSERT_FALSE(pwm2crsf_link_ok(&st, &cfg, 150 * MS));
}

static void test_arm_interlock_needs_off_position_first(void)
{
    pwm2crsf_config_t cfg = make_config();
    cfg.arm_input   = 4;   /* PWM5 → CH5 in the identity map */
    cfg.arm_crsf_ch = 4;
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    uint16_t ch[CRSF_RC_CHANNEL_COUNT];

    feed_all(&st, &cfg, 1500, 0);
    pwm2crsf_on_pulse(&st, &cfg, 4, 2000, 0);        /* powered up already ON */
    pwm2crsf_channels(&st, &cfg, 0, ch);
    TEST_ASSERT_EQUAL_UINT16(172, ch[4]);            /* locked */

    pwm2crsf_on_pulse(&st, &cfg, 4, 1000, 20 * MS);  /* switch off */
    pwm2crsf_channels(&st, &cfg, 20 * MS, ch);
    TEST_ASSERT_EQUAL_UINT16(172, ch[4]);
    pwm2crsf_on_pulse(&st, &cfg, 4, 2000, 40 * MS);  /* and on again */
    pwm2crsf_channels(&st, &cfg, 40 * MS, ch);
    TEST_ASSERT_EQUAL_UINT16(1811, ch[4]);           /* armed */

    pwm2crsf_reset_on_link_loss(&st);                /* failsafe */
    pwm2crsf_on_pulse(&st, &cfg, 4, 2000, 60 * MS);
    pwm2crsf_channels(&st, &cfg, 60 * MS, ch);
    TEST_ASSERT_EQUAL_UINT16(172, ch[4]);            /* locked again */
}

static void test_momentary_toggle_button_flips_on_press(void)
{
    pwm2crsf_config_t cfg = make_config();
    cfg.buttons[1].input            = 4;   /* PWM5 */
    cfg.buttons[1].crsf_ch          = 9;   /* CH10 */
    cfg.buttons[1].steps            = 2;
    cfg.buttons[1].count_both_edges = false;
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    uint16_t ch[CRSF_RC_CHANNEL_COUNT];

    feed_all(&st, &cfg, 1000, 0);
    pwm2crsf_channels(&st, &cfg, 0, ch);
    TEST_ASSERT_EQUAL_UINT16(172, ch[9]);

    pwm2crsf_on_pulse(&st, &cfg, 4, 2000, 200 * MS);   /* press */
    pwm2crsf_on_pulse(&st, &cfg, 4, 1000, 220 * MS);   /* release */
    pwm2crsf_channels(&st, &cfg, 220 * MS, ch);
    TEST_ASSERT_EQUAL_UINT16(1811, ch[9]);
    TEST_ASSERT_EQUAL_UINT8(1, pwm2crsf_button_step(&st, 1));

    pwm2crsf_on_pulse(&st, &cfg, 4, 2000, 500 * MS);
    pwm2crsf_on_pulse(&st, &cfg, 4, 1000, 520 * MS);
    pwm2crsf_channels(&st, &cfg, 520 * MS, ch);
    TEST_ASSERT_EQUAL_UINT16(172, ch[9]);
}

static void test_two_buttons_are_independent(void)
{
    pwm2crsf_config_t cfg = make_cycle_config(true);
    cfg.buttons[1].input            = 4;
    cfg.buttons[1].crsf_ch          = 9;
    cfg.buttons[1].steps            = 2;
    cfg.buttons[1].count_both_edges = false;
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    feed_all(&st, &cfg, 1000, 0);

    pwm2crsf_on_pulse(&st, &cfg, 3, 2000, 200 * MS);   /* speed → 2 */
    TEST_ASSERT_EQUAL_UINT8(1, pwm2crsf_button_step(&st, 0));
    TEST_ASSERT_EQUAL_UINT8(0, pwm2crsf_button_step(&st, 1));

    pwm2crsf_on_pulse(&st, &cfg, 4, 2000, 210 * MS);   /* drive → HOLD */
    TEST_ASSERT_EQUAL_UINT8(1, pwm2crsf_button_step(&st, 0));
    TEST_ASSERT_EQUAL_UINT8(1, pwm2crsf_button_step(&st, 1));
}

static void test_silent_input_triggers_failsafe(void)
{
    pwm2crsf_config_t cfg = make_config();
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    feed_all(&st, &cfg, 1500, 0);
    TEST_ASSERT_TRUE(pwm2crsf_link_ok(&st, &cfg, 100 * MS));

    /* Everyone but input 3 keeps talking. */
    for (uint8_t i = 0; i < 6; ++i) {
        if (i != 3) pwm2crsf_on_pulse(&st, &cfg, i, 1500, 90 * MS);
    }
    TEST_ASSERT_FALSE(pwm2crsf_link_ok(&st, &cfg, 101 * MS));

    uint8_t buf[CRSF_MAX_FRAME_SIZE];
    TEST_ASSERT_EQUAL_INT(0, (int)pwm2crsf_build_rc_frame(&st, &cfg, 101 * MS, buf, sizeof(buf)));

    /* Recovers as soon as the input is back. */
    pwm2crsf_on_pulse(&st, &cfg, 3, 1500, 120 * MS);
    TEST_ASSERT_TRUE(pwm2crsf_link_ok(&st, &cfg, 120 * MS));
}

static void test_unmapped_input_does_not_hold_link(void)
{
    pwm2crsf_config_t cfg = make_config();
    cfg.map[5] = PWM2CRSF_UNMAPPED;   /* PWM6 not used */
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    for (uint8_t i = 0; i < 5; ++i) pwm2crsf_on_pulse(&st, &cfg, i, 1500, 0);
    TEST_ASSERT_TRUE(pwm2crsf_link_ok(&st, &cfg, 50 * MS));
}

static void test_glitches_are_rejected_and_do_not_refresh(void)
{
    pwm2crsf_config_t cfg = make_config();
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    feed_all(&st, &cfg, 1500, 0);

    TEST_ASSERT_FALSE(pwm2crsf_on_pulse(&st, &cfg, 0, 300, 90 * MS));
    TEST_ASSERT_FALSE(pwm2crsf_on_pulse(&st, &cfg, 0, 3000, 90 * MS));
    TEST_ASSERT_EQUAL_UINT32(2, st.glitches);
    TEST_ASSERT_EQUAL_UINT16(1500, st.width_us[0]);
    TEST_ASSERT_FALSE(pwm2crsf_input_fresh(&st, &cfg, 0, 150 * MS));
}

static void test_out_of_range_input_index_rejected(void)
{
    pwm2crsf_config_t cfg = make_config();
    pwm2crsf_state_t st;
    pwm2crsf_init(&st);
    TEST_ASSERT_FALSE(pwm2crsf_on_pulse(&st, &cfg, 6, 1500, 0));
    TEST_ASSERT_FALSE(pwm2crsf_on_pulse(&st, &cfg, 200, 1500, 0));
}

static void test_link_stats_frame_reports_quality(void)
{
    uint8_t buf[CRSF_MAX_FRAME_SIZE];
    size_t len = pwm2crsf_build_link_stats_frame(true, buf, sizeof(buf));
    const uint8_t *payload = NULL;
    size_t payload_len = 0;
    TEST_ASSERT_EQUAL_UINT8(CRSF_FRAMETYPE_LINK_STATS,
                            biba_crsf_parse_frame(buf, len, &payload, &payload_len));
    biba_crsf_link_stats_t stats;
    TEST_ASSERT_TRUE(biba_crsf_parse_link_stats(payload, payload_len, &stats));
    TEST_ASSERT_EQUAL_UINT8(100, stats.uplink_link_quality);
}

static void run_all(void)
{
    RUN_TEST(test_us_to_crsf_endpoints_and_centre);
    RUN_TEST(test_us_to_crsf_clamps_outside_endpoints);
    RUN_TEST(test_us_to_crsf_is_monotonic);
    RUN_TEST(test_no_frame_before_any_pulse);
    RUN_TEST(test_frame_carries_mapped_and_idle_channels);
    RUN_TEST(test_remap_routes_inputs);
    RUN_TEST(test_invert_mask_mirrors_selected_input);
    RUN_TEST(test_cycle_momentary_steps_on_each_press);
    RUN_TEST(test_cycle_latching_steps_on_every_flip);
    RUN_TEST(test_cycle_baseline_high_is_not_a_press);
    RUN_TEST(test_cycle_ignores_hysteresis_band_and_bounce);
    RUN_TEST(test_cycle_reset_returns_to_first_step);
    RUN_TEST(test_dead_aux_input_keeps_link_and_idles_its_channel);
    RUN_TEST(test_arm_interlock_needs_off_position_first);
    RUN_TEST(test_momentary_toggle_button_flips_on_press);
    RUN_TEST(test_two_buttons_are_independent);
    RUN_TEST(test_silent_input_triggers_failsafe);
    RUN_TEST(test_unmapped_input_does_not_hold_link);
    RUN_TEST(test_glitches_are_rejected_and_do_not_refresh);
    RUN_TEST(test_out_of_range_input_index_rejected);
    RUN_TEST(test_link_stats_frame_reports_quality);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
