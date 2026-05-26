#ifndef BIBA_RPM_DR_H
#define BIBA_RPM_DR_H

/* Dead-reckoning RPM fallback.
 *
 * When the Goertzel spectral estimator returns valid=false, extrapolate
 * the wheel speed from the last valid meas_hz/target_hz ratio (EMA),
 * up to BIBA_RPM_DR_MAX_STREAK consecutive invalid cycles.
 *
 * Pure C99 — no HAL dependency. Portable under native_test env.
 * ISR-safe: no dynamic allocation, no blocking, no mutex.
 */

#include <stdint.h>
#include "app/rpm_spectral_estimator.h"   /* biba_rpm_spectral_result_t, reason enum */

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float   ratio_ema;   /* EMA of meas_hz/target_hz; 0.0f = cold start */
    uint8_t streak;      /* consecutive invalid cycles; clamped at 255  */
} biba_rpm_dr_state_t;

/* Zero ratio_ema and streak. Call at disarm / mode init (all 7 sites in
 * mode_standalone.c where biba_rpm_pi_reset() is called). */
void  biba_rpm_dr_reset(biba_rpm_dr_state_t *state);

/* Update DR state and return the best available Hz estimate.
 *
 * Returns spec->freq_hz when spec->valid == true (ratio EMA updated).
 * Returns ratio_ema * target_hz when streak <= MAX_STREAK, ratio_ema > 0,
 *   and target_hz >= BIBA_RPM_SPECTRAL_MIN_TARGET_HZ (*out_reason = EXTRAPOLATED).
 * Returns 0.0f otherwise (*out_reason = spec->invalid_reason).
 *
 * Works with magnitudes; sign is applied by mode_standalone.c.
 */
float biba_rpm_dr_update(
    biba_rpm_dr_state_t                      *state,
    const biba_rpm_spectral_result_t         *spec,
    float                                     target_hz,
    biba_rpm_spectral_invalid_reason_t       *out_reason
);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_RPM_DR_H */
