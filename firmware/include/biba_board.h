#ifndef BIBA_BOARD_H
#define BIBA_BOARD_H

/* Pin map shim.
 *
 * The actual pin definitions live in targets/<TARGET>/target.h.
 * PlatformIO injects `-Itargets/<TARGET>` for the selected env, so the
 * right `target.h` resolves automatically. See targets/README.md for
 * how to add a new board.
 *
 * Portable code should always include this header, never `target.h`
 * directly.
 */

#include "target.h"

/* Capability fallbacks.
 *
 * Targets opt *in* to optional hardware by defining these in their
 * target.h. Declaring the default here (rather than in every `#if`)
 * means a target that predates a feature keeps compiling untouched. */
#ifndef BIBA_HAS_RGB_LED
#  define BIBA_HAS_RGB_LED    0   /* on-board WS2812 status pixel */
#endif
#ifndef BIBA_HAS_LED_PANEL
#  define BIBA_HAS_LED_PANEL  0   /* front WS2812 indicator panels */
#endif

#endif /* BIBA_BOARD_H */
