#include "telemetry.h"

#include <string.h>

#include "hal/biba_hal.h"
#include "drivers/imu.h"
#include "drivers/voltage_sense.h"

static int16_t clamp_i16(int32_t v)
{
    if (v > 32767) return 32767;
    if (v < -32768) return -32768;
    return (int16_t)v;
}

void biba_telemetry_collect(const biba_telemetry_input_t *inputs,
                            biba_proto_telemetry_t *out)
{
    if (inputs == NULL || out == NULL) return;
    memset(out, 0, sizeof(*out));

    out->setpoint_left_q15  = clamp_i16((int32_t)(inputs->setpoint_left  * 32767.0f));
    out->setpoint_right_q15 = clamp_i16((int32_t)(inputs->setpoint_right * 32767.0f));
    out->current_left_ma  = clamp_i16((int32_t)(inputs->current_left_a  * 1000.0f));
    out->current_right_ma = clamp_i16((int32_t)(inputs->current_right_a * 1000.0f));

    out->vbat_mv     = biba_voltage_sense_vbat_mv();
    out->rail_12v_mv = biba_voltage_sense_rail_mv();
    out->ibat_ma     = clamp_i16((int32_t)(biba_voltage_sense_ibat_a() * 1000.0f));

    /* Temperature and humidity: pre-populated by a low-rate task (≤1 Hz)
     * that calls aht30_read(); copied directly from the inputs struct.
     * aht30_read() blocks ~80 ms and must NOT be called here. */
    out->temperature_cdeg = clamp_i16((int32_t)(inputs->temperature_c * 100.0f));
    out->humidity_q8      = (inputs->humidity_pct > 100.0f) ? 100u
                          : (inputs->humidity_pct < 0.0f)   ? 0u
                          : (uint8_t)inputs->humidity_pct;

    /* IS-signal wheel RPM (ZC frequency x10 for 0.1 Hz resolution). 0 = invalid. */
    {
        float lhz = inputs->wheel_rpm_left_hz;
        float rhz = inputs->wheel_rpm_right_hz;
        if (lhz < 0.0f) lhz = 0.0f;
        if (rhz < 0.0f) rhz = 0.0f;
        uint32_t lq = (uint32_t)(lhz * 10.0f + 0.5f);
        uint32_t rq = (uint32_t)(rhz * 10.0f + 0.5f);
        if (lq > 0xFFFFu) lq = 0xFFFFu;
        if (rq > 0xFFFFu) rq = 0xFFFFu;
        out->wheel_rpm_left_hz10  = (uint16_t)lq;
        out->wheel_rpm_right_hz10 = (uint16_t)rq;
    }

    biba_imu_sample_t imu;
    if (biba_imu_read(&imu)) {
        out->gyro_x_cdps = imu.gyro_x_cdps;
        out->gyro_y_cdps = imu.gyro_y_cdps;
        out->gyro_z_cdps = imu.gyro_z_cdps;
        out->accel_x_mg  = imu.accel_x_mg;
        out->accel_y_mg  = imu.accel_y_mg;
        out->accel_z_mg  = imu.accel_z_mg;
    }

    out->crsf_rssi         = inputs->crsf_rssi;
    out->crsf_link_quality = inputs->crsf_link_quality;
    out->crsf_snr_db       = inputs->crsf_snr_db;
    out->error_flags       = inputs->error_flags;
    out->uptime_ms         = biba_hal_now_ms();
}
