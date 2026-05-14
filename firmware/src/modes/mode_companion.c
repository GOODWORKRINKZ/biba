/* Companion mode: the SBC is master and owns the setpoint, the STM32 is
 * an SPI-slave that applies the commanded duties (with its own current
 * limiter) and pushes telemetry back on the MISO side of every shift. */

#include <string.h>

#include "mode_dispatcher.h"

#include "biba_config.h"
#include "app/control_loop.h"
#include "app/failsafe.h"
#include "app/telemetry.h"
#include "drivers/bts7960.h"
#include "drivers/current_sense.h"
#include "hal/biba_hal.h"
#include "proto/biba_proto.h"

static uint8_t s_rx_frame[BIBA_PROTO_FRAME_SIZE];
static uint8_t s_tx_frame[BIBA_PROTO_FRAME_SIZE];
static biba_failsafe_t s_spi_failsafe;
static uint8_t s_telemetry_seq;
static float   s_setpoint_left;
static float   s_setpoint_right;
static bool    s_armed;

static float q15_to_unit(int16_t q)
{
    float v = (float)q / 32767.0f;
    return biba_clamp_unit(v);
}

static void handle_command(const biba_proto_frame_t *cmd)
{
    switch (cmd->cmd) {
    case BIBA_CMD_PING:
        break;
    case BIBA_CMD_ARM:
        s_armed = true;
        biba_bts7960_set_enabled(true);
        break;
    case BIBA_CMD_DISARM:
        s_armed = false;
        s_setpoint_left = 0.0f;
        s_setpoint_right = 0.0f;
        biba_bts7960_set_enabled(false);
        break;
    case BIBA_CMD_SET_SETPOINT:
        if (cmd->payload_len >= 4) {
            int16_t left  = (int16_t)(cmd->payload[0] | (cmd->payload[1] << 8));
            int16_t right = (int16_t)(cmd->payload[2] | (cmd->payload[3] << 8));
            s_setpoint_left  = q15_to_unit(left);
            s_setpoint_right = q15_to_unit(right);
        }
        break;
    case BIBA_CMD_GET_TELEMETRY:
    case BIBA_CMD_SET_CONFIG:
        /* Follow-up patches handle the long-tail commands. */
        break;
    case BIBA_CMD_SET_MOTOR_AUDIO:
        if (cmd->payload_len >= sizeof(biba_proto_motor_audio_t)) {
            biba_proto_motor_audio_t m;
            memcpy(&m, cmd->payload, sizeof(m));
            uint32_t freq[4];
            float    duty[4];
            for (unsigned i = 0; i < 4; ++i) {
                freq[i] = m.freq_hz[i];
                duty[i] = (float)m.duty_q8[i] / 255.0f;
            }
            /* Ignore the return value: on targets without per-channel
             * timers this is a no-op by design. */
            (void)biba_hal_motor_audio_set_all(freq, duty);
        }
        break;
    default:
        break;
    }
}

static void build_telemetry_frame(uint8_t flags, float left_cmd, float right_cmd,
                                  biba_motor_current_t il, biba_motor_current_t ir)
{
    biba_telemetry_input_t inputs = {
        .setpoint_left = left_cmd,
        .setpoint_right = right_cmd,
        .current_left_a = il.current_a,
        .current_right_a = ir.current_a,
        .crsf_rssi = 0,
        .crsf_link_quality = 0,
        .crsf_snr_db = 0,
        .error_flags = flags,
        .seq = s_telemetry_seq,
    };
    biba_proto_telemetry_t tlm;
    biba_telemetry_collect(&inputs, &tlm);
    biba_proto_encode_telemetry(s_telemetry_seq++, flags, &tlm,
                                s_tx_frame, sizeof(s_tx_frame));
}

void biba_mode_companion_init(void)
{
    memset(s_rx_frame, 0, sizeof(s_rx_frame));
    memset(s_tx_frame, 0, sizeof(s_tx_frame));
    biba_failsafe_init(&s_spi_failsafe, BIBA_SPI_LINK_TIMEOUT_MS);
    s_setpoint_left = 0.0f;
    s_setpoint_right = 0.0f;
    s_armed = false;

    /* Seed the outbound buffer with a benign telemetry frame so the very
     * first SPI shift already sees valid data. */
    biba_motor_current_t zero = { 0.0f, true };
    build_telemetry_frame(BIBA_PROTO_FLAG_FAILSAFE, 0.0f, 0.0f, zero, zero);
    biba_hal_spi_slave_arm(s_tx_frame, s_rx_frame);
}

void biba_mode_companion_tick(void)
{
    uint32_t now = biba_hal_now_ms();

    /* Harvest completed transactions and re-arm the slave *immediately*
     * with whatever telemetry we have so far. Re-arming after the
     * heavy build_telemetry_frame() block below would leave a window in
     * which the SBC could clock the bus, get nothing, and time out. The
     * tx buffer is then refreshed in place by build_telemetry_frame()
     * before the next clock edge fires (the SBC stays idle for several
     * milliseconds between transactions). */
    bool transaction_done = biba_hal_spi_slave_poll();
    if (transaction_done) {
        biba_proto_frame_t cmd;
        if (biba_proto_decode(s_rx_frame, sizeof(s_rx_frame), &cmd) == BIBA_PROTO_OK) {
            biba_failsafe_mark_fresh(&s_spi_failsafe, now);
            handle_command(&cmd);
        }
        biba_hal_spi_slave_arm(s_tx_frame, s_rx_frame);
    }

    bool failsafe = biba_failsafe_tick(&s_spi_failsafe, now) || !s_armed;

    biba_motor_current_t il = biba_current_sense_left();
    biba_motor_current_t ir = biba_current_sense_right();

    biba_motor_limit_t lim = {
        .current_limit_a = BIBA_LEFT_MAX_CURRENT_A,
        .power_limit_w = BIBA_LEFT_MAX_POWER_W,
        .supply_voltage_v = BIBA_FALLBACK_SUPPLY_V,
    };
    biba_motor_limit_t rim = {
        .current_limit_a = BIBA_RIGHT_MAX_CURRENT_A,
        .power_limit_w = BIBA_RIGHT_MAX_POWER_W,
        .supply_voltage_v = BIBA_FALLBACK_SUPPLY_V,
    };

    float left_cmd  = failsafe ? 0.0f : s_setpoint_left;
    float right_cmd = failsafe ? 0.0f : s_setpoint_right;
    biba_limit_result_t out = biba_apply_motor_limits(left_cmd, right_cmd,
                                                       il, ir, lim, rim);
    biba_bts7960_drive(out.left, out.right);

    uint8_t flags = (s_armed ? BIBA_PROTO_FLAG_ARMED : 0)
                  | (failsafe ? BIBA_PROTO_FLAG_FAILSAFE : 0)
                  | (out.left_limited || out.right_limited ? BIBA_PROTO_FLAG_CURRENT_LIMIT : 0);
    /* Refreshes s_tx_frame in place. The DMA is reading from this same
     * buffer if a transaction is mid-flight; the SBC only sees the new
     * contents on the *next* transaction it initiates, which is the
     * intended semantics. */
    build_telemetry_frame(flags, out.left, out.right, il, ir);

    static uint32_t s_last_scan_count;
    uint32_t scan_count = biba_hal_adc_scan_count();
    if (scan_count != s_last_scan_count) {
        s_last_scan_count = scan_count;
        biba_hal_data_ready_pulse();
        biba_hal_status_led_set(!failsafe);
    }
}
