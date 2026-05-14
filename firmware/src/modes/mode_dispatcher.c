#include "mode_dispatcher.h"

#include "biba_config.h"
#include "hal/biba_hal.h"
#include "drivers/bts7960.h"
#include "drivers/imu.h"

/* --- Build-time mode selection ------------------------------------------ */

#if defined(BIBA_MODE_STANDALONE)
#  define BIBA_BUILT_IN_MODE BIBA_MODE_STANDALONE_E
#  define BIBA_BUILT_IN_MODE_FIXED 1
#elif defined(BIBA_MODE_COMPANION)
#  define BIBA_BUILT_IN_MODE BIBA_MODE_COMPANION_E
#  define BIBA_BUILT_IN_MODE_FIXED 1
#elif defined(BIBA_MODE_COMBINED)
#  define BIBA_BUILT_IN_MODE BIBA_MODE_STANDALONE_E /* default when MODE_SEL high */
#  define BIBA_BUILT_IN_MODE_FIXED 0
#else
#  error "One of BIBA_MODE_STANDALONE / BIBA_MODE_COMPANION / BIBA_MODE_COMBINED must be defined"
#endif

static biba_mode_t s_active_mode;

void biba_mode_dispatcher_boot(void)
{
    biba_hal_init();
    biba_bts7960_set_enabled(false);
    (void)biba_imu_probe();

#if BIBA_BUILT_IN_MODE_FIXED
    s_active_mode = BIBA_BUILT_IN_MODE;
#else
    s_active_mode = biba_hal_mode_sel_is_companion()
                      ? BIBA_MODE_COMPANION_E
                      : BIBA_MODE_STANDALONE_E;
#endif

    if (s_active_mode == BIBA_MODE_STANDALONE_E) {
        biba_mode_standalone_init();
    } else {
        biba_mode_companion_init();
    }
}

void biba_mode_dispatcher_run_forever(void)
{
    for (;;) {
        if (s_active_mode == BIBA_MODE_STANDALONE_E) {
            biba_mode_standalone_tick();
        } else {
            biba_mode_companion_tick();
        }
    }
}
