/* Motor PWM HAL for RP2040 (BiBa firmware).
 *
 * Uses pico-sdk hardware PWM.  Left pair (L_RPWM/L_LPWM) is on PWM
 * slice 1 (GP2/GP3); right pair (R_RPWM/R_LPWM) is on PWM slice 3
 * (GP6/GP7).  Both channels of a slice share one counter, so they
 * share the carrier frequency.
 *
 * AUDIO MODE (biba_hal_motor_audio_begin):
 *   Channel B (LPWM) is inverted via pwm_set_output_polarity.
 *   Setting both compare values to 50% produces true push-pull:
 *     counter < 50%  → RPWM=1 LPWM=0 → H-bridge drives fwd
 *     counter ≥ 50%  → RPWM=0 LPWM=1 → H-bridge drives rev
 *   Result: pure AC through the motor coil at the audio frequency.
 *   This is louder than the Python beat-frequency trick and requires
 *   no per-channel timer — the inversion does all the work.
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
static uint s_slice_r;   /* slice for right pair (GP6/GP7) */
static bool s_audio_mode = false;

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
    if (s_audio_mode) return;   /* audio owns the PWM hardware */
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
    if (s_audio_mode) return;   /* audio owns the PWM hardware */
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

/* -----------------------------------------------------------------------
 * Audio mode: hardware push-pull at the requested note frequency.
 *
 * Channel layout in audio mode (after motor_audio_begin):
 *   freq_hz[0] / duty_unit[0]  →  left  motor (slice l)
 *   freq_hz[2] / duty_unit[2]  →  right motor (slice r)
 *   channels 1 and 3 are ignored (LPWM is driven by inversion)
 * ----------------------------------------------------------------------- */

bool biba_hal_motor_audio_begin(void)
{
    /* Silence traction outputs before switching mode. */
    pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO,  0u);
    pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO,  0u);
    pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
    pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, 0u);
    /* Invert channel B (LPWM) on both slices so that setting RPWM and
     * LPWM to the same duty produces complementary drive (push-pull). */
    pwm_set_output_polarity(s_slice_l, false, true);
    pwm_set_output_polarity(s_slice_r, false, true);
    s_audio_mode = true;
    return true;
}

bool biba_hal_motor_audio_end(void)
{
    /* Silence before restoring traction settings. */
    pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO,  0u);
    pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO,  0u);
    pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
    pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, 0u);
    /* Restore traction carrier and normal (non-inverted) polarity. */
    pwm_set_wrap(s_slice_l, PWM_WRAP);
    pwm_set_wrap(s_slice_r, PWM_WRAP);
    pwm_set_output_polarity(s_slice_l, false, false);
    pwm_set_output_polarity(s_slice_r, false, false);
    s_audio_mode = false;
    return true;
}

bool biba_hal_motor_audio_set_all(const uint32_t freq_hz[4],
                                  const float    duty_unit[4])
{
    /* --- Left motor (slice l, channels 0/1) --- */
    uint32_t lf = freq_hz[0];
    if (lf > 0u) {
        uint32_t wrap = (BIBA_SYS_CLOCK_HZ / lf);
        if (wrap > 0u) wrap--; else wrap = 0u;
        if (wrap > 65535u) wrap = 65535u;
        pwm_set_wrap(s_slice_l, (uint16_t)wrap);
        /* Both RPWM and LPWM set to the same level; LPWM is inverted
         * (set in audio_begin) so the effective outputs are push-pull. */
        uint16_t lvl = (uint16_t)(duty_unit[0] * (float)(wrap + 1u));
        pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO, lvl);
        pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO, lvl);
    } else {
        pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO, 0u);
        pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO, 0u);
    }

    /* --- Right motor (slice r, channels 2/3) --- */
    uint32_t rf = freq_hz[2];
    if (rf > 0u) {
        uint32_t wrap = (BIBA_SYS_CLOCK_HZ / rf);
        if (wrap > 0u) wrap--; else wrap = 0u;
        if (wrap > 65535u) wrap = 65535u;
        pwm_set_wrap(s_slice_r, (uint16_t)wrap);
        uint16_t lvl = (uint16_t)(duty_unit[2] * (float)(wrap + 1u));
        pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, lvl);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, lvl);
    } else {
        pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, 0u);
    }

    return true;
}
