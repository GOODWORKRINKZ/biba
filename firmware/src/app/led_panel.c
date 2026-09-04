/* Indicator LED panel effects. See led_panel.h for the contract.
 *
 * Every effect is a pure function of the timestamp: no phase counters,
 * no "last frame" state. A dropped frame therefore costs nothing but a
 * dropped frame, and the host tests can sample any point of any cycle
 * by just passing the millisecond they want.
 */

#include "led_panel.h"

#include <string.h>

#define PANEL_COLS   ((unsigned)BIBA_LED_PANEL_COLS)
#define PANEL_ROWS   ((unsigned)BIBA_LED_PANEL_ROWS)
#define PANEL_COUNT  ((unsigned)BIBA_LED_PANEL_COUNT)
#define PANEL_PIXELS ((unsigned)BIBA_LED_PANEL_PIXELS)
#define PANEL_TOTAL  ((unsigned)BIBA_LED_PANEL_TOTAL)

/* --- Mode selection ----------------------------------------------------- */

biba_led_mode_t biba_led_panel_mode(const biba_led_inputs_t *in)
{
    if (in == NULL)                   return BIBA_LED_MODE_DISARMED;
    if (in->failsafe)                 return BIBA_LED_MODE_FAILSAFE;
    if (in->trim)                     return BIBA_LED_MODE_TRIM;
    if (in->armed && in->reversing)   return BIBA_LED_MODE_REVERSE;
    if (in->armed && in->forward)     return BIBA_LED_MODE_FORWARD;
    if (in->beacon)                   return BIBA_LED_MODE_BEACON;
    if (in->armed)                    return BIBA_LED_MODE_ARMED_IDLE;
    return BIBA_LED_MODE_DISARMED;
}

/* --- Geometry ----------------------------------------------------------- */

unsigned biba_led_panel_index(unsigned panel, unsigned x, unsigned y)
{
    if (panel >= PANEL_COUNT || x >= PANEL_COLS || y >= PANEL_ROWS) {
        return PANEL_TOTAL;
    }

#if BIBA_LED_PANEL_FLIP_X
    x = PANEL_COLS - 1u - x;
#endif
#if BIBA_LED_PANEL_FLIP_Y
    y = PANEL_ROWS - 1u - y;
#endif
#if BIBA_LED_PANEL_SERPENTINE
    /* Odd rows are wired right-to-left. */
    if ((y & 1u) != 0u) {
        x = PANEL_COLS - 1u - x;
    }
#endif

    return (panel * PANEL_PIXELS) + (y * PANEL_COLS) + x;
}

/* --- Frame helpers ------------------------------------------------------ */

/* The effects paint into a fixed-size scratch frame at full 0..255
 * intent; the public entry point scales by master brightness and copies
 * out however much the caller asked for. That keeps every effect below
 * free of both bounds arithmetic and brightness arithmetic. */
static biba_rgb_t s_frame[BIBA_LED_PANEL_TOTAL];

static void frame_clear(void)
{
    memset(s_frame, 0, sizeof(s_frame));
}

static void frame_fill(uint8_t r, uint8_t g, uint8_t b)
{
    for (unsigned i = 0; i < PANEL_TOTAL; i++) {
        s_frame[i].r = r;
        s_frame[i].g = g;
        s_frame[i].b = b;
    }
}

static void panel_fill(unsigned panel, uint8_t r, uint8_t g, uint8_t b)
{
    if (panel >= PANEL_COUNT) return;
    const unsigned base = panel * PANEL_PIXELS;
    for (unsigned i = 0; i < PANEL_PIXELS; i++) {
        s_frame[base + i].r = r;
        s_frame[base + i].g = g;
        s_frame[base + i].b = b;
    }
}

static void px_set(unsigned panel, unsigned x, unsigned y,
                   uint8_t r, uint8_t g, uint8_t b)
{
    unsigned i = biba_led_panel_index(panel, x, y);
    if (i >= PANEL_TOTAL) return;
    s_frame[i].r = r;
    s_frame[i].g = g;
    s_frame[i].b = b;
}

