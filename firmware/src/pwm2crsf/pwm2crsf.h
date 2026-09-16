#ifndef BIBA_PWM2CRSF_H
#define BIBA_PWM2CRSF_H

/* PWM → CRSF bridge core.
 *
 * Turns servo-PWM pulse widths captured from a plain PWM receiver
 * (HotRC and similar) into CRSF RC-channel frames, so the bridge board
 * can be plugged into BiBa's CRSF port in place of an ELRS receiver.
 *
 * Hardware-free: the RP2040 entry point (pwm2crsf_main.cpp) measures
 * pulses and owns the UART, this module only decides what to send.
 * Covered by test/test_pwm2crsf in the native env. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "crsf.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PWM2CRSF_MAX_INPUTS      8u
#define PWM2CRSF_UNMAPPED        (-1)

/* Standard CRSF channel range (what ELRS emits for 988..2012 µs and
 * what mode_standalone.c maps to -1..+1). */
#define PWM2CRSF_CRSF_MIN        172u
#define PWM2CRSF_CRSF_MID        992u
#define PWM2CRSF_CRSF_MAX        1811u

typedef struct {
    uint8_t  input_count;
    /* Receiver endpoints mapped onto CRSF_MIN / CRSF_MAX. Pulses outside
     * this range are clamped. */
    uint16_t min_us;
    uint16_t max_us;
    /* Anything outside [valid_min_us, valid_max_us] is a glitch and is
     * dropped without refreshing the input. */
    uint16_t valid_min_us;
    uint16_t valid_max_us;
    /* A mapped input with no valid pulse for this long puts the bridge
     * into failsafe (RC frames stop, BiBa times out on its own). */
    uint32_t input_timeout_us;
    /* For every CRSF channel: which PWM input feeds it (0-based) or
     * PWM2CRSF_UNMAPPED. */
    int8_t   map[CRSF_RC_CHANNEL_COUNT];
    /* Constant value sent on unmapped CRSF channels. */
    uint16_t idle[CRSF_RC_CHANNEL_COUNT];
    /* Bit i set → PWM input i is mirrored around the centre of
     * min_us..max_us before conversion (reverse an axis or a button). */
    uint8_t  invert_mask;

    /* Cycle button: every press on `cycle_input` advances a counter
     * 0 → 1 → … → cycle_steps-1 → 0, and `cycle_crsf_ch` carries it as
     * evenly spaced values CRSF_MIN..CRSF_MAX (3 steps = 172/992/1811).
     * Lets a single HotRC button drive BiBa's 3-position speed switch.
     * cycle_input = PWM2CRSF_UNMAPPED disables it. */
    int8_t   cycle_input;
    uint8_t  cycle_crsf_ch;
    uint8_t  cycle_steps;
    /* Latching button (each press flips the level) → count both edges.
     * Momentary button (high only while held) → count rising edges. */
    bool     cycle_count_both_edges;
    /* Button level hysteresis, µs (after invert_mask is applied). */
    uint16_t cycle_high_us;
    uint16_t cycle_low_us;
    /* Edges closer than this to the previous counted one are ignored. */
    uint32_t cycle_min_interval_us;
} pwm2crsf_config_t;

typedef struct {
    uint16_t width_us[PWM2CRSF_MAX_INPUTS];
    uint64_t last_valid_us[PWM2CRSF_MAX_INPUTS];
    bool     seen[PWM2CRSF_MAX_INPUTS];
    uint32_t glitches;

    bool     cycle_primed;     /* button level known */
    bool     cycle_btn_high;
    uint8_t  cycle_step;
    uint64_t cycle_last_edge_us;
} pwm2crsf_state_t;

void pwm2crsf_init(pwm2crsf_state_t *state);

/* Feed one measured high-time. Returns false if the pulse was rejected
 * (bad input index or out of the valid window). */
bool pwm2crsf_on_pulse(pwm2crsf_state_t *state,
                       const pwm2crsf_config_t *cfg,
                       uint8_t input,
                       uint32_t width_us,
                       uint64_t now_us);

/* True when the input has produced a valid pulse within the timeout. */
bool pwm2crsf_input_fresh(const pwm2crsf_state_t *state,
                          const pwm2crsf_config_t *cfg,
                          uint8_t input,
                          uint64_t now_us);

/* True when every input referenced by cfg->map is fresh. */
bool pwm2crsf_link_ok(const pwm2crsf_state_t *state,
                      const pwm2crsf_config_t *cfg,
                      uint64_t now_us);

/* Back to the first cycle step and forget the button level. Call when
 * the link drops so BiBa always comes back in the slowest mode. */
void pwm2crsf_reset_cycle(pwm2crsf_state_t *state);

/* Linear min_us..max_us → CRSF_MIN..CRSF_MAX, clamped. */
uint16_t pwm2crsf_us_to_crsf(const pwm2crsf_config_t *cfg, uint32_t width_us);

/* Fill all 16 CRSF channels from the current state. */
void pwm2crsf_channels(const pwm2crsf_state_t *state,
                       const pwm2crsf_config_t *cfg,
                       uint16_t out[CRSF_RC_CHANNEL_COUNT]);

/* Build the RC-channels frame to send now. Returns the frame length, or
 * 0 when the bridge is in failsafe and nothing must be sent. */
size_t pwm2crsf_build_rc_frame(const pwm2crsf_state_t *state,
                               const pwm2crsf_config_t *cfg,
                               uint64_t now_us,
                               uint8_t *out,
                               size_t out_cap);

/* Build a synthetic LINK_STATISTICS frame (LQ 100 / 0 by link state) so
 * BiBa's telemetry shows something sensible. */
size_t pwm2crsf_build_link_stats_frame(bool link_ok,
                                       uint8_t *out,
                                       size_t out_cap);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_PWM2CRSF_H */
