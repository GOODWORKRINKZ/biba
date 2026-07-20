#ifndef BIBA_RPM_PI_H
#define BIBA_RPM_PI_H

/* FF+PI RPM controller with gain scheduling and anti-windup.
 *
 * No HAL dependency — portable for native_test under the standalone gcc
 * shim. Source: PoC is_rpm_poc_main.cpp cmd_rpmrun inner loop.
 *
 * The controller is direction-agnostic: target_hz and meas_raw_hz are signed
 * at the API boundary, but the PI math regulates magnitude and restores the
 * target sign on the returned duty. Motor/HAL code owns the physical mapping
 * between signed duty and bridge pins.
 */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float kp;              /* P-term gain                                    */
    float ki;              /* I-term gain when target >= ki_low_thresh       */
    float ki_low;          /* I-term gain when target <  ki_low_thresh       */
    float ki_low_thresh;   /* Hz threshold for gain scheduling               */
    float ff_slope;        /* Hz per 1% duty (e.g. 10.13 from calibration)   */
    float ff_dead;         /* Hz dead-zone offset (e.g. 74.6)                */
    float stiction_floor;  /* Minimum non-zero duty (0..1)                   */
    float p_clamp;         /* Symmetric clamp on the P contribution to duty  */
    float dt_s;            /* Loop period in seconds (e.g. 0.104)            */
} biba_rpm_pi_config_t;

typedef struct {
    float integral;
    float meas_ema;
    float prev_duty;
    float prev_target;     /* last |target_hz| seen by step() (for I-rescaling) */
    bool  primed;
} biba_rpm_pi_state_t;

/* Default tuning constants (mirrors CONTEXT.md decisions).
 * Defaults are set in biba_config.h; these #ifndef guards allow target
 * overrides to propagate through. */
#ifndef BIBA_RPM_PI_KP
#  define BIBA_RPM_PI_KP             0.003f
#endif
#ifndef BIBA_RPM_PI_KI
#  define BIBA_RPM_PI_KI             0.010f
#endif
#ifndef BIBA_RPM_PI_KI_LOW
#  define BIBA_RPM_PI_KI_LOW         0.005f
#endif
#ifndef BIBA_RPM_PI_KI_LOW_THRESH
#  define BIBA_RPM_PI_KI_LOW_THRESH  200.0f
#endif
#ifndef BIBA_RPM_PI_FF_SLOPE
#  define BIBA_RPM_PI_FF_SLOPE       10.13f
#endif
#ifndef BIBA_RPM_PI_FF_DEAD
#  define BIBA_RPM_PI_FF_DEAD        74.6f
#endif
#ifndef BIBA_RPM_PI_STICTION
#  define BIBA_RPM_PI_STICTION       0.15f  /* sustain threshold ~77 Hz; break stiction needs ~0.20 */
#endif
#ifndef BIBA_RPM_PI_P_CLAMP
#  define BIBA_RPM_PI_P_CLAMP        0.20f
#endif
#ifndef BIBA_RPM_PI_DT_S
#  define BIBA_RPM_PI_DT_S           0.104f
#endif

void  biba_rpm_pi_reset(biba_rpm_pi_state_t *s);
float biba_rpm_pi_step(biba_rpm_pi_state_t *s,
                       const biba_rpm_pi_config_t *cfg,
                       float target_hz,
                       float meas_raw_hz);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_RPM_PI_H */
