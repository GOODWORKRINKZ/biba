#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "led_panel.h"
#include "biba_test_support.h"

/* These tests assume the shipped default geometry (2 panels, 4x4,
 * serpentine, no flips). If biba_config.h defaults ever change, the
 * expectations below are the place that will notice first. */

#define TOTAL ((unsigned)BIBA_LED_PANEL_TOTAL)
#define COLS  ((unsigned)BIBA_LED_PANEL_COLS)
#define ROWS  ((unsigned)BIBA_LED_PANEL_ROWS)
#define LEFT  ((unsigned)BIBA_LED_PANEL_LEFT_IDX)
#define RIGHT ((unsigned)BIBA_LED_PANEL_RIGHT_IDX)

static biba_rgb_t g_frame[BIBA_LED_PANEL_TOTAL];

static void render(biba_led_mode_t mode, uint32_t now_ms)
{
    memset(g_frame, 0xAA, sizeof(g_frame));   /* poison: every pixel must be written */
    biba_led_panel_render(mode, now_ms, g_frame, TOTAL);
}

static bool panel_is_dark(unsigned panel)
{
    for (unsigned y = 0; y < ROWS; y++) {
        for (unsigned x = 0; x < COLS; x++) {
            const biba_rgb_t p = g_frame[biba_led_panel_index(panel, x, y)];
            if (p.r || p.g || p.b) return false;
        }
    }
    return true;
}

static unsigned panel_lit_count(unsigned panel)
{
    unsigned n = 0;
    for (unsigned y = 0; y < ROWS; y++) {
        for (unsigned x = 0; x < COLS; x++) {
            const biba_rgb_t p = g_frame[biba_led_panel_index(panel, x, y)];
            if (p.r || p.g || p.b) n++;
        }
    }
    return n;
}

/* Is column `x` of `panel` fully lit? */
static bool column_lit(unsigned panel, unsigned x)
{
    for (unsigned y = 0; y < ROWS; y++) {
        const biba_rgb_t p = g_frame[biba_led_panel_index(panel, x, y)];
        if (!p.r && !p.g && !p.b) return false;
    }
    return true;
}

/* -----------------------------------------------------------------------
 * Geometry
 * ----------------------------------------------------------------------- */
static void test_index_covers_every_pixel_exactly_once(void)
{
    uint8_t seen[BIBA_LED_PANEL_TOTAL];
    memset(seen, 0, sizeof(seen));

    for (unsigned p = 0; p < (unsigned)BIBA_LED_PANEL_COUNT; p++) {
        for (unsigned y = 0; y < ROWS; y++) {
            for (unsigned x = 0; x < COLS; x++) {
                unsigned i = biba_led_panel_index(p, x, y);
                TEST_ASSERT_TRUE(i < TOTAL);
                seen[i]++;
            }
        }
    }
    for (unsigned i = 0; i < TOTAL; i++) {
        TEST_ASSERT_EQUAL_UINT(1u, seen[i]);
    }
}

static void test_index_serpentine_reverses_odd_rows(void)
{
    /* Row 0 runs left-to-right, row 1 right-to-left. */
    TEST_ASSERT_EQUAL_UINT(0u, biba_led_panel_index(0u, 0u, 0u));
    TEST_ASSERT_EQUAL_UINT(COLS - 1u, biba_led_panel_index(0u, COLS - 1u, 0u));
    TEST_ASSERT_EQUAL_UINT(COLS, biba_led_panel_index(0u, COLS - 1u, 1u));
    TEST_ASSERT_EQUAL_UINT((2u * COLS) - 1u, biba_led_panel_index(0u, 0u, 1u));
}

static void test_index_rejects_out_of_range(void)
{
    TEST_ASSERT_EQUAL_UINT(TOTAL, biba_led_panel_index(BIBA_LED_PANEL_COUNT, 0u, 0u));
    TEST_ASSERT_EQUAL_UINT(TOTAL, biba_led_panel_index(0u, COLS, 0u));
    TEST_ASSERT_EQUAL_UINT(TOTAL, biba_led_panel_index(0u, 0u, ROWS));
}

