/* Standalone mode: the STM32 owns the whole low-level biba behaviour.
 *
 *     CRSF RX -> parser -> mixer -> heading-hold PID -> limiter -> PWM
 *
 * Telemetry is aggregated at BIBA_TELEMETRY_PUBLISH_HZ for future CRSF
 * battery-sensor uplink, and the DATA_READY line still pulses so an
 * attached debugger / SBC can piggy-back if wired in. */

#include <string.h>
#include <stdio.h>

#include "mode_dispatcher.h"

#include "biba_config.h"
#include "biba_board.h"
#include "app/control_loop.h"
#include "app/failsafe.h"
#include "app/adc_capture.h"
#include "app/zc_detector.h"
#include "app/rpm_pi.h"
#include "app/telemetry.h"
#include "drivers/bts7960.h"
#include "drivers/crsf.h"
#include "drivers/current_sense.h"
#include "hal/biba_hal.h"
#include "proto/biba_proto.h"
#include "app/melody.h"
#define CRSF_ADDR_BROADCAST         0x00u
#define CRSF_ADDR_FLIGHT_CONTROLLER 0xC8u
#define CRSF_FRAMETYPE_DEVICE_PING  0x28u

#define CRSF_BUFFER_SIZE 192

static uint8_t  s_crsf_buffer[CRSF_BUFFER_SIZE];
static size_t   s_crsf_fill;
static biba_failsafe_t s_crsf_failsafe;

static biba_crsf_link_stats_t s_link;
static uint16_t s_channels[CRSF_RC_CHANNEL_COUNT];
static uint32_t s_last_scan_count;
static uint32_t s_last_tick_ms;
static uint8_t  s_telemetry_seq;

static uint32_t s_dbg_bytes_total;
static uint32_t s_dbg_frames_ok;
static uint32_t s_dbg_frames_bad;
static uint32_t s_dbg_ch_frames;
static uint32_t s_dbg_tx_ok;
static uint32_t s_dbg_tx_fail;

static void send_crsf_ping(void)
{
    /* Minimal CRSF device ping so ELRS EP01 knows a host is present and
     * starts outputting RC_CHANNELS_PACKED frames on its TX pin. */
    uint8_t body[3] = {
        CRSF_FRAMETYPE_DEVICE_PING,
        CRSF_ADDR_BROADCAST,
        CRSF_ADDR_FLIGHT_CONTROLLER,
    };
    uint8_t crc = biba_crsf_crc8_dvb_s2(body, sizeof(body));
    uint8_t frame[6] = {
        CRSF_SYNC_BYTE,
        (uint8_t)(sizeof(body) + 1u), /* length = body + crc */
        body[0], body[1], body[2],
        crc,
    };
    if (biba_hal_crsf_write(frame, sizeof(frame)) == 0) {
        s_dbg_tx_ok++;
    } else {
        s_dbg_tx_fail++;
    }
}

static biba_pid_state_t s_heading_pid;
/* Heading-hold PID. ki is intentionally 0 while the IMU integration is a
 * stub: without a reliable yaw measurement the integral term would wind
 * up against operator steering and make the robot feel sluggish. Once
 * `biba_imu_read()` returns real gyro data the ki can be re-tuned. */
static const biba_pid_config_t s_heading_cfg = {
    .kp = 0.6f, .ki = 0.0f, .kd = 0.02f,
    .output_limit = 0.5f, .integral_limit = 0.5f
};

static bool s_armed;   /* tracks arm state across ticks for edge logging */
static bool s_last_failsafe;

/* RPM closed-loop state (per-channel). Replaces the open-loop slew
 * ramp from Phase ≤6. DMA IRQ writes s_rpm_duty_*; tick reads them. */
static biba_rpm_pi_state_t  s_rpm_pi_left;
static biba_rpm_pi_state_t  s_rpm_pi_right;
static volatile float       s_rpm_duty_left;
static volatile float       s_rpm_duty_right;
static volatile float       s_target_hz_left;   /* tick writes, on_adc_done reads */
static volatile float       s_target_hz_right;
static float                s_raw_hz_left;       /* LEFT ZC held until RIGHT branch */
static uint16_t             s_adc_buf[1024];     /* shared DMA buffer (L then R) */

/* Measured Hz per channel (set by on_adc_done IRQ, read for DRIVE_DATA telem). */
static volatile float s_meas_hz_left;
static volatile float s_meas_hz_right;

/* Debug override state — serial-controlled bench testing.
 * DBGON  : enable override mode (CRSF inputs bypassed).
 * ARM    : set s_dbg_arm (only when debug active).
 * DISARM : clear s_dbg_arm, zero throttle/steering.
 * SET T=<-100..100> S=<-100..100> : set throttle/steering overrides.
 * DBGOFF : disable override mode.
 * While active, DRIVE_DATA telemetry is emitted every tick. */
