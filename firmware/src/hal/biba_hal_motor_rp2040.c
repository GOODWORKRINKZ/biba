/* Motor PWM HAL for RP2040 (BiBa firmware).
 *
 * Uses pico-sdk hardware PWM.  Left pair (L_RPWM/L_LPWM) is on PWM
 * slice 1 (GP2/GP3); right pair (R_RPWM/R_LPWM) is on PWM slice 2
 * (GP4/GP5).  Both channels of a slice share the same wrap value
 * (i.e. the same carrier frequency), so per-channel independent
 * carriers are not supported — motor-audio functions return false.
 *
 * 20 kHz carrier at 125 MHz system clock:
 *   wrap = 125 000 000 / 20 000 − 1 = 6249
 *   divider = 1.0 (integer)
 */

#include "biba_hal.h"

#include "biba_board.h"
#include "biba_config.h"

#include "hardware/pwm.h"
#include "hardware/gpio.h"

#include <math.h>

/* Wrap value for the chosen carrier frequency. */
#define PWM_WRAP ((uint16_t)((BIBA_SYS_CLOCK_HZ / BIBA_PWM_FREQUENCY_HZ) - 1u))

static uint s_slice_l;   /* slice for left  pair (GP2/GP3) */
static uint s_slice_r;   /* slice for right pair (GP4/GP5) */

/* Convert absolute duty [0.0, 1.0] to a 16-bit compare value. */
static uint16_t duty_to_level(float duty_abs)
{
    if (duty_abs < 0.0f) duty_abs = 0.0f;
    if (duty_abs > 1.0f) duty_abs = 1.0f;
    return (uint16_t)lroundf(duty_abs * (float)PWM_WRAP);
}

void biba_hal_motor_pwm_init(void)
{
    /* Route GPIO pins to PWM function. */
    gpio_set_function(BIBA_PIN_LEFT_RPWM_GPIO,  GPIO_FUNC_PWM);
    gpio_set_function(BIBA_PIN_LEFT_LPWM_GPIO,  GPIO_FUNC_PWM);
    gpio_set_function(BIBA_PIN_RIGHT_RPWM_GPIO, GPIO_FUNC_PWM);
    gpio_set_function(BIBA_PIN_RIGHT_LPWM_GPIO, GPIO_FUNC_PWM);

    s_slice_l = pwm_gpio_to_slice_num(BIBA_PIN_LEFT_RPWM_GPIO);
    s_slice_r = pwm_gpio_to_slice_num(BIBA_PIN_RIGHT_RPWM_GPIO);

    pwm_config cfg = pwm_get_default_config();
    pwm_config_set_clkdiv_int(&cfg, 1u);
    pwm_config_set_wrap(&cfg, PWM_WRAP);

    pwm_init(s_slice_l, &cfg, true);
    pwm_init(s_slice_r, &cfg, true);

    /* All channels start at zero duty. */
    pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO,  0u);
    pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO,  0u);
    pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
    pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, 0u);
}

void biba_hal_motor_pwm_left(float duty)
{
    if (duty > 0.0f) {
        pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO, duty_to_level(duty));
        pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO, 0u);
    } else if (duty < 0.0f) {
        pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO, 0u);
        pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO, duty_to_level(-duty));
    } else {
        pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO, 0u);
        pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO, 0u);
    }
}

void biba_hal_motor_pwm_right(float duty)
{
    if (duty > 0.0f) {
        pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, duty_to_level(duty));
        pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, 0u);
    } else if (duty < 0.0f) {
        pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, duty_to_level(-duty));
    } else {
        pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, 0u);
    }
}

/* Motor audio: both channels of a slice share one wrap value so
 * independent frequencies are not possible without remapping pins to
 * separate slices.  Return false to indicate unsupported. */
bool biba_hal_motor_audio_set_all(const uint32_t freq_hz[4],
                                  const float    duty_unit[4])
{
    (void)freq_hz; (void)duty_unit;
    return false;
}

bool biba_hal_motor_audio_begin(void) { return false; }
bool biba_hal_motor_audio_end(void)   { return false; }
