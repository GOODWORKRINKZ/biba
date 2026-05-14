/* Motor PWM HAL — target-aware topology selection.
 *
 * Two implementations live here side-by-side, guarded by the target ABI
 * flag `BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM`:
 *
 *   0 -> All four motor PWM lines share a single timer (TIM1). One
 *        carrier frequency for the whole bridge; fine for traction, no
 *        motor-audio. This is what BLUEPILL_F103C8 gets.
 *
 *   1 -> Each of the four PWM lines is on its own hardware timer, so
 *        they can run four independent carriers at once. In traction
 *        mode they are still driven at the same BIBA_PWM_FREQUENCY_HZ
 *        carrier, so the BTS7960 drive path is byte-compatible with the
 *        single-timer variant. The motor-audio API programs
 *        PSC/ARR/CCR independently on each channel. This is what
 *        BIBA_F103_REV_A gets.
 *
 * The file is only compiled into the firmware envs; the native_test env
 * excludes src/hal/ via platformio.ini's src_filter.
 */

#include "biba_hal.h"

#include "biba_board.h"
#include "biba_config.h"

#include "stm32f1xx_hal.h"

#include <math.h>

/* --- Traction-mode helpers shared by both variants --------------------- */

/* TIM1 break/dead-time configuration shared by both PWM topologies.
 * BTS7960 needs a guaranteed dead-time between RPWM/LPWM transitions to
 * prevent shoot-through, so we always program the DTG bits — even on the
 * per-channel topology where the comment used to claim the HAL would
 * "force one side to 0". */
static void tim1_apply_break_dead_time(TIM_HandleTypeDef *h)
{
    TIM_BreakDeadTimeConfigTypeDef bd = {0};
    bd.OffStateRunMode  = TIM_OSSR_DISABLE;
    bd.OffStateIDLEMode = TIM_OSSI_DISABLE;
    bd.LockLevel        = TIM_LOCKLEVEL_OFF;
    uint32_t dtg = (uint32_t)(((uint64_t)BIBA_PWM_DEADTIME_NS *
                               (BIBA_SYS_CLOCK_HZ / 1000000ULL) +
                               999ULL) / 1000ULL);
    if (dtg > 127u) dtg = 127u;
    bd.DeadTime        = (uint8_t)dtg;
    bd.BreakState      = TIM_BREAK_DISABLE;
    bd.AutomaticOutput = TIM_AUTOMATICOUTPUT_ENABLE;
    HAL_TIMEx_ConfigBreakDeadTime(h, &bd);
}

static uint32_t duty_to_compare(uint32_t arr, float duty_abs)
{
    if (duty_abs < 0.0f) duty_abs = 0.0f;
    if (duty_abs > 1.0f) duty_abs = 1.0f;
    return (uint32_t)lroundf(duty_abs * (float)arr);
}

/* ============================================================ */
#if BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM
/* ============================================================ */

/* One TIM handle per motor PWM line. */
static TIM_HandleTypeDef s_h_l_rpwm;
static TIM_HandleTypeDef s_h_l_lpwm;
static TIM_HandleTypeDef s_h_r_rpwm;
static TIM_HandleTypeDef s_h_r_lpwm;

typedef struct {
    TIM_HandleTypeDef *h;
    TIM_TypeDef       *instance;
    uint32_t           channel;
    GPIO_TypeDef      *port;
    uint16_t           pin;
} motor_pwm_binding_t;

