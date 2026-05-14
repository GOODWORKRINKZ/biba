#ifndef BIBA_CURRENT_SENSE_H
#define BIBA_CURRENT_SENSE_H

#include <stdbool.h>
#include <stdint.h>

#include "app/control_loop.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float zero_offset_v;
    float amps_per_volt;
} biba_current_calibration_t;

void biba_current_sense_configure(biba_current_calibration_t left,
                                  biba_current_calibration_t right);

/* Convert the latest ADC samples into amps for left/right BTS7960. */
biba_motor_current_t biba_current_sense_left(void);
biba_motor_current_t biba_current_sense_right(void);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_CURRENT_SENSE_H */
