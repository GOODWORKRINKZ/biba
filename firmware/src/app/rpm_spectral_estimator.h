#ifndef BIBA_RPM_SPECTRAL_ESTIMATOR_H
#define BIBA_RPM_SPECTRAL_ESTIMATOR_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Defaults are set in biba_config.h; these #ifndef guards allow target
 * overrides to propagate through. */
#ifndef BIBA_RPM_SPECTRAL_MIN_TARGET_HZ
#  define BIBA_RPM_SPECTRAL_MIN_TARGET_HZ      50.0f
#endif
#ifndef BIBA_RPM_SPECTRAL_MAX_TARGET_HZ
#  define BIBA_RPM_SPECTRAL_MAX_TARGET_HZ    1200.0f
#endif
#ifndef BIBA_RPM_SPECTRAL_REL_BAND
#  define BIBA_RPM_SPECTRAL_REL_BAND           0.35f
#endif
#ifndef BIBA_RPM_SPECTRAL_ABS_BAND_HZ
#  define BIBA_RPM_SPECTRAL_ABS_BAND_HZ        80.0f
#endif
#ifndef BIBA_RPM_SPECTRAL_MIN_PEAK_AMP_LSB
#  define BIBA_RPM_SPECTRAL_MIN_PEAK_AMP_LSB   45.0f
#endif
#ifndef BIBA_RPM_SPECTRAL_MIN_QUALITY
#  define BIBA_RPM_SPECTRAL_MIN_QUALITY         3.0f
#endif

typedef enum {
    BIBA_RPM_SPECTRAL_INVALID_NONE = 0,
    BIBA_RPM_SPECTRAL_INVALID_TARGET_LOW = 1,
    BIBA_RPM_SPECTRAL_INVALID_NO_BAND = 2,
    BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW = 3,
    BIBA_RPM_SPECTRAL_INVALID_QUALITY_LOW = 4,
    BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED = 5,   /* DR fallback active */
    BIBA_RPM_SPECTRAL_HINT_MEASURED = 6,           /* hint window was better than plant window */
    BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD = 7,        /* IS-pin DC load gate tripped (Phase 11) */
} biba_rpm_spectral_invalid_reason_t;

typedef struct {
    float mean_adc;
    float freq_hz;
    float candidate_hz;
    float quality;
    float peak_amp_lsb;
    float second_amp_lsb;
    biba_rpm_spectral_invalid_reason_t invalid_reason;
    bool valid;
} biba_rpm_spectral_result_t;

biba_rpm_spectral_result_t biba_rpm_spectral_estimate(const uint16_t *buf,
                                                      uint16_t n,
                                                      uint32_t sps,
                                                      float target_hz,
                                                      float hint_hz);

void biba_rpm_spectral_apply_load_gate(biba_rpm_spectral_result_t *primary,
                                       biba_rpm_spectral_result_t *secondary);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_RPM_SPECTRAL_ESTIMATOR_H */