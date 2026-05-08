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
#include "app/telemetry.h"
#include "drivers/bts7960.h"
#include "drivers/crsf.h"
#include "drivers/current_sense.h"
#include "hal/biba_hal.h"
#include "proto/biba_proto.h"
#include "app/melody.h"
#include "app/pcm_sounds.h"
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
static bool s_beacon_active;
static uint32_t s_sos_next_ms;   /* earliest time for next SOS repeat */
static biba_melody_player_t s_player;

static float rc_to_unit(uint16_t v)
{
    /* Standard CRSF channel: 172..1811 maps to -1..+1. */
    float normalised = ((float)v - 992.0f) / 819.0f;
    return biba_clamp_unit(normalised);
}

void biba_mode_standalone_init(void)
{
    biba_hal_crsf_begin(BIBA_CRSF_BAUD);
    biba_failsafe_init(&s_crsf_failsafe, BIBA_CRSF_TIMEOUT_MS);
    biba_pid_reset(&s_heading_pid);
    s_last_tick_ms = biba_hal_now_ms();
    biba_bts7960_set_enabled(true);

    /* Suppress failsafe melody on the very first tick (no RC lock-in yet). */
    s_last_failsafe = true;

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

    /* Failsafe rising edge: play warning (distinct from normal disarm). */
    if (failsafe && !s_last_failsafe) {
        biba_melody_player_start(&s_player, &biba_melody_failsafe);
    }
    s_last_failsafe = failsafe;

    if (armed && !s_armed) {
        printf("[biba] ARMED\r\n");
        biba_melody_player_stop(&s_player);
        biba_hal_motor_pcm_play(pcm_arm_data, pcm_arm_count, pcm_arm_rate);
    } else if (!armed && s_armed) {
        printf("[biba] DISARMED\r\n");
        biba_pid_reset(&s_heading_pid);
        if (!failsafe) {   /* failsafe already started its own melody */
            biba_melody_player_stop(&s_player);
            biba_hal_motor_pcm_play(pcm_disarm_data, pcm_disarm_count, pcm_disarm_rate);
        }
    }
    s_armed = armed;

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

    /* Scale drive inputs: tank-mix → scale → un-mix  (≡ Python
     * _scale_drive_inputs_for_speed_mode).  Without clamping this
     * simplifies to throttle *= s, steering *= s, but the full form
     * handles corner cases at the unit-circle boundary correctly. */
    float throttle, steering;
    {
        float ml = biba_clamp_unit(raw_throttle + raw_steering);
        float mr = biba_clamp_unit(raw_throttle - raw_steering);
        float sl = ml * speed_scale;
        float sr = mr * speed_scale;
        throttle = (sl + sr) * 0.5f;
        steering = (sl - sr) * 0.5f;
    }

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

    /* Limit throttle + steering to the speed-mode envelope (≡ Python
     * _limit_drive_output_for_speed_mode). */
    {
        float lim_thr = throttle;
        if (lim_thr >  speed_scale) lim_thr =  speed_scale;
        if (lim_thr < -speed_scale) lim_thr = -speed_scale;
        float steer_lim = speed_scale - (lim_thr < 0.0f ? -lim_thr : lim_thr);
        if (steer_lim < 0.0f) steer_lim = 0.0f;
        float lim_str = steering;
        if (lim_str >  steer_lim) lim_str =  steer_lim;
        if (lim_str < -steer_lim) lim_str = -steer_lim;
        throttle = lim_thr;
        steering = lim_str;
    }

    /* ------------------------------------------------------------------ *
     * Motor trim  (live from CH_TRIM — no persistence in standalone mode)
     * Positive trim → attenuate right motor.
     * Negative trim → attenuate left motor.
     * ------------------------------------------------------------------ */
    float trim = trim_ch * BIBA_MOTOR_TRIM_MAX_EFFECT;
    if (trim >  BIBA_MOTOR_TRIM_MAX_EFFECT) trim =  BIBA_MOTOR_TRIM_MAX_EFFECT;
    if (trim < -BIBA_MOTOR_TRIM_MAX_EFFECT) trim = -BIBA_MOTOR_TRIM_MAX_EFFECT;

    /* ------------------------------------------------------------------ *
     * Mix → current limiter → trim → drive
     * ------------------------------------------------------------------ */
    float left_out = 0.0f, right_out = 0.0f;
    bool left_limited = false, right_limited = false;

    if (armed) {
        biba_mix_output_t mix = biba_mix_differential(throttle, steering);

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
        biba_limit_result_t out = biba_apply_motor_limits(mix.left, mix.right,
                                                           il, ir, lim, rim);
        left_limited  = out.left_limited;
        right_limited = out.right_limited;
        left_out  = out.left;
        right_out = out.right;

        /* Apply trim */
        if (trim > 0.0f) {
            right_out *= (1.0f - trim);
        } else if (trim < 0.0f) {
            left_out *= (1.0f + trim);   /* trim is negative → reduces left */
        }
    }

    /* If actively driving, motors are needed — interrupt any melody or PCM. */
    bool control_active = armed &&
        ((throttle > BIBA_MOTOR_DEADBAND  || throttle < -BIBA_MOTOR_DEADBAND) ||
         (steering > BIBA_MOTOR_DEADBAND  || steering < -BIBA_MOTOR_DEADBAND));
    if (control_active) {
        biba_melody_player_stop(&s_player);
        biba_hal_motor_pcm_stop();
    }

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

    /* Advance melody state machine (no-op when idle). */
    biba_melody_player_tick(&s_player, now);

    /* Drive motors only when audio/PCM is not occupying the PWM hardware. */
    if (!s_player.active && !biba_hal_motor_pcm_active()) {
        biba_bts7960_drive(left_out, right_out);
    }

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
            printf("[biba] t=%lu fs=%d arm=%d spd=%d stab=%d thr=%d str=%d L=%d R=%d rssi=%d lq=%d\r\n",
                   now, (int)failsafe, (int)armed, spd, (int)stabilized,
                   (int)(raw_throttle * 100), (int)(raw_steering * 100),
                   (int)(left_out * 100), (int)(right_out * 100),
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
