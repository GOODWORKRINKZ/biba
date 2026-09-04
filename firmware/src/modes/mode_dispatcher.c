#include "mode_dispatcher.h"

#include "biba_config.h"
#include "hal/biba_hal.h"
#include "drivers/imu.h"

#if BIBA_TARGET_HAS_BTS7960_2CH
#  include "drivers/bts7960.h"
#elif BIBA_TARGET_HAS_BLDC_2CH
#  include "drivers/odrive_can.h"
#endif

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

    /* Motor bring-up.  On the brushed-DC target we keep BTS7960's
     * enable pairs low; on the BLDC target the ODrive driver is
     * already running from biba_hal_motor_pwm_init() inside hal_init
     * and we ask it to keep the setpoints zero for now.  See
     * ADR-0001 §1.5. */
#if BIBA_TARGET_HAS_BTS7960_2CH
    biba_bts7960_set_enabled(false);
#elif BIBA_TARGET_HAS_BLDC_2CH
    biba_odrive_set_enabled(false);
    biba_odrive_drive(0.0f, 0.0f);
#endif

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