static bool  s_dbg_active;
static bool  s_dbg_arm;
static float s_dbg_thr;
static float s_dbg_str;

/* ADC capture state machine. */
typedef enum { ADC_IDLE, ADC_CAPTURING_LEFT, ADC_CAPTURING_RIGHT } adc_state_t;
static volatile adc_state_t s_adc_state = ADC_IDLE;

/* PI config initialised in biba_mode_standalone_init(). */
static biba_rpm_pi_config_t s_rpm_cfg;

/* Max Hz at 100% duty (from Phase 06 calibration). Maps mixer [-1,1] -> Hz. */
#define STANDALONE_RPM_MAX_HZ  940.0f

static bool s_beacon_active;
static uint32_t s_sos_next_ms;   /* earliest time for next SOS repeat */
static biba_melody_player_t s_player;

/* Reverse backup pip */
static bool     s_reversing;
static bool     s_reverse_pip_active;
static uint32_t s_reverse_pip_next_ms;

/* Motor trim state (ported from biba-controller/main.py) */
static bool     s_trim_mode_active;
static float    s_saved_motor_trim;
static uint32_t s_trim_gesture_start_ms;
static bool     s_trim_gesture_consumed;

/* RGB LED state machine -------------------------------------------------- */
static uint32_t s_led_blink_ms;   /* last blink toggle timestamp */
static bool     s_led_blink_on;

/* Update the WS2812 RGB LED once per tick based on system state.
 *
 * Priority (highest first):
 *  1. Failsafe                → red fast blink (200 ms)
 *  2. Trim mode active        → yellow blink   (300 ms)
 *  3. Armed + reversing       → red solid
 *  4. Armed (forward/idle)    → green solid
 *  5. Beacon active           → magenta blink  (500 ms)
 *  6. Disarmed + RC OK        → blue dim solid
 *  7. Boot / no RC            → white slow blink (1000 ms)
 */
static void update_rgb_led(bool failsafe, bool armed, bool trim_mode,
                            bool reversing, bool beacon, uint32_t now)
{
    uint8_t r = 0, g = 0, b = 0;
    uint32_t period = 0; /* 0 = solid */

    if (failsafe) {
        r = 255; period = 200u;
    } else if (trim_mode) {
        r = 200; g = 100; period = 300u;  /* orange */
    } else if (armed && reversing) {
        r = 255;
    } else if (armed) {
        g = 80;
    } else if (beacon) {
        r = 100; b = 180; period = 500u;  /* magenta */
    } else {
        /* Disarmed + RC OK */
        b = 40; /* dim blue */
    }

    if (period > 0u) {
        if (now - s_led_blink_ms >= period) {
            s_led_blink_ms = now;
            s_led_blink_on = !s_led_blink_on;
        }
        if (!s_led_blink_on) { r = 0; g = 0; b = 0; }
    }

    biba_hal_rgb_led_set(r, g, b);
}

/* Process one line of serial debug input per tick (non-blocking).
 * Commands: DBGON / DBGOFF / ARM / DISARM / SET T=<pct> S=<pct> */
static void process_debug_serial(void)
{
    char line[64];
    if (!biba_hal_serial_readline(line, sizeof(line))) return;
    if (strcmp(line, "DBGON") == 0) {
        s_dbg_active = true;
        printf("[biba] DBG mode ON\r\n");
    } else if (strcmp(line, "DBGOFF") == 0) {
        s_dbg_active = false;
        s_dbg_arm    = false;
        s_dbg_thr    = 0.0f;
        s_dbg_str    = 0.0f;
        printf("[biba] DBG mode OFF\r\n");
    } else if (s_dbg_active && strcmp(line, "ARM") == 0) {
        s_dbg_arm = true;
        printf("[biba] DBG armed\r\n");
    } else if (s_dbg_active && (strcmp(line, "DISARM") == 0)) {
        s_dbg_arm = false;
        s_dbg_thr = 0.0f;
        s_dbg_str = 0.0f;
        printf("[biba] DBG disarmed\r\n");
    } else if (s_dbg_active) {
        int thr_pct = 0, str_pct = 0;
        if (sscanf(line, "SET T=%d S=%d", &thr_pct, &str_pct) == 2) {
            if (thr_pct < -100) thr_pct = -100;
            if (thr_pct >  100) thr_pct =  100;
            if (str_pct < -100) str_pct = -100;
            if (str_pct >  100) str_pct =  100;
            s_dbg_thr = (float)thr_pct / 100.0f;
            s_dbg_str = (float)str_pct / 100.0f;
        }
    }
}