static void test_second_panel_occupies_the_upper_half_of_the_chain(void)
{
    for (unsigned y = 0; y < ROWS; y++) {
        for (unsigned x = 0; x < COLS; x++) {
            TEST_ASSERT_TRUE(biba_led_panel_index(1u, x, y) >= BIBA_LED_PANEL_PIXELS);
        }
    }
}

/* -----------------------------------------------------------------------
 * Mode priority
 * ----------------------------------------------------------------------- */
static void test_mode_failsafe_beats_everything(void)
{
    biba_led_inputs_t in = { true, true, true, true, true, true };
    TEST_ASSERT_EQUAL_INT(BIBA_LED_MODE_FAILSAFE, biba_led_panel_mode(&in));
}

static void test_mode_trim_beats_driving(void)
{
    biba_led_inputs_t in = { false, true, true, true, false, false };
    TEST_ASSERT_EQUAL_INT(BIBA_LED_MODE_TRIM, biba_led_panel_mode(&in));
}

static void test_mode_driving_beats_beacon(void)
{
    biba_led_inputs_t fwd = { false, true, false, true, false, true };
    TEST_ASSERT_EQUAL_INT(BIBA_LED_MODE_FORWARD, biba_led_panel_mode(&fwd));

    biba_led_inputs_t rev = { false, true, false, false, true, true };
    TEST_ASSERT_EQUAL_INT(BIBA_LED_MODE_REVERSE, biba_led_panel_mode(&rev));
}

static void test_mode_reverse_beats_forward(void)
{
    /* Should never happen upstream, but the tie-break must be defined. */
    biba_led_inputs_t in = { false, true, false, true, true, false };
    TEST_ASSERT_EQUAL_INT(BIBA_LED_MODE_REVERSE, biba_led_panel_mode(&in));
}

static void test_mode_beacon_shows_when_armed_but_stopped(void)
{
    biba_led_inputs_t in = { false, true, false, false, false, true };
    TEST_ASSERT_EQUAL_INT(BIBA_LED_MODE_BEACON, biba_led_panel_mode(&in));
}

static void test_mode_armed_idle_and_disarmed(void)
{
    biba_led_inputs_t idle = { false, true, false, false, false, false };
    TEST_ASSERT_EQUAL_INT(BIBA_LED_MODE_ARMED_IDLE, biba_led_panel_mode(&idle));

    biba_led_inputs_t off = { false, false, false, false, false, false };
    TEST_ASSERT_EQUAL_INT(BIBA_LED_MODE_DISARMED, biba_led_panel_mode(&off));

    TEST_ASSERT_EQUAL_INT(BIBA_LED_MODE_DISARMED, biba_led_panel_mode(NULL));
}

static void test_mode_direction_ignored_while_disarmed(void)
{
    /* Stale direction flags must not light driving lights on a disarmed
     * robot — the arrow board is the safe default. */
    biba_led_inputs_t in = { false, false, false, true, true, false };
    TEST_ASSERT_EQUAL_INT(BIBA_LED_MODE_DISARMED, biba_led_panel_mode(&in));
}

/* -----------------------------------------------------------------------
 * Driving lights
 * ----------------------------------------------------------------------- */
static void test_forward_is_solid_white_on_both_panels(void)
{
    const uint8_t lvl = (uint8_t)BIBA_LED_PANEL_BRIGHTNESS;
    render(BIBA_LED_MODE_FORWARD, 12345u);
    for (unsigned i = 0; i < TOTAL; i++) {
        TEST_ASSERT_EQUAL_UINT(lvl, g_frame[i].r);
        TEST_ASSERT_EQUAL_UINT(lvl, g_frame[i].g);
        TEST_ASSERT_EQUAL_UINT(lvl, g_frame[i].b);
    }
}

static void test_forward_does_not_animate(void)
{
    render(BIBA_LED_MODE_FORWARD, 0u);
    biba_rgb_t first = g_frame[0];
    render(BIBA_LED_MODE_FORWARD, 7777u);
    TEST_ASSERT_EQUAL_UINT(first.r, g_frame[0].r);
    TEST_ASSERT_EQUAL_UINT(first.g, g_frame[0].g);
    TEST_ASSERT_EQUAL_UINT(first.b, g_frame[0].b);
}

