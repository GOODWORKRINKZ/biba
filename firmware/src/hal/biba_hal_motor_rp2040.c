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
#include "pico/time.h"

#include <math.h>

/* Wrap value for the chosen carrier frequency. */
#define PWM_WRAP ((uint16_t)((BIBA_SYS_CLOCK_HZ / BIBA_PWM_FREQUENCY_HZ) - 1u))

static uint s_slice_l;   /* slice for left  pair (GP2/GP3) */
static uint s_slice_r;   /* slice for right pair (GP6/GP7) */
static bool s_audio_mode = false;
static volatile bool s_pcm_mode = false;

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
    if (s_audio_mode || s_pcm_mode) return;   /* audio/PCM owns the PWM hardware */
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
    if (s_audio_mode || s_pcm_mode) return;   /* audio/PCM owns the PWM hardware */
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
    /* Restore traction carrier, clock divider, and normal polarity. */
    pwm_set_clkdiv(s_slice_l, 1.0f);
    pwm_set_clkdiv(s_slice_r, 1.0f);
    pwm_set_wrap(s_slice_l, PWM_WRAP);
    pwm_set_wrap(s_slice_r, PWM_WRAP);
    pwm_set_output_polarity(s_slice_l, false, false);
    pwm_set_output_polarity(s_slice_r, false, false);
    s_audio_mode = false;
    return true;
}

/* Audio wrap: fixed at 2499 counts.
 * Clock divider is varied per-note so actual frequency = SYSCLK / (div * 2500).
 * With div in [1..255] this covers ~196 Hz (G3) .. 50 kHz, covering all
 * musical notes used in the melody catalog.
 *
 * SILENCE BUG NOTE: channel B (LPWM) has polarity inversion active.
 * Setting level=0 on an inverted channel means "HIGH when counter<0" = never
 * HIGH normally → after inversion = ALWAYS HIGH = 100% reverse drive!
 * Fix: for silence, set RPWM level=0 AND LPWM level=(AUDIO_WRAP+1).
 * Since counter only reaches AUDIO_WRAP=2499, level=2500 is never reached
 * → raw output always HIGH → after inversion = always LOW = silence. */
#define AUDIO_WRAP  2499u

bool biba_hal_motor_audio_set_all(const uint32_t freq_hz[4],
                                  const float    duty_unit[4])
{
    /* --- Left motor (slice l, channels A=RPWM / B=LPWM inverted) --- */
    uint32_t lf = freq_hz[0];
    if (lf > 0u) {
        float div = (float)BIBA_SYS_CLOCK_HZ / ((float)lf * (float)(AUDIO_WRAP + 1u));
        if (div < 1.0f)   div = 1.0f;
        if (div > 255.0f) div = 255.0f;
        pwm_set_clkdiv(s_slice_l, div);
        pwm_set_wrap(s_slice_l, AUDIO_WRAP);
        uint16_t lvl = (uint16_t)(duty_unit[0] * (float)(AUDIO_WRAP + 1u));
        /* Both RPWM and LPWM get the same level; inverted polarity on LPWM
         * makes them complementary → true push-pull, zero net torque. */
        pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO, lvl);
        pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO, lvl);
    } else {
        /* Silence on inverted channel: level > wrap → raw always HIGH
         * → after inversion always LOW.  RPWM level=0 → always LOW. */
        pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO, 0u);
        pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO, (uint16_t)(AUDIO_WRAP + 1u));
    }

    /* --- Right motor (slice r, channels A=RPWM / B=LPWM inverted) --- */
    uint32_t rf = freq_hz[2];
    if (rf > 0u) {
        float div = (float)BIBA_SYS_CLOCK_HZ / ((float)rf * (float)(AUDIO_WRAP + 1u));
        if (div < 1.0f)   div = 1.0f;
        if (div > 255.0f) div = 255.0f;
        pwm_set_clkdiv(s_slice_r, div);
        pwm_set_wrap(s_slice_r, AUDIO_WRAP);
        uint16_t lvl = (uint16_t)(duty_unit[2] * (float)(AUDIO_WRAP + 1u));
        pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, lvl);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, lvl);
    } else {
        pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, (uint16_t)(AUDIO_WRAP + 1u));
    }

    return true;
}

/* -----------------------------------------------------------------------
 * PCM-over-PWM playback — BIPOLAR mode (≡ Python play_bipolar_samples).
 *
 * sample > 128 → RPWM = (sample-128)/127 × wrap, LPWM = 0   (forward)
 * sample < 128 → RPWM = 0,  LPWM = (128-sample)/128 × wrap  (reverse)
 * sample = 128 → RPWM = 0,  LPWM = 0                        (silence)
 *
 * Full coil swing ±Vbat — twice the amplitude of the old DC-bias scheme.
 * No polarity inversion; traction PWM is blocked while active.
 * ----------------------------------------------------------------------- */

static volatile bool          s_pcm_mode;   /* defined at top of file */
static const uint8_t         *s_pcm_samples;
static uint32_t               s_pcm_count;
static volatile uint32_t      s_pcm_pos;
static struct repeating_timer s_pcm_timer;

static bool s_pcm_isr(struct repeating_timer *t)
{
    (void)t;
    if (s_pcm_pos >= s_pcm_count) {
        pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO,  0u);
        pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO,  0u);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, 0u);
        s_pcm_mode = false;
        return false;   /* cancels the repeating timer */
    }
    uint8_t  s = s_pcm_samples[s_pcm_pos++];
    uint16_t lvl;
    if (s > 128u) {
        lvl = (uint16_t)((uint32_t)(s - 128u) * PWM_WRAP / 127u);
        pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO,  lvl);
        pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO,  0u);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, lvl);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, 0u);
    } else if (s < 128u) {
        lvl = (uint16_t)((uint32_t)(128u - s) * PWM_WRAP / 128u);
        pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO,  0u);
        pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO,  lvl);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, lvl);
    } else {
        pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO,  0u);
        pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO,  0u);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
        pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, 0u);
    }
    return true;
}

bool biba_hal_motor_pcm_play(const uint8_t *samples, uint32_t count,
                              uint32_t rate_hz)
{
    if (s_audio_mode) return false;   /* melody player owns PWM */

    if (s_pcm_mode) {
        cancel_repeating_timer(&s_pcm_timer);
        s_pcm_mode = false;
    }

    s_pcm_samples = samples;
    s_pcm_count   = count;
    s_pcm_pos     = 0;

    /* Silence all channels before starting (bipolar: idle = all zero). */
    pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO,  0u);
    pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO,  0u);
    pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
    pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, 0u);

    s_pcm_mode = true;
    int32_t period_us = -(int32_t)(1000000u / rate_hz);
    add_repeating_timer_us(period_us, s_pcm_isr, NULL, &s_pcm_timer);
    return true;
}

bool biba_hal_motor_pcm_active(void)
{
    return s_pcm_mode;
}

void biba_hal_motor_pcm_stop(void)
{
    if (s_pcm_mode) {
        cancel_repeating_timer(&s_pcm_timer);
        s_pcm_mode = false;
    }
    pwm_set_gpio_level(BIBA_PIN_LEFT_RPWM_GPIO,  0u);
    pwm_set_gpio_level(BIBA_PIN_LEFT_LPWM_GPIO,  0u);
    pwm_set_gpio_level(BIBA_PIN_RIGHT_RPWM_GPIO, 0u);
    pwm_set_gpio_level(BIBA_PIN_RIGHT_LPWM_GPIO, 0u);
}
