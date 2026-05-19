#ifndef BIBA_VOLTAGE_SENSE_H
#define BIBA_VOLTAGE_SENSE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Returns VBAT in millivolts, based on the configured voltage divider. */
uint16_t biba_voltage_sense_vbat_mv(void);

/* Returns pack current in amperes from the 3DR Power Module current output.
 * Uses BIBA_IBAT_AMPS_PER_VOLT and BIBA_IBAT_ZERO_OFFSET_V for calibration.
 * Returns 0.0 when BIBA_ADC_CHAN_IBAT is not defined for the target. */
float biba_voltage_sense_ibat_a(void);

/* Returns optional 12 V rail in millivolts. Returns 0 when unpopulated. */
uint16_t biba_voltage_sense_rail_mv(void);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_VOLTAGE_SENSE_H */
