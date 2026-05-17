#include "bts7960.h"

#include "hal/biba_hal.h"
#include "biba_config.h"

static uint32_t thermal_reset_pulse_us(uint32_t pulse_us)
{
    if (pulse_us < BIBA_BTS7960_RESET_PULSE_US) {
        return BIBA_BTS7960_RESET_PULSE_US;
    }
    return pulse_us;
}

static void set_motor_pwm_zero(void)
{
    biba_hal_motor_pwm_left(0.0f);
    biba_hal_motor_pwm_right(0.0f);
}

void biba_bts7960_set_enabled(bool enabled)
{
    biba_hal_left_enable(enabled);
    biba_hal_right_enable(enabled);
    if (!enabled) {
        set_motor_pwm_zero();
    }
}

void biba_bts7960_drive(float left_duty, float right_duty)
{
    biba_hal_motor_pwm_left( left_duty  * BIBA_LEFT_MOTOR_DIR);
    biba_hal_motor_pwm_right(right_duty * BIBA_RIGHT_MOTOR_DIR);
}

void biba_bts7960_thermal_reset(uint32_t pulse_us)
{
    uint32_t hold_us = thermal_reset_pulse_us(pulse_us);

    set_motor_pwm_zero();
    biba_hal_left_enable(false);
    biba_hal_right_enable(false);
    biba_hal_delay_us(hold_us);
    biba_hal_left_enable(true);
    biba_hal_right_enable(true);
}