static float rc_to_unit(uint16_t v)
{
    /* Standard CRSF channel: 172..1811 maps to -1..+1. */
    float normalised = ((float)v - 992.0f) / 819.0f;
    return biba_clamp_unit(normalised);
}

/* DMA IRQ callback: a 1024-sample capture just finished on `channel`.
 * Compute the ZC frequency, advance the L->R state machine, and once both
 * channels are sampled run the PI step for both motors. Writes to the
 * volatile s_rpm_duty_* are picked up by the next biba_mode_standalone_tick. */
static void on_adc_done(uint8_t channel, const uint16_t *buf, uint16_t n)
{
    (void)channel;
    float raw_hz = zc_freq_hz(buf, n, 10000u);

    if (s_adc_state == ADC_CAPTURING_LEFT) {
        s_raw_hz_left = raw_hz;
        s_adc_state = ADC_CAPTURING_RIGHT;
        (void)adc_capture_start_async(BIBA_ADC_CHAN_IS_RIGHT, 1024u, s_adc_buf, on_adc_done);
    } else if (s_adc_state == ADC_CAPTURING_RIGHT) {
        float raw_hz_right = raw_hz;
        float raw_hz_left  = s_raw_hz_left;
        /* Save raw measurements for DRIVE_DATA telemetry (debug mode). */
        s_meas_hz_left  = raw_hz_left;
        s_meas_hz_right = raw_hz_right;
        s_rpm_duty_left  = biba_rpm_pi_step(&s_rpm_pi_left,  &s_rpm_cfg,
                                            s_target_hz_left,  raw_hz_left);
        s_rpm_duty_right = biba_rpm_pi_step(&s_rpm_pi_right, &s_rpm_cfg,
                                            s_target_hz_right, raw_hz_right);
        s_adc_state = ADC_CAPTURING_LEFT;
        (void)adc_capture_start_async(BIBA_ADC_CHAN_IS_LEFT, 1024u, s_adc_buf, on_adc_done);
    }
}

static biba_limit_result_t apply_drive_current_limits(biba_mix_output_t mix)
{
    biba_motor_current_t il = biba_current_sense_left();
    biba_motor_current_t ir = biba_current_sense_right();
    biba_motor_limit_t lim = {
        .current_limit_a  = BIBA_LEFT_MAX_CURRENT_A,
        .power_limit_w    = BIBA_LEFT_MAX_POWER_W,
        .supply_voltage_v = BIBA_FALLBACK_SUPPLY_V,
    };
    biba_motor_limit_t rim = {
        .current_limit_a  = BIBA_RIGHT_MAX_CURRENT_A,
        .power_limit_w    = BIBA_RIGHT_MAX_POWER_W,
        .supply_voltage_v = BIBA_FALLBACK_SUPPLY_V,
    };
    return biba_apply_motor_limits(mix.left, mix.right, il, ir, lim, rim);
}

void biba_mode_standalone_init(void)
{
    biba_hal_crsf_begin(BIBA_CRSF_BAUD);
    biba_failsafe_init(&s_crsf_failsafe, BIBA_CRSF_TIMEOUT_MS);
    biba_pid_reset(&s_heading_pid);
    s_last_tick_ms = biba_hal_now_ms();
    biba_bts7960_thermal_reset(BIBA_BTS7960_RESET_PULSE_US);

    /* Suppress failsafe melody on the very first tick (no RC lock-in yet). */
    s_last_failsafe = true;

    /* PI config: load default tuning from rpm_pi.h. */
    s_rpm_cfg.kp             = BIBA_RPM_PI_KP;
    s_rpm_cfg.ki             = BIBA_RPM_PI_KI;
    s_rpm_cfg.ki_low         = BIBA_RPM_PI_KI_LOW;
    s_rpm_cfg.ki_low_thresh  = BIBA_RPM_PI_KI_LOW_THRESH;
    s_rpm_cfg.ff_slope       = BIBA_RPM_PI_FF_SLOPE;
    s_rpm_cfg.ff_dead        = BIBA_RPM_PI_FF_DEAD;
    s_rpm_cfg.stiction_floor = BIBA_RPM_PI_STICTION;
    s_rpm_cfg.p_clamp        = BIBA_RPM_PI_P_CLAMP;
    s_rpm_cfg.dt_s           = BIBA_RPM_PI_DT_S;

    biba_rpm_pi_reset(&s_rpm_pi_left);
    biba_rpm_pi_reset(&s_rpm_pi_right);
    s_rpm_duty_left   = 0.0f;
    s_rpm_duty_right  = 0.0f;
    s_target_hz_left  = 0.0f;
    s_target_hz_right = 0.0f;
    s_raw_hz_left     = 0.0f;

    /* Start the LEFT->RIGHT ADC capture state machine. */
    adc_capture_init(10000u);
    s_adc_state = ADC_CAPTURING_LEFT;
    (void)adc_capture_start_async(BIBA_ADC_CHAN_IS_LEFT, 1024u, s_adc_buf, on_adc_done);

    /* Play startup fanfare through motor coils. */
    biba_melody_player_start(&s_player, &biba_melody_startup);
}

