#include "current_sense.h"

#include "biba_board.h"
#include "biba_config.h"
#include "hal/biba_hal.h"

static biba_current_calibration_t s_left  = { BIBA_IS_ZERO_OFFSET_V, BIBA_IS_AMPS_PER_VOLT };
static biba_current_calibration_t s_right = { BIBA_IS_ZERO_OFFSET_V, BIBA_IS_AMPS_PER_VOLT };

void biba_current_sense_configure(biba_current_calibration_t left,
                                  biba_current_calibration_t right)
{
    s_left = left;
    s_right = right;
}

static biba_motor_current_t sample(uint8_t adc_chan,
                                    const biba_current_calibration_t *cal)
{
    /* Phase 06: IS signals combined per motor on native ADC (RC-filtered).
     * GP26 = IS_LEFT (BIBA_ADC_CHAN_IS_LEFT), GP27 = IS_RIGHT (BIBA_ADC_CHAN_IS_RIGHT). */
    uint16_t raw = biba_hal_adc_sample(adc_chan);
    float v = biba_hal_adc_volts(raw);
    float amps = (v - cal->zero_offset_v) * cal->amps_per_volt;
    if (amps < 0.0f) amps = 0.0f;
    biba_motor_current_t out = { .current_a = amps, .valid = true };
    return out;
}

biba_motor_current_t biba_current_sense_left(void)
{
    return sample(BIBA_ADC_CHAN_IS_LEFT, &s_left);
}

biba_motor_current_t biba_current_sense_right(void)
{
    return sample(BIBA_ADC_CHAN_IS_RIGHT, &s_right);
}
