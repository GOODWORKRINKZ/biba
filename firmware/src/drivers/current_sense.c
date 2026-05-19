#include "current_sense.h"

#include "ads1115.h"
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

static biba_motor_current_t sample(uint8_t fwd_chan, uint8_t rev_chan,
                                    const biba_current_calibration_t *cal)
{
    float vfwd = 0.0f;
    float vrev = 0.0f;
    /* Read both half-bridge IS channels from ADS1115.
     * Only one half-bridge conducts at a time; take the larger magnitude. */
    (void)ads1115_read_channel_v(ADS1115_ADDR, fwd_chan, &vfwd);
    (void)ads1115_read_channel_v(ADS1115_ADDR, rev_chan, &vrev);
    float v = (vfwd > vrev) ? vfwd : vrev;
    float amps = (v - cal->zero_offset_v) * cal->amps_per_volt;
    biba_motor_current_t out = { .current_a = amps, .valid = true };
    return out;
}

biba_motor_current_t biba_current_sense_left(void)
{
    return sample(BIBA_ADS1115_CHAN_IS_L_FWD, BIBA_ADS1115_CHAN_IS_L_REV, &s_left);
}

biba_motor_current_t biba_current_sense_right(void)
{
    return sample(BIBA_ADS1115_CHAN_IS_R_FWD, BIBA_ADS1115_CHAN_IS_R_REV, &s_right);
}