static void ingest_crsf(void)
{
    size_t free_space = CRSF_BUFFER_SIZE - s_crsf_fill;
    if (free_space > 0) {
        size_t got = biba_hal_crsf_read(&s_crsf_buffer[s_crsf_fill], free_space);
        s_crsf_fill += got;
        s_dbg_bytes_total += (uint32_t)got;
    }

    uint8_t frame[CRSF_MAX_FRAME_SIZE];
    size_t frame_len = 0;
    for (;;) {
        uint8_t type = biba_crsf_pop_frame(s_crsf_buffer, &s_crsf_fill,
                                           frame, sizeof(frame), &frame_len);
        if (type == 0) break;

        const uint8_t *payload = NULL;
        size_t payload_len = 0;
        if (biba_crsf_parse_frame(frame, frame_len, &payload, &payload_len) == 0) {
            s_dbg_frames_bad++;
            continue;
        }
        s_dbg_frames_ok++;
        if (type == CRSF_FRAMETYPE_RC_CHANNELS) {
            if (biba_crsf_unpack_channels(payload, payload_len, s_channels)) {
                s_dbg_ch_frames++;
                biba_failsafe_mark_fresh(&s_crsf_failsafe, biba_hal_now_ms());
            }
        } else if (type == CRSF_FRAMETYPE_LINK_STATS) {
            biba_crsf_parse_link_stats(payload, payload_len, &s_link);
        }
    }
}

