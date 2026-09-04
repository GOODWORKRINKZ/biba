#ifndef BIBA_APP_LED_PANEL_H
#define BIBA_APP_LED_PANEL_H

/* Indicator LED panels — pure rendering layer.
 *
 * Two WS2812 matrices are mounted at the front-left and front-right
 * corners of the robot and daisy-chained onto a single data line. The
 * three driving states follow car tail-light convention — dim red
 * rolling, bright red standing, white reversing — so an observer reads
 * them without being told what they mean.
 *
 * This module owns nothing but arithmetic: given the machine state and a
 * millisecond timestamp it fills a frame buffer. Pushing that buffer at
 * the wire is `biba_hal_led_strip_write()`; deciding *when* to push is
 * the caller's job (mode_standalone repaints at
 * BIBA_LED_PANEL_REFRESH_MS).
 *
 * Keeping it a pure function of (mode, now_ms) means every effect is
 * reproducible on the host and covered by test/test_led_panel.
 *
 * Geometry, colours and effect timings live in biba_config.h so a
 * different panel size is a config change, not a code change.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "biba_config.h"

#ifdef __cplusplus
extern "C" {
#endif

/* One pixel, in the order the HAL expects on the wire-facing side
 * (the GRB swap WS2812 needs happens in the HAL, not here). */
typedef struct {
    uint8_t r;
    uint8_t g;
    uint8_t b;
} biba_rgb_t;

/* What the panels are showing. Highest-priority state wins — see
 * biba_led_panel_mode(). */
typedef enum {
    BIBA_LED_MODE_DISARMED = 0, /* amber road-service arrow board       */
    BIBA_LED_MODE_BEACON,       /* blue/red emergency lightbar          */
    BIBA_LED_MODE_ARMED_IDLE,   /* bright red — armed, standing still   */
    BIBA_LED_MODE_FORWARD,      /* dim red — rolling forward            */
    BIBA_LED_MODE_REVERSE,      /* solid white — reversing              */
    BIBA_LED_MODE_TRIM,         /* yellow perimeter chase               */
    BIBA_LED_MODE_FAILSAFE,     /* red strobe                           */
    BIBA_LED_MODE_COUNT
} biba_led_mode_t;

/* Machine state, mirrored from the mode-standalone tick. `forward` and
 * `reversing` are the both-wheels-same-sign flags — a pivot turn sets
 * neither and falls through to ARMED_IDLE. */
typedef struct {
    bool failsafe;
    bool armed;
    bool trim;
    bool forward;
    bool reversing;
    bool beacon;
} biba_led_inputs_t;

/* Resolve the inputs into exactly one mode.
 *
 * Priority, highest first:
 *   failsafe > trim > reverse > forward > beacon > armed idle > disarmed
 *
 * Beacon deliberately sits *below* the two driving states: while the
 * robot is actually moving the operator behind it needs to read
 * direction, not a lightbar. A stopped-but-armed robot with the beacon
 * switch up shows the lightbar. */
biba_led_mode_t biba_led_panel_mode(const biba_led_inputs_t *in);

/* Map a logical cell to its index in the daisy chain.
 *
 * `panel` is a chain position (BIBA_LED_PANEL_LEFT_IDX /
 * _RIGHT_IDX), `x` is the column 0..COLS-1 counted left→right as seen
 * by an observer standing in front of the robot, `y` the row 0..ROWS-1
 * counted top→bottom. Serpentine wiring and the two flip flags from
 * biba_config.h are applied here and nowhere else.
 *
 * Out-of-range arguments return BIBA_LED_PANEL_TOTAL (one past the
 * end) so callers can cheaply reject them. */
unsigned biba_led_panel_index(unsigned panel, unsigned x, unsigned y);

/* Render one frame. Writes exactly min(count, BIBA_LED_PANEL_TOTAL)
 * pixels; `out` is never read. Master brightness
 * (BIBA_LED_PANEL_BRIGHTNESS) is applied as the final step, so effect
 * code below works in full 0..255 intent. */
void biba_led_panel_render(biba_led_mode_t mode, uint32_t now_ms,
                           biba_rgb_t *out, size_t count);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_APP_LED_PANEL_H */
