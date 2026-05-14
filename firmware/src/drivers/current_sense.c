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

static biba_motor_current_t sample(unsigned r_chan, unsigned l_chan,
                                    const biba_current_calibration_t *cal)
{
    uint16_t r_raw = biba_hal_adc_sample(r_chan);
    uint16_t l_raw = biba_hal_adc_sample(l_chan);
    /* BTS7960: R_IS is active when rotating one direction, L_IS the other;
     * the driver's internal current mirror maps a fraction of motor current
     * to the IS pin. We take the larger of the two as the magnitude. */
    float vr = biba_hal_adc_volts(r_raw);
    float vl = biba_hal_adc_volts(l_raw);
    float v = (vr > vl) ? vr : vl;
    float amps = (v - cal->zero_offset_v) * cal->amps_per_volt;
    biba_motor_current_t out = { .current_a = amps, .valid = true };
    return out;
}

biba_motor_current_t biba_current_sense_left(void)
{
    return sample(BIBA_ADC_CHAN_LEFT_R_IS, BIBA_ADC_CHAN_LEFT_L_IS, &s_left);
}

biba_motor_current_t biba_current_sense_right(void)
{
    return sample(BIBA_ADC_CHAN_RIGHT_R_IS, BIBA_ADC_CHAN_RIGHT_L_IS, &s_right);
}
