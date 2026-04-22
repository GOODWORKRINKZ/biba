/* Standalone mode: the STM32 owns the whole low-level biba behaviour.
 *
 *     CRSF RX -> parser -> mixer -> heading-hold PID -> limiter -> PWM
 *
 * Telemetry is aggregated at BIBA_TELEMETRY_PUBLISH_HZ for future CRSF
 * battery-sensor uplink, and the DATA_READY line still pulses so an
 * attached debugger / SBC can piggy-back if wired in. */

#include <string.h>

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

#define CRSF_BUFFER_SIZE 192

static uint8_t  s_crsf_buffer[CRSF_BUFFER_SIZE];
static size_t   s_crsf_fill;
static biba_failsafe_t s_crsf_failsafe;

static biba_crsf_link_stats_t s_link;
static uint16_t s_channels[CRSF_RC_CHANNEL_COUNT];
static uint32_t s_last_scan_count;
static uint32_t s_last_tick_ms;
static uint8_t  s_telemetry_seq;

static biba_pid_state_t s_heading_pid;
static const biba_pid_config_t s_heading_cfg = {
    .kp = 0.6f, .ki = 0.0f, .kd = 0.02f,
    .output_limit = 0.5f, .integral_limit = 0.5f
};

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
}

static void ingest_crsf(void)
{
    size_t free_space = CRSF_BUFFER_SIZE - s_crsf_fill;
    if (free_space > 0) {
        s_crsf_fill += biba_hal_crsf_read(&s_crsf_buffer[s_crsf_fill], free_space);
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
            continue;
        }
        if (type == CRSF_FRAMETYPE_RC_CHANNELS) {
            if (biba_crsf_unpack_channels(payload, payload_len, s_channels)) {
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
    float dt = (float)(now - s_last_tick_ms) / 1000.0f;
    s_last_tick_ms = now;

    bool failsafe = biba_failsafe_tick(&s_crsf_failsafe, now);

    float throttle = 0.0f;
    float steer = 0.0f;
    if (!failsafe) {
        throttle = rc_to_unit(s_channels[1]);   /* CH2 */
        steer    = rc_to_unit(s_channels[0]);   /* CH1 */
    } else {
        biba_pid_reset(&s_heading_pid);
    }

    /* Heading-hold correction: fold in a small PID drive on steer error.
     * Without IMU the PID just becomes a no-op (error = 0). */
    float heading_correction = biba_pid_step(&s_heading_pid, &s_heading_cfg,
                                             0.0f, dt);
    steer = biba_clamp_unit(steer + heading_correction);

    biba_mix_output_t mix = biba_mix_differential(throttle, steer);

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
    if (failsafe) {
        out.left = 0.0f;
        out.right = 0.0f;
    }
    biba_bts7960_drive(out.left, out.right);

    /* Publish telemetry / pulse DATA_READY on each fresh ADC scan. */
    uint32_t scan_count = biba_hal_adc_scan_count();
    if (scan_count != s_last_scan_count) {
        s_last_scan_count = scan_count;
        biba_telemetry_input_t inputs = {
            .setpoint_left = out.left,
            .setpoint_right = out.right,
            .current_left_a = il.current_a,
            .current_right_a = ir.current_a,
            .crsf_rssi = s_link.uplink_rssi_1,
            .crsf_link_quality = s_link.uplink_link_quality,
            .crsf_snr_db = s_link.uplink_snr,
            .error_flags = (failsafe ? BIBA_PROTO_FLAG_FAILSAFE : 0)
                         | (failsafe ? 0 : BIBA_PROTO_FLAG_CRSF_ALIVE)
                         | (out.left_limited || out.right_limited ? BIBA_PROTO_FLAG_CURRENT_LIMIT : 0),
            .seq = s_telemetry_seq++,
        };
        biba_proto_telemetry_t tlm;
        biba_telemetry_collect(&inputs, &tlm);
        (void)tlm; /* CRSF telemetry uplink is a follow-up patch */
        biba_hal_data_ready_pulse();
        biba_hal_status_led_set(!failsafe);
    }
}
