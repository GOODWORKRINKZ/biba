#include "motor_bridge.h"

#include "biba_config.h"
#include "drivers/bts7960.h"
#include "hal/biba_hal.h"

void biba_motor_bridge_rearm(void)
{
    biba_bts7960_thermal_reset(BIBA_BTS7960_RESET_PULSE_US);
    biba_hal_ssr_set(true);
}