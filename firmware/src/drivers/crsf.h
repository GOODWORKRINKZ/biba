#ifndef BIBA_CRSF_H
#define BIBA_CRSF_H

/* CRSF (Crossfire/ExpressLRS) frame parser.
 *
 * Only the subset BiBa needs: RC channels and link statistics. Mirrors
 * behaviour expected by tests/test_crsf.py so both implementations stay
 * in lockstep. Pure-C so the native test env can exercise it with gcc. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CRSF_SYNC_BYTE              0xC8u
#define CRSF_MAX_FRAME_SIZE         64u

#define CRSF_FRAMETYPE_RC_CHANNELS  0x16u
#define CRSF_FRAMETYPE_LINK_STATS   0x14u
#define CRSF_FRAMETYPE_BATTERY      0x08u

#define CRSF_RC_CHANNEL_COUNT       16u

typedef struct {
    uint8_t uplink_rssi_1;
    uint8_t uplink_rssi_2;
    uint8_t uplink_link_quality;
    int8_t  uplink_snr;
    uint8_t active_antenna;
    uint8_t rf_mode;
    uint8_t uplink_tx_power;
    uint8_t downlink_rssi;
    uint8_t downlink_link_quality;
    int8_t  downlink_snr;
} biba_crsf_link_stats_t;

/* DVB-S2 CRC8 (poly 0xD5). */
uint8_t biba_crsf_crc8_dvb_s2(const uint8_t *data, size_t len);

/* Decode one full CRSF frame (sync..crc) out of `frame`. Returns the
 * frame type on success, 0 on validation failure. `payload_len_out` is
 * the number of bytes at `*payload_out`, which points inside `frame`. */
uint8_t biba_crsf_parse_frame(const uint8_t *frame,
                              size_t frame_len,
                              const uint8_t **payload_out,
                              size_t *payload_len_out);

/* Pop one validated frame from `buffer` of size `*buffer_len`, moving
 * the remaining bytes to the front and updating `*buffer_len`. Returns
 * the frame type (non-zero) or 0 if no complete frame is available.
 * Oversized/malformed frames are discarded by advancing one byte. */
uint8_t biba_crsf_pop_frame(uint8_t *buffer,
                            size_t *buffer_len,
                            uint8_t *out_frame,
                            size_t out_cap,
                            size_t *out_frame_len);

/* Unpack the 22-byte packed RC payload into 16 channel values [0..2047]. */
bool biba_crsf_unpack_channels(const uint8_t *payload,
                               size_t payload_len,
                               uint16_t channels[CRSF_RC_CHANNEL_COUNT]);

/* Parse a 10-byte link statistics payload. */
bool biba_crsf_parse_link_stats(const uint8_t *payload,
                                size_t payload_len,
                                biba_crsf_link_stats_t *stats);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_CRSF_H */
