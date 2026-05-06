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

    /* --- UART loopback self-test (requires PB10 → PB11 jumper) ----------
     * Short PB10 to PB11, reset, check the log line below.
     * If loopback_ok=1 — UART/DMA hardware is fine, problem is EP01/wiring.
     * If loopback_ok=0 — UART or DMA init failed on this board. */
    biba_hal_delay_ms(1);               /* let DMA arm */
    uint8_t lb_byte = 0xA5u;
    biba_hal_crsf_write(&lb_byte, 1);
    biba_hal_delay_ms(1);               /* ~20 µs at 420 kbaud, 1 ms is plenty */
    uint8_t lb_buf[1];
    int loopback_ok = (biba_hal_crsf_read(lb_buf, 1) == 1 && lb_buf[0] == 0xA5u);
    printf("[biba] UART loopback: loopback_ok=%d (need PB10->PB11 jumper)\r\n", loopback_ok);
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

        /* Log at ~1 Hz to avoid flooding semihosting.
         * Use integer-scaled values to avoid %f / soft-float stack bloat. */
        static uint32_t s_last_log_ms;
        uint32_t now = biba_hal_now_ms();
        if (now - s_last_log_ms >= 1000u) {
            s_last_log_ms = now;
            printf("[biba] t=%lu fs=%d L=%d R=%d rssi=%d lq=%d"
                   " | rx_b=%lu frm=%lu bad=%lu ch=%lu ch0=%u ch1=%u\r\n",
                   now, failsafe,
                   (int)(out.left * 100), (int)(out.right * 100),
                   s_link.uplink_rssi_1, s_link.uplink_link_quality,
                   s_dbg_bytes_total, s_dbg_frames_ok, s_dbg_frames_bad, s_dbg_ch_frames,
                   s_channels[0], s_channels[1]);

            /* Extra UART/DMA health line every 5 s to diagnose rx_b=0 */
            static uint32_t s_last_diag_ms;
            if (now - s_last_diag_ms >= 5000u) {
                s_last_diag_ms = now;
                biba_hal_crsf_diag_t d = biba_hal_crsf_diag();
                printf("[biba] CRSF diag: dma_init=%lu ndtr=%lu err=0x%lx rx_st=0x%lx tx_st=0x%lx SR=0x%lx CR1=0x%lx RCC_APB1=%lx tx_ok=%lu tx_fail=%lu\r\n",
                       d.dma_init_status, d.dma_ndtr,
                       d.uart_error_code, d.uart_rx_state, d.uart_tx_state,
                       d.uart_sr, d.uart_cr1, d.rcc_apb1enr,
                       s_dbg_tx_ok, s_dbg_tx_fail);
            }
        }
    }
}
