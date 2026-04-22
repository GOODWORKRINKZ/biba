#include "crsf.h"

#include <string.h>

uint8_t biba_crsf_crc8_dvb_s2(const uint8_t *data, size_t len)
{
    uint8_t crc = 0;
    if (data == NULL) return crc;
    for (size_t i = 0; i < len; ++i) {
        crc ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            if (crc & 0x80u) {
                crc = (uint8_t)((crc << 1) ^ 0xD5u);
            } else {
                crc = (uint8_t)(crc << 1);
            }
        }
    }
    return crc;
}

uint8_t biba_crsf_parse_frame(const uint8_t *frame,
                              size_t frame_len,
                              const uint8_t **payload_out,
                              size_t *payload_len_out)
{
    if (frame == NULL || frame_len < 4) return 0;
    if (frame[0] != CRSF_SYNC_BYTE) return 0;
    uint8_t length = frame[1];
    if (length < 2) return 0;
    if ((size_t)length + 2 != frame_len) return 0;

    const uint8_t *body = &frame[2];
    size_t body_len = (size_t)length - 1;
    uint8_t expected = biba_crsf_crc8_dvb_s2(body, body_len);
    if (expected != frame[frame_len - 1]) return 0;

    if (payload_out != NULL) *payload_out = &frame[3];
    if (payload_len_out != NULL) *payload_len_out = body_len - 1;
    return frame[2];
}

uint8_t biba_crsf_pop_frame(uint8_t *buffer,
                            size_t *buffer_len,
                            uint8_t *out_frame,
                            size_t out_cap,
                            size_t *out_frame_len)
{
    if (buffer == NULL || buffer_len == NULL) return 0;
    size_t have = *buffer_len;

    /* Skip noise until a sync byte is at the front. */
    while (have > 0 && buffer[0] != CRSF_SYNC_BYTE) {
        memmove(buffer, buffer + 1, have - 1);
        have -= 1;
    }
    if (have < 2) {
        *buffer_len = have;
        return 0;
    }

    size_t frame_len = (size_t)buffer[1] + 2;
    if (frame_len > CRSF_MAX_FRAME_SIZE || frame_len < 4) {
        /* drop the sync byte and let the caller try again */
        memmove(buffer, buffer + 1, have - 1);
        *buffer_len = have - 1;
        return 0;
    }
    if (have < frame_len) {
        *buffer_len = have;
        return 0;
    }

    const uint8_t *payload = NULL;
    size_t payload_len = 0;
    uint8_t frame_type = biba_crsf_parse_frame(buffer, frame_len, &payload, &payload_len);
    if (frame_type == 0) {
        /* bad frame -> drop sync byte */
        memmove(buffer, buffer + 1, have - 1);
        *buffer_len = have - 1;
        return 0;
    }

    if (out_frame != NULL && out_cap >= frame_len) {
        memcpy(out_frame, buffer, frame_len);
    }
    if (out_frame_len != NULL) {
        *out_frame_len = frame_len;
    }

    memmove(buffer, buffer + frame_len, have - frame_len);
    *buffer_len = have - frame_len;
    return frame_type;
}

bool biba_crsf_unpack_channels(const uint8_t *payload,
                               size_t payload_len,
                               uint16_t channels[CRSF_RC_CHANNEL_COUNT])
{
    if (payload == NULL || channels == NULL) return false;
    if (payload_len < 22) return false;

    /* 16 channels, 11 bits each, little-endian bit packing. */
    uint32_t accumulator = 0;
    unsigned bits_in_accumulator = 0;
    size_t byte_index = 0;
    for (unsigned ch = 0; ch < CRSF_RC_CHANNEL_COUNT; ++ch) {
        while (bits_in_accumulator < 11) {
            accumulator |= ((uint32_t)payload[byte_index]) << bits_in_accumulator;
            bits_in_accumulator += 8;
            byte_index += 1;
        }
        channels[ch] = (uint16_t)(accumulator & 0x07FFu);
        accumulator >>= 11;
        bits_in_accumulator -= 11;
    }
    return true;
}

bool biba_crsf_parse_link_stats(const uint8_t *payload,
                                size_t payload_len,
                                biba_crsf_link_stats_t *stats)
{
    if (payload == NULL || stats == NULL) return false;
    if (payload_len < 10) return false;
    stats->uplink_rssi_1        = payload[0];
    stats->uplink_rssi_2        = payload[1];
    stats->uplink_link_quality  = payload[2];
    stats->uplink_snr           = (int8_t)payload[3];
    stats->active_antenna       = payload[4];
    stats->rf_mode              = payload[5];
    stats->uplink_tx_power      = payload[6];
    stats->downlink_rssi        = payload[7];
    stats->downlink_link_quality= payload[8];
    stats->downlink_snr         = (int8_t)payload[9];
    return true;
}
