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