static motor_pwm_binding_t s_bindings[4] = {
    { &s_h_l_rpwm, BIBA_PWM_LEFT_RPWM_TIM,  BIBA_PWM_LEFT_RPWM_CHANNEL,
      BIBA_PIN_LEFT_RPWM_PORT,  BIBA_PIN_LEFT_RPWM_PIN },
    { &s_h_l_lpwm, BIBA_PWM_LEFT_LPWM_TIM,  BIBA_PWM_LEFT_LPWM_CHANNEL,
      BIBA_PIN_LEFT_LPWM_PORT,  BIBA_PIN_LEFT_LPWM_PIN },
    { &s_h_r_rpwm, BIBA_PWM_RIGHT_RPWM_TIM, BIBA_PWM_RIGHT_RPWM_CHANNEL,
      BIBA_PIN_RIGHT_RPWM_PORT, BIBA_PIN_RIGHT_RPWM_PIN },
    { &s_h_r_lpwm, BIBA_PWM_RIGHT_LPWM_TIM, BIBA_PWM_RIGHT_LPWM_CHANNEL,
      BIBA_PIN_RIGHT_LPWM_PORT, BIBA_PIN_RIGHT_LPWM_PIN },
};

static void enable_binding_clock(motor_pwm_binding_t *b)
{
    /* Per-target macros avoid a big switch over the timer instance. */
    if      (b == &s_bindings[0]) { BIBA_PWM_LEFT_RPWM_CLK_ENABLE();  BIBA_PWM_LEFT_RPWM_AF_REMAP();  }
    else if (b == &s_bindings[1]) { BIBA_PWM_LEFT_LPWM_CLK_ENABLE();  BIBA_PWM_LEFT_LPWM_AF_REMAP();  }
    else if (b == &s_bindings[2]) { BIBA_PWM_RIGHT_RPWM_CLK_ENABLE(); BIBA_PWM_RIGHT_RPWM_AF_REMAP(); }
    else                           { BIBA_PWM_RIGHT_LPWM_CLK_ENABLE(); BIBA_PWM_RIGHT_LPWM_AF_REMAP(); }
}

static void init_binding(motor_pwm_binding_t *b, uint32_t arr)
{
    enable_binding_clock(b);

    /* GPIO AF push-pull for this line. */
    GPIO_InitTypeDef g = {0};
    g.Pin   = b->pin;
    g.Mode  = GPIO_MODE_AF_PP;
    g.Pull  = GPIO_NOPULL;
    g.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(b->port, &g);

    /* PWM1, up-counting, ARR-preload so PSC/ARR updates become effective
     * on the next UEV instead of mid-period. */
    b->h->Instance               = b->instance;
    b->h->Init.Prescaler         = 0;
    b->h->Init.CounterMode       = TIM_COUNTERMODE_UP;
    b->h->Init.Period            = arr;
    b->h->Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    b->h->Init.RepetitionCounter = 0;
    b->h->Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    HAL_TIM_PWM_Init(b->h);

    TIM_OC_InitTypeDef oc = {0};
    oc.OCMode     = TIM_OCMODE_PWM1;
    oc.Pulse      = 0;
    oc.OCPolarity = TIM_OCPOLARITY_HIGH;
    oc.OCFastMode = TIM_OCFAST_DISABLE;
    HAL_TIM_PWM_ConfigChannel(b->h, &oc, b->channel);

    /* TIM1 is the only advanced-control timer in the bunch; it needs
     * MOE (main output enable) turned on AND a non-zero dead-time so the
     * BTS7960 cannot see overlapping RPWM/LPWM commands. TIM2/3/4 are
     * general-purpose and have no break/MOE block — software guarantees
     * dead-time on those by always zeroing the inactive side first in
     * set_channel_pair() below. */
    if (b->instance == TIM1) {
        tim1_apply_break_dead_time(b->h);
    }

    HAL_TIM_PWM_Start(b->h, b->channel);
}

void biba_hal_motor_pwm_init(void)
{
    uint32_t arr = (BIBA_SYS_CLOCK_HZ / BIBA_PWM_FREQUENCY_HZ) - 1u;
    for (unsigned i = 0; i < 4; ++i) {
        init_binding(&s_bindings[i], arr);
    }
}

