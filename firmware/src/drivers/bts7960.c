#include "bts7960.h"

#include "hal/biba_hal.h"
#include "biba_config.h"

void biba_bts7960_set_enabled(bool enabled)
{
    biba_hal_left_enable(enabled);
    biba_hal_right_enable(enabled);
    if (!enabled) {
        biba_hal_motor_pwm_left(0.0f);
        biba_hal_motor_pwm_right(0.0f);
    }
}

void biba_bts7960_drive(float left_duty, float right_duty)
{
    biba_hal_motor_pwm_left( left_duty  * BIBA_LEFT_MOTOR_DIR);
    biba_hal_motor_pwm_right(right_duty * BIBA_RIGHT_MOTOR_DIR);
}