static void panel_fill_column(unsigned panel, unsigned x,
                              uint8_t r, uint8_t g, uint8_t b)
{
    for (unsigned y = 0; y < PANEL_ROWS; y++) {
        px_set(panel, x, y, r, g, b);
    }
}

/* Rounded v * num / 255. Used for master brightness and for the fading
 * tail of the chase effect. */
static uint8_t scale8(uint8_t v, unsigned num)
{
    return (uint8_t)(((unsigned)v * num + 127u) / 255u);
}

/* --- Effect: road-service arrow board (disarmed) ------------------------ *
 *
 * Amber, shaped like the arrow board on a highway maintenance truck:
 * both panels sweep outward from the centre of the robot (left panel
 * right-to-left, right panel left-to-right), each step adding a column
 * until the panel is full, then the whole board double-flashes and the
 * cycle restarts.
 *
 * Phases, BIBA_LED_PANEL_SERVICE_STEP_MS each:
 *   0 .. COLS-1   accumulating outward sweep
 *   COLS          hold, everything lit
 *   COLS+1        blank
 *   COLS+2        flash
 *   COLS+3        blank
 */
#define SERVICE_PHASES (PANEL_COLS + 4u)

static void render_service(uint32_t now_ms)
{
    const uint8_t ar = (uint8_t)BIBA_LED_PANEL_AMBER_R;
    const uint8_t ag = (uint8_t)BIBA_LED_PANEL_AMBER_G;
    const uint8_t ab = (uint8_t)BIBA_LED_PANEL_AMBER_B;

    const unsigned phase =
        (now_ms / BIBA_LED_PANEL_SERVICE_STEP_MS) % SERVICE_PHASES;

    frame_clear();

    if (phase < PANEL_COLS) {
        /* The column nearest the robot centre lights first, then outward. */
        for (unsigned step = 0; step <= phase; step++) {
            panel_fill_column(BIBA_LED_PANEL_LEFT_IDX,
                              PANEL_COLS - 1u - step, ar, ag, ab);
            panel_fill_column(BIBA_LED_PANEL_RIGHT_IDX, step, ar, ag, ab);
        }
        return;
    }

    /* phase COLS and COLS+2 are lit; the odd tail phases stay blank
     * (the frame is already cleared). */
    if (phase == PANEL_COLS || phase == PANEL_COLS + 2u) {
        frame_fill(ar, ag, ab);
    }
}

/* --- Effect: emergency lightbar (beacon) -------------------------------- *
 *
 * 16 slots of BIBA_LED_PANEL_BEACON_SLOT_MS. Left panel flashes blue
 * twice, pause, right panel flashes red twice, pause: the alternating
 * double-flash of a real light bar. Bit 0 = left panel lit, bit 1 =
 * right panel lit.
 */
#define BEACON_SLOTS 16u

static const uint8_t s_beacon_pattern[BEACON_SLOTS] = {
    1u, 0u, 1u, 0u,   /* left  double flash */
    0u, 0u, 0u, 0u,   /* dark               */
    2u, 0u, 2u, 0u,   /* right double flash */
    0u, 0u, 0u, 0u,   /* dark               */
};

static void render_beacon(uint32_t now_ms)
{
    const unsigned slot =
        (now_ms / BIBA_LED_PANEL_BEACON_SLOT_MS) % BEACON_SLOTS;
    const uint8_t bits = s_beacon_pattern[slot];

    frame_clear();
    if ((bits & 1u) != 0u) {
        panel_fill(BIBA_LED_PANEL_LEFT_IDX, 0u, 0u, 255u);   /* blue */
    }
    if ((bits & 2u) != 0u) {
        panel_fill(BIBA_LED_PANEL_RIGHT_IDX, 255u, 0u, 0u);  /* red  */
    }
}

/* --- Effect: perimeter chase (trim mode) -------------------------------- *
 *
 * A yellow dot with a two-cell fading tail runs around the border of
 * both panels. Deliberately unlike every other effect at a glance:
 * trim is a bench state, not a driving state.
 */