void biba_mode_standalone_tick(void)
{
    process_debug_serial();
    ingest_crsf();
    uint32_t now = biba_hal_now_ms();

    /* Send CRSF ping at 5 Hz so ELRS EP01 knows a host is present. */
    static uint32_t s_last_ping_ms;
    if (now - s_last_ping_ms >= 200u) {
        s_last_ping_ms = now;
        send_crsf_ping();
    }

    float dt = (float)(now - s_last_tick_ms) / 1000.0f;
    s_last_tick_ms = now;

    bool failsafe = biba_failsafe_tick(&s_crsf_failsafe, now);

    /* ------------------------------------------------------------------ *
     * Channel reads (normalised -1..+1, mirroring biba-controller/config.py)
     * ------------------------------------------------------------------ */
    float raw_throttle = failsafe ? 0.0f : rc_to_unit(s_channels[BIBA_CH_THROTTLE]);
    float raw_steering = failsafe ? 0.0f : rc_to_unit(s_channels[BIBA_CH_STEERING]);
    float arm_ch       = failsafe ? 0.0f : rc_to_unit(s_channels[BIBA_CH_ARM]);
    float speed_sel    = failsafe ? 0.0f : rc_to_unit(s_channels[BIBA_CH_SPEED_MODE]);
    float drive_sel    = failsafe ? 0.0f : rc_to_unit(s_channels[BIBA_CH_DRIVE_MODE]);
    float trim_ch      = failsafe ? 0.0f : rc_to_unit(s_channels[BIBA_CH_TRIM]);
    float beacon_ch    = failsafe ? 0.0f : rc_to_unit(s_channels[BIBA_CH_BEACON]);
    bool  beacon       = (beacon_ch > BIBA_ARM_THRESHOLD);

    /* ------------------------------------------------------------------ *
     * Arm / disarm
     * ------------------------------------------------------------------ */
    bool armed = (!failsafe) && (arm_ch > BIBA_ARM_THRESHOLD);

    /* Debug override: bypass CRSF inputs for bench testing with wheels
     * in the air.  Activated via serial command DBGON. */
    if (s_dbg_active) {
        failsafe     = false;
        armed        = s_dbg_arm;
        raw_throttle = s_dbg_thr;
        raw_steering = s_dbg_str;
    }

    /* Failsafe rising edge: play warning (distinct from normal disarm). */
    if (failsafe && !s_last_failsafe) {
        biba_melody_player_start(&s_player, &biba_melody_failsafe);
        biba_rpm_pi_reset(&s_rpm_pi_left);   /* D-04: hard reset on failsafe edge */
        biba_rpm_pi_reset(&s_rpm_pi_right);
        s_rpm_duty_left   = 0.0f;
        s_rpm_duty_right  = 0.0f;
        s_target_hz_left  = 0.0f;
        s_target_hz_right = 0.0f;
        biba_hal_ssr_set(false);          /* D-10: belt-and-suspenders SSR cut on failsafe */
    }
    s_last_failsafe = failsafe;

    if (armed && !s_armed) {
        /* Best-effort reset: clears possible BTS7960 thermal latch on arm edge.
         * Recovery is not guaranteed immediately; control loop still applies failsafe. */
        biba_bts7960_thermal_reset(BIBA_BTS7960_RESET_PULSE_US);
        printf("[biba] ARMED\r\n");
        biba_melody_player_start(&s_player, &biba_melody_arm);
    } else if (!armed && s_armed) {
        printf("[biba] DISARMED\r\n");
        biba_pid_reset(&s_heading_pid);
        if (!failsafe) {   /* failsafe already started its own melody */
            biba_melody_player_start(&s_player, &biba_melody_disarm);
        }
        /* Exit trim mode on disarm edge (safety) */
        s_trim_mode_active = false;
        biba_rpm_pi_reset(&s_rpm_pi_left);   /* D-04: hard reset on disarm edge */
        biba_rpm_pi_reset(&s_rpm_pi_right);
        s_rpm_duty_left   = 0.0f;
        s_rpm_duty_right  = 0.0f;
        s_target_hz_left  = 0.0f;
        s_target_hz_right = 0.0f;
    }
    s_armed = armed;
    biba_hal_ssr_set(armed);              /* D-10: SSR HIGH=armed, LOW=disarmed */

    /* ------------------------------------------------------------------ *
     * Speed mode  (3-position switch → 1/3 / 2/3 / full scale)
     * ------------------------------------------------------------------ */
    float speed_scale;
    if (speed_sel < BIBA_SPEED_MODE_LOW_THRESHOLD) {
        speed_scale = BIBA_SPEED_MODE_SLOW_SCALE;
    } else if (speed_sel > BIBA_SPEED_MODE_HIGH_THRESHOLD) {
        speed_scale = BIBA_SPEED_MODE_FAST_SCALE;
    } else {
        speed_scale = BIBA_SPEED_MODE_MEDIUM_SCALE;
    }

    /* Drive inputs pass through unscaled — the speed_scale is applied
     * AFTER the mixer on left_out/right_out (see below).  This keeps
     * steering authority constant regardless of throttle level, which
     * feels more predictable to the operator than the Python-era
     * envelope-limiter that bled steering when throttle saturated. */
    float throttle = raw_throttle;
    float steering = raw_steering;

    /* ------------------------------------------------------------------ *
     * Drive mode  (low position = MANUAL, else = STABILIZED)
     * In STABILIZED the heading-hold PID adds a small yaw correction.
     * The PID error is 0 until a real IMU feeds gyro data; when it does,
     * re-tune kp/kd in s_heading_cfg.
     * ------------------------------------------------------------------ */
    bool stabilized = (drive_sel > BIBA_DRIVE_MODE_LOW_THRESHOLD);
    if (stabilized && armed) {
        float correction = biba_pid_step(&s_heading_pid, &s_heading_cfg,
                                         0.0f, dt);
        steering = biba_clamp_unit(steering + correction);
    } else if (!armed) {
        biba_pid_reset(&s_heading_pid);
    }

    /* (Envelope limiter removed — output-side scaling below preserves
     *  the full steering authority at any throttle level.) */

    /* ------------------------------------------------------------------ *
     * Motor trim  (ported from biba-controller/main.py)
     *
     * Gesture: hold channels 0-3 all above BIBA_TRIM_GESTURE_THRESHOLD
     * for BIBA_TRIM_CONFIRM_HOLD_MS while disarmed.
     *   1st confirm  → enters trim mode  (play trim_enter, live trim via CH_TRIM)
     *   2nd confirm  → saves & exits      (play trim_exit, saved trim persists)
     *
     * Positive saved trim → attenuate right motor.
     * Negative saved trim → attenuate left motor.
     * ------------------------------------------------------------------ */
    bool trim_gesture = !armed && !failsafe &&
        (rc_to_unit(s_channels[0]) > BIBA_TRIM_GESTURE_THRESHOLD) &&
        (rc_to_unit(s_channels[1]) > BIBA_TRIM_GESTURE_THRESHOLD) &&
        (rc_to_unit(s_channels[2]) > BIBA_TRIM_GESTURE_THRESHOLD) &&
        (rc_to_unit(s_channels[3]) > BIBA_TRIM_GESTURE_THRESHOLD);
    if (trim_gesture) {
        if (s_trim_gesture_start_ms == 0u) {
            s_trim_gesture_start_ms = now;
        } else if (!s_trim_gesture_consumed &&
                   (now - s_trim_gesture_start_ms >= BIBA_TRIM_CONFIRM_HOLD_MS)) {
            if (s_trim_mode_active) {
                float live = trim_ch * BIBA_MOTOR_TRIM_MAX_EFFECT;
                if (live >  BIBA_MOTOR_TRIM_MAX_EFFECT) live =  BIBA_MOTOR_TRIM_MAX_EFFECT;
                if (live < -BIBA_MOTOR_TRIM_MAX_EFFECT) live = -BIBA_MOTOR_TRIM_MAX_EFFECT;
                s_saved_motor_trim = live;
                s_trim_mode_active = false;
                biba_melody_player_start(&s_player, &biba_melody_trim_exit);
                printf("[biba] Trim saved: %.3f\r\n", s_saved_motor_trim);
            } else {
                s_trim_mode_active = true;
                biba_melody_player_start(&s_player, &biba_melody_trim_enter);
                printf("[biba] Trim mode ON\r\n");
            }
            s_trim_gesture_consumed = true;
        }
    } else {
        s_trim_gesture_start_ms = 0u;
        s_trim_gesture_consumed = false;
    }
    /* TODO(trim): Motor trim was designed for open-loop duty control (Phase ≤6).
     * With RPM closed-loop (Phase 7+) the PI independently regulates each wheel
     * to the same target_hz, so duty-level trim has no meaningful effect and
     * may fight the integrator.  Options to revisit:
     *   a) Remove trim entirely — PI balances wheels via feedback.
     *   b) Rethink as target_hz offset trim (left_target_hz *= 1 ± trim) so
     *      the operator can permanently bias one wheel's setpoint if the two
     *      motors have different real-world characteristics.
     * For now trim is bypassed (trim = 0). The gesture/LED machinery is kept
     * so no user-visible behaviour is lost and the code compiles cleanly. */
    float trim = 0.0f;
    (void)trim_ch;  /* suppress unused-variable warning */

    /* ------------------------------------------------------------------ *
     * Mix → current limiter (thermal backoff) → drive
     * (trim bypassed — see TODO above)
     * ------------------------------------------------------------------ */
    float left_out = 0.0f, right_out = 0.0f;
    bool left_limited = false, right_limited = false;

    if (armed) {
        /* Vector-style mix: treat (throttle, steer) as a 2-D command and
         * project onto the L∞ ball of radius speed_scale.  L_raw=T+S and
         * R_raw=T−S together define the desired wheel-vector; we shrink
         * BOTH proportionally so neither exceeds speed_scale, preserving
         * the L:R ratio (≡ direction of motion).  This avoids the
         * envelope-limiter's behaviour where steering authority collapsed
         * once throttle saturated. */
        float t = biba_clamp_unit(throttle);
        float s = biba_clamp_unit(steering);
        float l_raw = t + s;
        float r_raw = t - s;
        float al = l_raw < 0.0f ? -l_raw : l_raw;
        float ar = r_raw < 0.0f ? -r_raw : r_raw;
        float peak = al > ar ? al : ar;
        float denom = peak > 1.0f ? peak : 1.0f;
        biba_mix_output_t mix;
        mix.left  = l_raw * speed_scale / denom;
        mix.right = r_raw * speed_scale / denom;
        biba_limit_result_t out = apply_drive_current_limits(mix);
        left_limited  = out.left_limited;
        right_limited = out.right_limited;
        left_out  = out.left;
        right_out = out.right;
        (void)trim;  /* trim disabled — see TODO above */
    }

    /* RPM closed-loop (forward) + open-loop pass-through (reverse).
     * Forward: IS ZC closes the loop via on_adc_done() IRQ.
     * Reverse: ZC only detects magnitude, not direction — pass raw mixer
     *          duty directly.  Reset PI on direction flip so the integrator
     *          starts clean when returning to forward. */
    {
        static bool s_prev_rev_left  = false;
        static bool s_prev_rev_right = false;

        bool rev_left  = (left_out  < -BIBA_MOTOR_DEADBAND);
        bool rev_right = (right_out < -BIBA_MOTOR_DEADBAND);

        /* Direction flip → reset PI + clear stale duty */
        if (rev_left != s_prev_rev_left) {
            biba_rpm_pi_reset(&s_rpm_pi_left);
            s_rpm_duty_left = 0.0f;
        }
        if (rev_right != s_prev_rev_right) {
            biba_rpm_pi_reset(&s_rpm_pi_right);
            s_rpm_duty_right = 0.0f;
        }
        s_prev_rev_left  = rev_left;
        s_prev_rev_right = rev_right;

        /* Forward target (deadband guard prevents stiction snap at neutral) */
        s_target_hz_left  = (!rev_left  && left_out  > BIBA_MOTOR_DEADBAND)
                            ? left_out  * STANDALONE_RPM_MAX_HZ : 0.0f;
        s_target_hz_right = (!rev_right && right_out > BIBA_MOTOR_DEADBAND)
                            ? right_out * STANDALONE_RPM_MAX_HZ : 0.0f;

        /* Reverse: bypass PI, use raw mixer duty directly */
        float duty_left  = rev_left  ? left_out  : s_rpm_duty_left;
        float duty_right = rev_right ? right_out : s_rpm_duty_right;
        if (failsafe || !armed) {
            duty_left  = 0.0f;
            duty_right = 0.0f;
        }
        left_out  = duty_left;
        right_out = duty_right;
    }
    (void)dt;   /* PI dt is configured via cfg.dt_s; tick dt no longer used here */

    /* Debug telemetry: emit per-tick line when debug override is active.
     * Format (CSV): DRIVE_DATA t_ms,thr,str,mix_L,mix_R,tgt_L,tgt_R,
     *                           meas_L,meas_R,duty_L,duty_R,int_L,int_R
     * Values: thr/str/mix/duty in [-1,1]; tgt/meas in Hz; int dimensionless. */
    if (s_dbg_active) {
        /* Reconstruct pre-RPM mixer outputs from target Hz (forward) or
         * duty (reverse) — the signed mixer outputs before the PI block. */
        float mix_l = s_target_hz_left  > 0.0f
                      ? s_target_hz_left  / STANDALONE_RPM_MAX_HZ : left_out;
        float mix_r = s_target_hz_right > 0.0f
                      ? s_target_hz_right / STANDALONE_RPM_MAX_HZ : right_out;
        printf("DRIVE_DATA %lu,%.3f,%.3f,%.3f,%.3f,%.1f,%.1f,%.1f,%.1f,%.3f,%.3f,%.4f,%.4f\r\n",
               now,
               throttle, steering,
               mix_l, mix_r,
               s_target_hz_left, s_target_hz_right,
               s_meas_hz_left, s_meas_hz_right,
               left_out, right_out,
               s_rpm_pi_left.integral, s_rpm_pi_right.integral);
    }

    /* If actively driving, motors are needed — interrupt melodies.
     * Exception: the intentional reverse backup pip must not be self-cancelled. */
    bool control_active = armed &&
        ((throttle > BIBA_MOTOR_DEADBAND  || throttle < -BIBA_MOTOR_DEADBAND) ||
         (steering > BIBA_MOTOR_DEADBAND  || steering < -BIBA_MOTOR_DEADBAND));
    if (control_active && !s_reverse_pip_active) {
        biba_melody_player_stop(&s_player);
    }

    bool going_reverse = armed &&
        (left_out  < -BIBA_MOTOR_DEADBAND) &&
        (right_out < -BIBA_MOTOR_DEADBAND);
    s_reversing = going_reverse;

#if BIBA_REVERSE_PIP_ENABLED
    /* Detect reverse pip finishing */
    if (s_reverse_pip_active && !s_player.active) {
        s_reverse_pip_active = false;
    }
    /* Reverse: stop pip if no longer going backwards */
    if (!going_reverse) {
        if (s_reverse_pip_active) {
            biba_melody_player_stop(&s_player);
            s_reverse_pip_active = false;
        }
        s_reverse_pip_next_ms = 0u;
    }
    /* Schedule next pip while reversing */
    if (going_reverse && !s_player.active && now >= s_reverse_pip_next_ms) {
        biba_melody_player_start(&s_player, &biba_melody_backup_pip);
        s_reverse_pip_active = true;
        s_reverse_pip_next_ms = now + BIBA_REVERSE_PIP_INTERVAL_MS;
    }
#else
    if (s_reverse_pip_active) {
        biba_melody_player_stop(&s_player);
    }
    s_reverse_pip_active = false;
    s_reverse_pip_next_ms = 0u;
#endif

    /* Beacon: play SOS every 8 s while CH_BEACON is high and not driving.
     * Priority melodies (failsafe/arm/disarm) may run first; the interval
     * timer keeps firing so the beacon stays audible on schedule. */
    if (beacon && !control_active) {
        if (!s_player.active && now >= s_sos_next_ms) {
            biba_melody_player_start(&s_player, &biba_melody_sos);
            s_sos_next_ms = now + 8000u;
        }
    } else if (!beacon) {
        if (s_beacon_active) {
            /* Beacon just switched off — stop SOS immediately. */
            biba_melody_player_stop(&s_player);
        }
        /* Reset timer so next activation fires immediately. */
        s_sos_next_ms = 0u;
    }
    s_beacon_active = beacon;

    /* Advance melody state machine.
     * During reverse pip: use biased tick so motors keep driving while beeping.
     * All other melodies use standard symmetric push-pull (zero net torque). */
    if (s_reverse_pip_active) {
        biba_melody_player_tick_biased(&s_player, now, left_out, right_out);
    } else {
        biba_melody_player_tick(&s_player, now);
    }

    /* Drive motors only when audio is not occupying the PWM hardware. */
    if (!s_player.active) {
        biba_bts7960_drive(left_out, right_out);
    }

    /* Update RGB status LED. */
    update_rgb_led(failsafe, armed, s_trim_mode_active,
                   s_reversing, beacon, now);

    /* ------------------------------------------------------------------ *
     * Telemetry / DATA_READY / status LED
     * ------------------------------------------------------------------ */
    uint32_t scan_count = biba_hal_adc_scan_count();
    if (scan_count != s_last_scan_count) {
        s_last_scan_count = scan_count;
        biba_motor_current_t il = biba_current_sense_left();
        biba_motor_current_t ir = biba_current_sense_right();
        biba_telemetry_input_t inputs = {
            .setpoint_left    = left_out,
            .setpoint_right   = right_out,
            .current_left_a   = il.current_a,
            .current_right_a  = ir.current_a,
            .wheel_rpm_left_hz  = s_rpm_pi_left.meas_ema,
            .wheel_rpm_right_hz = s_rpm_pi_right.meas_ema,
            .crsf_rssi        = s_link.uplink_rssi_1,
            .crsf_link_quality = s_link.uplink_link_quality,
            .crsf_snr_db      = s_link.uplink_snr,
            .error_flags      = (failsafe      ? BIBA_PROTO_FLAG_FAILSAFE      : 0u)
                              | (failsafe      ? 0u : BIBA_PROTO_FLAG_CRSF_ALIVE)
                              | (!armed        ? BIBA_PROTO_FLAG_FAILSAFE       : 0u)
                              | (left_limited || right_limited
                                               ? BIBA_PROTO_FLAG_CURRENT_LIMIT  : 0u),
            .seq = s_telemetry_seq++,
        };
        biba_proto_telemetry_t tlm;
        biba_telemetry_collect(&inputs, &tlm);
        (void)tlm; /* CRSF telemetry uplink is a follow-up patch */
        biba_hal_data_ready_pulse();
        biba_hal_status_led_set(armed);   /* LED on = armed (not just "not failsafe") */

        /* Log at ~1 Hz */
        static uint32_t s_last_log_ms;
        if (now - s_last_log_ms >= 1000u) {
            s_last_log_ms = now;
            int spd = (speed_scale < 0.4f) ? 1 : (speed_scale < 0.8f) ? 2 : 3;
            int current_limited = (left_limited || right_limited) ? 1 : 0;
            printf("[biba] t=%lu fs=%d arm=%d spd=%d stab=%d thr=%d str=%d L=%d R=%d cl=%d rssi=%d lq=%d\r\n",
                   now, (int)failsafe, (int)armed, spd, (int)stabilized,
                   (int)(raw_throttle * 100), (int)(raw_steering * 100),
                   (int)(left_out * 100), (int)(right_out * 100),
                   current_limited,
                   s_link.uplink_rssi_1, s_link.uplink_link_quality);

            /* CRSF/DMA health line every 5 s */
            static uint32_t s_last_diag_ms;
            if (now - s_last_diag_ms >= 5000u) {
                s_last_diag_ms = now;
                biba_hal_crsf_diag_t d = biba_hal_crsf_diag();
                printf("[biba] CRSF diag: dma_init=%lu ndtr=%lu err=0x%lx"
                       " rx_st=0x%lx tx_st=0x%lx SR=0x%lx CR1=0x%lx"
                       " RCC_APB1=%lx tx_ok=%lu tx_fail=%lu"
                       " | rx_b=%lu frm=%lu bad=%lu ch=%lu\r\n",
                       d.dma_init_status, d.dma_ndtr,
                       d.uart_error_code, d.uart_rx_state, d.uart_tx_state,
                       d.uart_sr, d.uart_cr1, d.rcc_apb1enr,
                       s_dbg_tx_ok, s_dbg_tx_fail,
                       s_dbg_bytes_total, s_dbg_frames_ok,
                       s_dbg_frames_bad, s_dbg_ch_frames);
            }
        }
    }
}