static void test_reverse_is_solid_red_on_both_panels(void)
{
    render(BIBA_LED_MODE_REVERSE, 999u);
    for (unsigned i = 0; i < TOTAL; i++) {
        TEST_ASSERT_EQUAL_UINT((uint8_t)BIBA_LED_PANEL_BRIGHTNESS, g_frame[i].r);
        TEST_ASSERT_EQUAL_UINT(0u, g_frame[i].g);
        TEST_ASSERT_EQUAL_UINT(0u, g_frame[i].b);
    }
}

static void test_armed_idle_is_dimmer_than_forward(void)
{
    render(BIBA_LED_MODE_FORWARD, 0u);
    const uint8_t bright = g_frame[0].r;
    render(BIBA_LED_MODE_ARMED_IDLE, 0u);
    TEST_ASSERT_TRUE(g_frame[0].r < bright);
    /* Still white, still on. */
    TEST_ASSERT_TRUE(g_frame[0].r > 0u);
    TEST_ASSERT_EQUAL_UINT(g_frame[0].r, g_frame[0].g);
    TEST_ASSERT_EQUAL_UINT(g_frame[0].r, g_frame[0].b);
}

/* -----------------------------------------------------------------------
 * Failsafe strobe
 * ----------------------------------------------------------------------- */
static void test_failsafe_strobes_red(void)
{
    render(BIBA_LED_MODE_FAILSAFE, 0u);
    TEST_ASSERT_TRUE(g_frame[0].r > 0u);
    TEST_ASSERT_EQUAL_UINT(0u, g_frame[0].g);
    TEST_ASSERT_EQUAL_UINT(0u, g_frame[0].b);

    render(BIBA_LED_MODE_FAILSAFE, BIBA_LED_PANEL_FAILSAFE_MS);
    TEST_ASSERT_TRUE(panel_is_dark(LEFT));
    TEST_ASSERT_TRUE(panel_is_dark(RIGHT));

    render(BIBA_LED_MODE_FAILSAFE, 2u * BIBA_LED_PANEL_FAILSAFE_MS);
    TEST_ASSERT_TRUE(g_frame[0].r > 0u);
}

/* -----------------------------------------------------------------------
 * Beacon lightbar
 * ----------------------------------------------------------------------- */
static void test_beacon_alternates_blue_left_and_red_right(void)
{
    const uint32_t slot = BIBA_LED_PANEL_BEACON_SLOT_MS;

    /* Slot 0: left blue only. */
    render(BIBA_LED_MODE_BEACON, 0u);
    TEST_ASSERT_TRUE(panel_is_dark(RIGHT));
    TEST_ASSERT_EQUAL_UINT(0u, g_frame[biba_led_panel_index(LEFT, 0u, 0u)].r);
    TEST_ASSERT_TRUE(g_frame[biba_led_panel_index(LEFT, 0u, 0u)].b > 0u);

    /* Slot 8: right red only. */
    render(BIBA_LED_MODE_BEACON, 8u * slot);
    TEST_ASSERT_TRUE(panel_is_dark(LEFT));
    TEST_ASSERT_TRUE(g_frame[biba_led_panel_index(RIGHT, 0u, 0u)].r > 0u);
    TEST_ASSERT_EQUAL_UINT(0u, g_frame[biba_led_panel_index(RIGHT, 0u, 0u)].b);

    /* Slots 1 and 5: both dark (the gap inside and after a double flash). */
    render(BIBA_LED_MODE_BEACON, slot);
    TEST_ASSERT_TRUE(panel_is_dark(LEFT));
    TEST_ASSERT_TRUE(panel_is_dark(RIGHT));
    render(BIBA_LED_MODE_BEACON, 5u * slot);
    TEST_ASSERT_TRUE(panel_is_dark(LEFT));
    TEST_ASSERT_TRUE(panel_is_dark(RIGHT));
}

static void test_beacon_cycle_repeats(void)
{
    const uint32_t cycle = 16u * BIBA_LED_PANEL_BEACON_SLOT_MS;
    render(BIBA_LED_MODE_BEACON, 2u * BIBA_LED_PANEL_BEACON_SLOT_MS);
    const unsigned lit = panel_lit_count(LEFT);
    render(BIBA_LED_MODE_BEACON, cycle + (2u * BIBA_LED_PANEL_BEACON_SLOT_MS));
    TEST_ASSERT_EQUAL_UINT(lit, panel_lit_count(LEFT));
}

