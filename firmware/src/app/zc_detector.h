#ifndef BIBA_ZC_DETECTOR_H
#define BIBA_ZC_DETECTOR_H

/* A2 Sub-window Schmitt-trigger zero-crossing frequency estimator.
 * Pure C99 — no HAL dependency. Portable under native_test env.
 *
 * Ported from firmware/src/poc/is_rpm_poc_main.cpp (Phase 6 PoC).
 * Used by mode_standalone.c (Plan 07-05) for closed-loop RPM control
 * over both wheel IS-pin channels (BIBA_ADC_CHAN_IS_LEFT/RIGHT).
 */

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Sub-window count for the A2 algorithm. The input buffer is split into
 * ZC_SUBWIN_K equal blocks; each block computes a local baseline (min/max/mid)
 * and counts Schmitt-trigger transitions independently. Local baselines
 * remove low-frequency DC drift that ruins a single global-mean detector
 * during PWM transients. */
#define ZC_SUBWIN_K          8u

/* Minimum per-block peak-to-peak (LSB) to consider a block "active" — blocks
 * with less AC content are skipped (DC-only or noise-floor segments).
 *
 * Calibrated from bench data (sweepraw n=196 SIN amp35):
 *   - Motor STOPPED (PWM noise only):  pkpk = 87–170 LSB, median 117
 *   - Motor RUNNING at >15% duty:       pkpk = 100–613 LSB, median 264
 * Threshold 120 gives 0% false positives (stopped) while keeping 84% of
 * real-signal windows.  The previous value of 30 allowed PWM noise through
 * at ~110 Hz — above the ZC_MIN_VALID_HZ=80 gate — corrupting the EMA. */
#define ZC_SUBWIN_MIN_PKPK   120u

/* Low-side validity gate for zc_ema_update: readings below this are treated
 * as noise-floor (back-EMF saturation / no IS current) rather than real
 * commutation frequency. */
#define ZC_MIN_VALID_HZ      80.0f

/* EMA smoothing factor for the validity-gated update (alpha=0.7 → 70% weight
 * on the new reading). Two-cycle (~200 ms @ 10 Hz loop) step response. */
#define ZC_EMA_ALPHA         0.7f

/* Compute the dominant frequency in `buf` (n samples at `sps` SPS) using
 * the A2 Sub-window Schmitt detector. Returns 0.0f when n is too small
 * (< ZC_SUBWIN_K * 4) or when fewer than 2 blocks contain AC content. */
float zc_freq_hz(const uint16_t *buf, uint16_t n, uint32_t sps);

/* Update the EMA filter `*ema` with a new raw measurement, gated by a
 * two-sided validity window:
 *   - meas_raw in [ZC_MIN_VALID_HZ, target_hz*2.5 + 300] → standard EMA update
 *   - meas_raw == 0.0f                                   → slow decay (*=0.9)
 *   - otherwise                                          → hold unchanged
 * Returns the new EMA value (also stored in *ema). */
float zc_ema_update(float *ema, float meas_raw, float target_hz);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_ZC_DETECTOR_H */