#define PERIM_LEN ((PANEL_COLS + PANEL_ROWS) * 2u - 4u)

#if (BIBA_LED_PANEL_COLS >= 2) && (BIBA_LED_PANEL_ROWS >= 2)
/* Walk the border clockwise starting at the top-left corner. */
static void perimeter_cell(unsigned k, unsigned *x, unsigned *y)
{
    if (k < PANEL_COLS) {                                /* top, L to R  */
        *x = k;
        *y = 0u;
    } else if (k < PANEL_COLS + PANEL_ROWS - 1u) {       /* right, down  */
        *x = PANEL_COLS - 1u;
        *y = k - PANEL_COLS + 1u;
    } else if (k < 2u * PANEL_COLS + PANEL_ROWS - 2u) {  /* bottom, R to L */
        *x = (2u * PANEL_COLS + PANEL_ROWS - 3u) - k;
        *y = PANEL_ROWS - 1u;
    } else {                                             /* left, up     */
        *x = 0u;
        *y = PERIM_LEN - k;
    }
}
#endif

static void render_trim(uint32_t now_ms)
{
    frame_clear();

#if (BIBA_LED_PANEL_COLS < 2) || (BIBA_LED_PANEL_ROWS < 2)
    /* A one-wide or one-tall panel has no perimeter to run around. */
    (void)now_ms;
    frame_fill(255u, 200u, 0u);
#else
    const unsigned head = (now_ms / BIBA_LED_PANEL_TRIM_STEP_MS) % PERIM_LEN;
    /* Head at full, then two tail cells at 40 % and 15 %. */
    static const unsigned tail_num[3] = { 255u, 102u, 38u };

    for (unsigned t = 0; t < 3u; t++) {
        unsigned k = (head + PERIM_LEN - t) % PERIM_LEN;
        unsigned x = 0u, y = 0u;
        perimeter_cell(k, &x, &y);
        uint8_t r = scale8(255u, tail_num[t]);
        uint8_t g = scale8(200u, tail_num[t]);
        for (unsigned p = 0; p < PANEL_COUNT; p++) {
            px_set(p, x, y, r, g, 0u);
        }
    }
#endif
}

/* --- Public entry point ------------------------------------------------- */

void biba_led_panel_render(biba_led_mode_t mode, uint32_t now_ms,
                           biba_rgb_t *out, size_t count)
{
    if (out == NULL || count == 0u) return;

    switch (mode) {
    case BIBA_LED_MODE_FAILSAFE: {
        bool on = ((now_ms / BIBA_LED_PANEL_FAILSAFE_MS) & 1u) == 0u;
        if (on) {
            frame_fill(255u, 0u, 0u);
        } else {
            frame_clear();
        }
        break;
    }
    case BIBA_LED_MODE_TRIM:
        render_trim(now_ms);
        break;
    case BIBA_LED_MODE_REVERSE:
        frame_fill(255u, 0u, 0u);
        break;
    case BIBA_LED_MODE_FORWARD:
        frame_fill(255u, 255u, 255u);
        break;
    case BIBA_LED_MODE_BEACON:
        render_beacon(now_ms);
        break;
    case BIBA_LED_MODE_ARMED_IDLE: {
        const uint8_t d = (uint8_t)BIBA_LED_PANEL_DRL_LEVEL;
        frame_fill(d, d, d);
        break;
    }
    case BIBA_LED_MODE_DISARMED:
    default:
        render_service(now_ms);
        break;
    }

    /* Master brightness, applied once, to everything. */
    const unsigned n = (count < (size_t)PANEL_TOTAL) ? (unsigned)count
                                                     : PANEL_TOTAL;
    for (unsigned i = 0; i < n; i++) {
        out[i].r = scale8(s_frame[i].r, BIBA_LED_PANEL_BRIGHTNESS);
        out[i].g = scale8(s_frame[i].g, BIBA_LED_PANEL_BRIGHTNESS);
        out[i].b = scale8(s_frame[i].b, BIBA_LED_PANEL_BRIGHTNESS);
    }
}