static void set_channel_pair(motor_pwm_binding_t *rpwm,
                             motor_pwm_binding_t *lpwm,
                             float duty)
{
    if (duty >  1.0f) duty =  1.0f;
    if (duty < -1.0f) duty = -1.0f;

    uint32_t arr_r = __HAL_TIM_GET_AUTORELOAD(rpwm->h);
    uint32_t arr_l = __HAL_TIM_GET_AUTORELOAD(lpwm->h);

    if (duty >= 0.0f) {
        __HAL_TIM_SET_COMPARE(lpwm->h, lpwm->channel, 0);
        __HAL_TIM_SET_COMPARE(rpwm->h, rpwm->channel, duty_to_compare(arr_r,  duty));
    } else {
        __HAL_TIM_SET_COMPARE(rpwm->h, rpwm->channel, 0);
        __HAL_TIM_SET_COMPARE(lpwm->h, lpwm->channel, duty_to_compare(arr_l, -duty));
    }
}

void biba_hal_motor_pwm_left(float duty)
{
    set_channel_pair(&s_bindings[0], &s_bindings[1], duty);
}

void biba_hal_motor_pwm_right(float duty)
{
    set_channel_pair(&s_bindings[2], &s_bindings[3], duty);
}

/* Pick PSC so that (SYSCLK / (PSC+1)) / freq_hz fits in the 16-bit ARR.
 * Both PSC and ARR are 16-bit on STM32F1, so we cap PSC at 0xFFFF. */
static void compute_psc_arr(uint32_t freq_hz, uint32_t *out_psc, uint32_t *out_arr)
{
    uint32_t top = BIBA_SYS_CLOCK_HZ / freq_hz;
    if (top == 0) top = 1;
    uint32_t psc = 0;
    while ((top / (psc + 1u)) > 0xFFFFu && psc < 0xFFFFu) {
        psc++;
    }
    uint32_t arr = (top / (psc + 1u));
    if (arr == 0) arr = 1;
    if (arr > 0xFFFFu) arr = 0xFFFFu;
    *out_psc = psc;
    *out_arr = arr - 1u;
}

bool biba_hal_motor_audio_set_all(const uint32_t freq_hz[4],
                                  const float    duty_unit[4])
{
    if (freq_hz == NULL || duty_unit == NULL) return false;
    for (unsigned i = 0; i < 4; ++i) {
        motor_pwm_binding_t *b = &s_bindings[i];
        uint32_t f = freq_hz[i];
        if (f == 0u) {
            __HAL_TIM_SET_COMPARE(b->h, b->channel, 0);
            continue;
        }
        uint32_t psc = 0, arr = 0;
        compute_psc_arr(f, &psc, &arr);
        __HAL_TIM_SET_PRESCALER(b->h, psc);
        __HAL_TIM_SET_AUTORELOAD(b->h, arr);
        float d = duty_unit[i];
        if (d < 0.0f) d = 0.0f;
        if (d > 1.0f) d = 1.0f;
        __HAL_TIM_SET_COMPARE(b->h, b->channel, duty_to_compare(arr, d));
    }
    return true;
}

bool biba_hal_motor_audio_begin(void)
{
    /* Nothing to flip: each timer already has ARR preload enabled, so
     * biba_hal_motor_audio_set_all() can reprogram PSC/ARR on any
     * channel without tearing. The call exists so the companion-mode
     * handler can signal intent. */
    return true;
}

bool biba_hal_motor_audio_end(void)
{
    uint32_t arr = (BIBA_SYS_CLOCK_HZ / BIBA_PWM_FREQUENCY_HZ) - 1u;
    for (unsigned i = 0; i < 4; ++i) {
        motor_pwm_binding_t *b = &s_bindings[i];
        __HAL_TIM_SET_PRESCALER(b->h, 0);
        __HAL_TIM_SET_AUTORELOAD(b->h, arr);
        __HAL_TIM_SET_COMPARE(b->h, b->channel, 0);
    }
    return true;
}

/* ============================================================ */
#else  /* !BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM */
/* ============================================================ */

/* Single shared timer (TIM1). All four channels share ARR -> one
 * carrier. No motor-audio. */
static TIM_HandleTypeDef s_htim1;

