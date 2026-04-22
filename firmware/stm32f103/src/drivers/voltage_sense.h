#ifndef BIBA_VOLTAGE_SENSE_H
#define BIBA_VOLTAGE_SENSE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Returns VBAT in millivolts, based on the configured 1:11 divider. */
uint16_t biba_voltage_sense_vbat_mv(void);

/* Returns optional 12 V rail in millivolts. Returns 0 when unpopulated. */
uint16_t biba_voltage_sense_rail_mv(void);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_VOLTAGE_SENSE_H */