/* -----------------------------------------------------------------------
 * Road-service arrow board
 * ----------------------------------------------------------------------- */
static void test_service_sweeps_outward_from_the_centre(void)
{
    const uint32_t step = BIBA_LED_PANEL_SERVICE_STEP_MS;

    /* Phase 0: only the innermost column of each panel. Innermost means
     * the rightmost column of the left panel and the leftmost column of
     * the right panel. */
    render(BIBA_LED_MODE_DISARMED, 0u);
    TEST_ASSERT_EQUAL_UINT(ROWS, panel_lit_count(LEFT));
    TEST_ASSERT_EQUAL_UINT(ROWS, panel_lit_count(RIGHT));
    TEST_ASSERT_TRUE(column_lit(LEFT, COLS - 1u));
    TEST_ASSERT_TRUE(column_lit(RIGHT, 0u));

    /* Each further phase adds one more column, outward. */
    for (unsigned phase = 1; phase < COLS; phase++) {
        render(BIBA_LED_MODE_DISARMED, phase * step);
        TEST_ASSERT_EQUAL_UINT((phase + 1u) * ROWS, panel_lit_count(LEFT));
        TEST_ASSERT_EQUAL_UINT((phase + 1u) * ROWS, panel_lit_count(RIGHT));
        TEST_ASSERT_TRUE(column_lit(LEFT, COLS - 1u - phase));
        TEST_ASSERT_TRUE(column_lit(RIGHT, phase));
    }
}

static void test_service_is_amber_and_double_flashes(void)
{
    const uint32_t step = BIBA_LED_PANEL_SERVICE_STEP_MS;

    render(BIBA_LED_MODE_DISARMED, 0u);
    const biba_rgb_t p = g_frame[biba_led_panel_index(RIGHT, 0u, 0u)];
    TEST_ASSERT_TRUE(p.r > 0u);
    TEST_ASSERT_TRUE(p.g > 0u);
    TEST_ASSERT_TRUE(p.g < p.r);          /* amber, not yellow, not red */
    TEST_ASSERT_EQUAL_UINT(0u, p.b);

    /* hold, blank, flash, blank */
    render(BIBA_LED_MODE_DISARMED, (COLS + 0u) * step);
    TEST_ASSERT_EQUAL_UINT(COLS * ROWS, panel_lit_count(LEFT));
    render(BIBA_LED_MODE_DISARMED, (COLS + 1u) * step);
    TEST_ASSERT_TRUE(panel_is_dark(LEFT));
    render(BIBA_LED_MODE_DISARMED, (COLS + 2u) * step);
    TEST_ASSERT_EQUAL_UINT(COLS * ROWS, panel_lit_count(LEFT));
    render(BIBA_LED_MODE_DISARMED, (COLS + 3u) * step);
    TEST_ASSERT_TRUE(panel_is_dark(LEFT));

    /* And the cycle restarts. */
    render(BIBA_LED_MODE_DISARMED, (COLS + 4u) * step);
    TEST_ASSERT_EQUAL_UINT(ROWS, panel_lit_count(LEFT));
}

/* -----------------------------------------------------------------------
 * Trim chase
 * ----------------------------------------------------------------------- */
static void test_trim_lights_a_short_moving_tail(void)
{
    render(BIBA_LED_MODE_TRIM, 0u);
    TEST_ASSERT_EQUAL_UINT(3u, panel_lit_count(LEFT));
    TEST_ASSERT_EQUAL_UINT(3u, panel_lit_count(RIGHT));

    /* Head is at the top-left corner at t=0 and moves along the top row. */
    const unsigned head0 = biba_led_panel_index(LEFT, 0u, 0u);
    TEST_ASSERT_TRUE(g_frame[head0].r > 0u);

    render(BIBA_LED_MODE_TRIM, BIBA_LED_PANEL_TRIM_STEP_MS);
    TEST_ASSERT_TRUE(g_frame[biba_led_panel_index(LEFT, 1u, 0u)].r > 0u);
    /* The old head is now the first tail cell — still lit, but dimmer. */
    TEST_ASSERT_TRUE(g_frame[head0].r > 0u);
    TEST_ASSERT_TRUE(g_frame[head0].r
                     < g_frame[biba_led_panel_index(LEFT, 1u, 0u)].r);
}