static void tim1_init_shared(void)
{
    __HAL_RCC_TIM1_CLK_ENABLE();

    uint32_t arr = (BIBA_SYS_CLOCK_HZ / BIBA_PWM_FREQUENCY_HZ) - 1u;

    s_htim1.Instance               = TIM1;
    s_htim1.Init.Prescaler         = 0;
    s_htim1.Init.CounterMode       = TIM_COUNTERMODE_UP;
    s_htim1.Init.Period            = arr;
    s_htim1.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    s_htim1.Init.RepetitionCounter = 0;
    s_htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    HAL_TIM_PWM_Init(&s_htim1);

    TIM_OC_InitTypeDef oc = {0};
    oc.OCMode     = TIM_OCMODE_PWM1;
    oc.Pulse      = 0;
    oc.OCPolarity = TIM_OCPOLARITY_HIGH;
    oc.OCFastMode = TIM_OCFAST_DISABLE;
    HAL_TIM_PWM_ConfigChannel(&s_htim1, &oc, TIM_CHANNEL_1);
    HAL_TIM_PWM_ConfigChannel(&s_htim1, &oc, TIM_CHANNEL_2);
    HAL_TIM_PWM_ConfigChannel(&s_htim1, &oc, TIM_CHANNEL_3);
    HAL_TIM_PWM_ConfigChannel(&s_htim1, &oc, TIM_CHANNEL_4);

    tim1_apply_break_dead_time(&s_htim1);

    HAL_TIM_PWM_Start(&s_htim1, TIM_CHANNEL_1);
    HAL_TIM_PWM_Start(&s_htim1, TIM_CHANNEL_2);
    HAL_TIM_PWM_Start(&s_htim1, TIM_CHANNEL_3);
    HAL_TIM_PWM_Start(&s_htim1, TIM_CHANNEL_4);
}

void biba_hal_motor_pwm_init(void)
{
    /* TIM1_CH1..CH4 AF pin init. */
    GPIO_InitTypeDef g = {0};
    g.Pin = BIBA_PIN_LEFT_RPWM_PIN | BIBA_PIN_LEFT_LPWM_PIN
          | BIBA_PIN_RIGHT_RPWM_PIN | BIBA_PIN_RIGHT_LPWM_PIN;
    g.Mode  = GPIO_MODE_AF_PP;
    g.Pull  = GPIO_NOPULL;
    g.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOA, &g);

    tim1_init_shared();
}

static void set_channel_pair(uint32_t rpwm_chan, uint32_t lpwm_chan, float duty)
{
    if (duty >  1.0f) duty =  1.0f;
    if (duty < -1.0f) duty = -1.0f;
    uint32_t arr = __HAL_TIM_GET_AUTORELOAD(&s_htim1);
    if (duty >= 0.0f) {
        __HAL_TIM_SET_COMPARE(&s_htim1, lpwm_chan, 0);
        __HAL_TIM_SET_COMPARE(&s_htim1, rpwm_chan, duty_to_compare(arr,  duty));
    } else {
        __HAL_TIM_SET_COMPARE(&s_htim1, rpwm_chan, 0);
        __HAL_TIM_SET_COMPARE(&s_htim1, lpwm_chan, duty_to_compare(arr, -duty));
    }
}

void biba_hal_motor_pwm_left(float duty)
{
    set_channel_pair(TIM_CHANNEL_1, TIM_CHANNEL_2, duty);
}

void biba_hal_motor_pwm_right(float duty)
{
    set_channel_pair(TIM_CHANNEL_3, TIM_CHANNEL_4, duty);
}

bool biba_hal_motor_audio_set_all(const uint32_t freq_hz[4],
                                  const float    duty_unit[4])
{
    /* Single shared carrier: per-channel frequencies are not available. */
    (void)freq_hz;
    (void)duty_unit;
    return false;
}

bool biba_hal_motor_audio_begin(void) { return false; }
bool biba_hal_motor_audio_end(void)   { return false; }

#endif /* BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM */
