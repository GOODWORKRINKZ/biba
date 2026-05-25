#ifndef BIBA_TELEMETRY_H
#define BIBA_TELEMETRY_H

#include "proto/biba_proto.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Aggregate the latest telemetry snapshot from the control loop and the
 * drivers. The resulting struct is what the SPI slave clocks out on the
 * MISO line and what standalone mode ships over CRSF. */
typedef struct {
    float   setpoint_left;
    float   setpoint_right;
    float   current_left_a;
    float   current_right_a;
    uint16_t vbat_mv;          /* battery voltage from 3DR Power Module (mV) */
    float   ibat_a;            /* battery current from 3DR Power Module (A)  */
    float   temperature_c;     /* ambient temperature from AHT30 (°C)        */
    float   humidity_pct;      /* relative humidity from AHT30 (%)           */
    float   wheel_rpm_left_hz;   /* IS_LEFT ZC frequency in Hz; 0.0 = invalid/no signal */
    float   wheel_rpm_right_hz;  /* IS_RIGHT ZC frequency in Hz; 0.0 = invalid/no signal */
    uint8_t crsf_rssi;
    uint8_t crsf_link_quality;
    int8_t  crsf_snr_db;
    uint8_t error_flags;
    uint8_t seq;
} biba_telemetry_input_t;

void biba_telemetry_collect(const biba_telemetry_input_t *inputs,
                            biba_proto_telemetry_t *out);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_TELEMETRY_H */
