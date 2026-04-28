#include "biba_proto.h"

#include <string.h>

/* CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflect, xorout 0. */
uint16_t biba_proto_crc16_ccitt(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFFu;
    if (data == NULL) {
        return crc;
    }
    for (size_t i = 0; i < len; ++i) {
        crc ^= ((uint16_t)data[i]) << 8;
        for (unsigned bit = 0; bit < 8; ++bit) {
            if (crc & 0x8000u) {
                crc = (uint16_t)((crc << 1) ^ 0x1021u);
            } else {
                crc = (uint16_t)(crc << 1);
            }
        }
    }
    return crc;
}

int biba_proto_encode(const biba_proto_frame_t *frame,
                      uint8_t *buffer,
                      size_t buffer_len)
{
    if (frame == NULL || buffer == NULL) {
        return BIBA_PROTO_ERR_ARGS;
    }
    if (buffer_len != BIBA_PROTO_FRAME_SIZE) {
        return BIBA_PROTO_ERR_SIZE;
    }
    if (frame->payload_len > BIBA_PROTO_PAYLOAD_MAX) {
        return BIBA_PROTO_ERR_PAYLOAD_TOO_BIG;
    }

    memset(buffer, 0, BIBA_PROTO_FRAME_SIZE);
    buffer[0] = BIBA_PROTO_SYNC_0;
    buffer[1] = BIBA_PROTO_SYNC_1;
    buffer[2] = frame->version;
    buffer[3] = frame->cmd;
    buffer[4] = frame->seq;
    buffer[5] = frame->flags;
    buffer[6] = frame->payload_len;
    buffer[7] = 0; /* reserved */
    if (frame->payload_len > 0) {
        memcpy(&buffer[BIBA_PROTO_HEADER_SIZE], frame->payload, frame->payload_len);
    }

    uint16_t crc = biba_proto_crc16_ccitt(buffer,
                                          BIBA_PROTO_FRAME_SIZE - BIBA_PROTO_CRC_SIZE);
    buffer[BIBA_PROTO_FRAME_SIZE - 2] = (uint8_t)(crc & 0xFFu);
    buffer[BIBA_PROTO_FRAME_SIZE - 1] = (uint8_t)((crc >> 8) & 0xFFu);
    return BIBA_PROTO_OK;
}

int biba_proto_decode(const uint8_t *buffer,
                      size_t buffer_len,
                      biba_proto_frame_t *frame)
{
    if (buffer == NULL || frame == NULL) {
        return BIBA_PROTO_ERR_ARGS;
    }
    if (buffer_len != BIBA_PROTO_FRAME_SIZE) {
        return BIBA_PROTO_ERR_SIZE;
    }
    if (buffer[0] != BIBA_PROTO_SYNC_0 || buffer[1] != BIBA_PROTO_SYNC_1) {
        return BIBA_PROTO_ERR_SYNC;
    }
    if (buffer[2] != BIBA_PROTO_VERSION) {
        return BIBA_PROTO_ERR_VERSION;
    }
    uint8_t payload_len = buffer[6];
    if (payload_len > BIBA_PROTO_PAYLOAD_MAX) {
        return BIBA_PROTO_ERR_PAYLOAD_TOO_BIG;
    }

    uint16_t expected = biba_proto_crc16_ccitt(buffer,
                                               BIBA_PROTO_FRAME_SIZE - BIBA_PROTO_CRC_SIZE);
    uint16_t found = (uint16_t)buffer[BIBA_PROTO_FRAME_SIZE - 2]
                   | ((uint16_t)buffer[BIBA_PROTO_FRAME_SIZE - 1] << 8);
    if (expected != found) {
        return BIBA_PROTO_ERR_CRC;
    }

    frame->version = buffer[2];
    frame->cmd = buffer[3];
    frame->seq = buffer[4];
    frame->flags = buffer[5];
    frame->payload_len = payload_len;
    memset(frame->payload, 0, sizeof(frame->payload));
    if (payload_len > 0) {
        memcpy(frame->payload, &buffer[BIBA_PROTO_HEADER_SIZE], payload_len);
    }
    return BIBA_PROTO_OK;
}

int biba_proto_encode_telemetry(uint8_t seq,
                                uint8_t flags,
                                const biba_proto_telemetry_t *tlm,
                                uint8_t *buffer,
                                size_t buffer_len)
{
    if (tlm == NULL) {
        return BIBA_PROTO_ERR_ARGS;
    }
    biba_proto_frame_t frame;
    memset(&frame, 0, sizeof(frame));
    frame.version = BIBA_PROTO_VERSION;
    frame.cmd = BIBA_TLM_SNAPSHOT;
    frame.seq = seq;
    frame.flags = flags;
    frame.payload_len = (uint8_t)sizeof(biba_proto_telemetry_t);
    memcpy(frame.payload, tlm, sizeof(biba_proto_telemetry_t));
    return biba_proto_encode(&frame, buffer, buffer_len);
}