static void test_trim_stays_on_the_border(void)
{
    const unsigned perim = ((COLS + ROWS) * 2u) - 4u;
    for (unsigned k = 0; k < perim; k++) {
        render(BIBA_LED_MODE_TRIM, k * BIBA_LED_PANEL_TRIM_STEP_MS);
        for (unsigned y = 1; y + 1u < ROWS; y++) {
            for (unsigned x = 1; x + 1u < COLS; x++) {
                const biba_rgb_t p = g_frame[biba_led_panel_index(LEFT, x, y)];
                TEST_ASSERT_EQUAL_UINT(0u, p.r);
                TEST_ASSERT_EQUAL_UINT(0u, p.g);
                TEST_ASSERT_EQUAL_UINT(0u, p.b);
            }
        }
    }
}

/* -----------------------------------------------------------------------
 * Buffer handling
 * ----------------------------------------------------------------------- */
static void test_render_respects_a_short_buffer(void)
{
    biba_rgb_t small[4];
    memset(small, 0x11, sizeof(small));
    biba_led_panel_render(BIBA_LED_MODE_FORWARD, 0u, small, 2u);
    TEST_ASSERT_EQUAL_UINT((uint8_t)BIBA_LED_PANEL_BRIGHTNESS, small[0].r);
    TEST_ASSERT_EQUAL_UINT((uint8_t)BIBA_LED_PANEL_BRIGHTNESS, small[1].r);
    TEST_ASSERT_EQUAL_UINT(0x11u, small[2].r);   /* untouched */
    TEST_ASSERT_EQUAL_UINT(0x11u, small[3].r);
}

static void test_render_tolerates_null_and_zero(void)
{
    biba_led_panel_render(BIBA_LED_MODE_FORWARD, 0u, NULL, 8u);
    biba_rgb_t one = { 1u, 2u, 3u };
    biba_led_panel_render(BIBA_LED_MODE_FORWARD, 0u, &one, 0u);
    TEST_ASSERT_EQUAL_UINT(1u, one.r);
}

/* -----------------------------------------------------------------------
 * Runner
 * ----------------------------------------------------------------------- */
static void run_all(void)
{
    RUN_TEST(test_index_covers_every_pixel_exactly_once);
    RUN_TEST(test_index_serpentine_reverses_odd_rows);
    RUN_TEST(test_index_rejects_out_of_range);
    RUN_TEST(test_second_panel_occupies_the_upper_half_of_the_chain);

    RUN_TEST(test_mode_failsafe_beats_everything);
    RUN_TEST(test_mode_trim_beats_driving);
    RUN_TEST(test_mode_driving_beats_beacon);
    RUN_TEST(test_mode_reverse_beats_forward);
    RUN_TEST(test_mode_beacon_shows_when_armed_but_stopped);
    RUN_TEST(test_mode_armed_idle_and_disarmed);
    RUN_TEST(test_mode_direction_ignored_while_disarmed);

    RUN_TEST(test_forward_is_solid_white_on_both_panels);
    RUN_TEST(test_forward_does_not_animate);
    RUN_TEST(test_reverse_is_solid_red_on_both_panels);
    RUN_TEST(test_armed_idle_is_dimmer_than_forward);

    RUN_TEST(test_failsafe_strobes_red);

    RUN_TEST(test_beacon_alternates_blue_left_and_red_right);
    RUN_TEST(test_beacon_cycle_repeats);

    RUN_TEST(test_service_sweeps_outward_from_the_centre);
    RUN_TEST(test_service_is_amber_and_double_flashes);

    RUN_TEST(test_trim_lights_a_short_moving_tail);
    RUN_TEST(test_trim_stays_on_the_border);

    RUN_TEST(test_render_respects_a_short_buffer);
    RUN_TEST(test_render_tolerates_null_and_zero);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
