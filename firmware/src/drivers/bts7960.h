#ifndef BIBA_BTS7960_H
#define BIBA_BTS7960_H

/* Thin wrapper around the HAL PWM + enable lines for the two BTS7960
 * driver boards. Keeps mode code free of direct timer/PWM references. */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void biba_bts7960_set_enabled(bool enabled);

/* Both duties in [-1, 1]. Positive = forward. */
void biba_bts7960_drive(float left_duty, float right_duty);

/* Best-effort thermal-latch clear using BTS7960 enable lines only. */
void biba_bts7960_thermal_reset(uint32_t pulse_us);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_BTS7960_H */
