#include <stdint.h>
#include <string.h>

#include "biba_proto.h"
#include "biba_test_support.h"

static void test_crc16_ccitt_known_vector_123456789(void)
{
    /* Classic CRC-16/CCITT-FALSE vector for the ASCII string "123456789". */
    const uint8_t data[] = "123456789";
    uint16_t crc = biba_proto_crc16_ccitt(data, 9);
    TEST_ASSERT_EQUAL_HEX16(0x29B1, crc);
}

static void test_crc16_empty_input_returns_init(void)
{
    TEST_ASSERT_EQUAL_HEX16(0xFFFF, biba_proto_crc16_ccitt(NULL, 0));
    TEST_ASSERT_EQUAL_HEX16(0xFFFF, biba_proto_crc16_ccitt((const uint8_t *)"", 0));
}

static void test_encode_then_decode_round_trips(void)
{
    biba_proto_frame_t in;
    memset(&in, 0, sizeof(in));
    in.version = BIBA_PROTO_VERSION;
    in.cmd = BIBA_CMD_SET_SETPOINT;
    in.seq = 42;
    in.flags = BIBA_PROTO_FLAG_ARMED;
    in.payload_len = 6;
    for (uint8_t i = 0; i < in.payload_len; ++i) {
        in.payload[i] = (uint8_t)(0x10 + i);
    }

    uint8_t buffer[BIBA_PROTO_FRAME_SIZE];
    TEST_ASSERT_EQUAL_INT(BIBA_PROTO_OK,
                          biba_proto_encode(&in, buffer, sizeof(buffer)));

    /* Sanity: frame carries fixed header/sync. */
    TEST_ASSERT_EQUAL_UINT8(BIBA_PROTO_SYNC_0, buffer[0]);
    TEST_ASSERT_EQUAL_UINT8(BIBA_PROTO_SYNC_1, buffer[1]);
    TEST_ASSERT_EQUAL_UINT8(BIBA_PROTO_VERSION, buffer[2]);
    TEST_ASSERT_EQUAL_UINT8(BIBA_CMD_SET_SETPOINT, buffer[3]);
    TEST_ASSERT_EQUAL_UINT8(42, buffer[4]);

    biba_proto_frame_t out;
    TEST_ASSERT_EQUAL_INT(BIBA_PROTO_OK,
                          biba_proto_decode(buffer, sizeof(buffer), &out));
    TEST_ASSERT_EQUAL_UINT8(in.version, out.version);
    TEST_ASSERT_EQUAL_UINT8(in.cmd, out.cmd);
    TEST_ASSERT_EQUAL_UINT8(in.seq, out.seq);
    TEST_ASSERT_EQUAL_UINT8(in.flags, out.flags);
    TEST_ASSERT_EQUAL_UINT8(in.payload_len, out.payload_len);
    TEST_ASSERT_EQUAL_MEMORY(in.payload, out.payload, in.payload_len);
}

static void test_decode_rejects_wrong_sync(void)
{
    biba_proto_frame_t in;
    memset(&in, 0, sizeof(in));
    in.version = BIBA_PROTO_VERSION;
    in.cmd = BIBA_CMD_PING;
    uint8_t buffer[BIBA_PROTO_FRAME_SIZE];
    TEST_ASSERT_EQUAL_INT(BIBA_PROTO_OK,
                          biba_proto_encode(&in, buffer, sizeof(buffer)));
    buffer[0] ^= 0x01;

    biba_proto_frame_t out;
    TEST_ASSERT_EQUAL_INT(BIBA_PROTO_ERR_SYNC,
                          biba_proto_decode(buffer, sizeof(buffer), &out));
}

static void test_decode_rejects_wrong_version(void)
{
    biba_proto_frame_t in;
    memset(&in, 0, sizeof(in));
    in.version = BIBA_PROTO_VERSION;
    in.cmd = BIBA_CMD_PING;
    uint8_t buffer[BIBA_PROTO_FRAME_SIZE];
    biba_proto_encode(&in, buffer, sizeof(buffer));
    buffer[2] = 0xEE;
    /* Recompute CRC so only the version mismatch triggers the error. */
    uint16_t crc = biba_proto_crc16_ccitt(buffer,
                                          BIBA_PROTO_FRAME_SIZE - BIBA_PROTO_CRC_SIZE);
    buffer[BIBA_PROTO_FRAME_SIZE - 2] = (uint8_t)(crc & 0xFF);
    buffer[BIBA_PROTO_FRAME_SIZE - 1] = (uint8_t)((crc >> 8) & 0xFF);

    biba_proto_frame_t out;
    TEST_ASSERT_EQUAL_INT(BIBA_PROTO_ERR_VERSION,
                          biba_proto_decode(buffer, sizeof(buffer), &out));
}

static void test_decode_rejects_crc_flip(void)
{
    biba_proto_frame_t in;
    memset(&in, 0, sizeof(in));
    in.version = BIBA_PROTO_VERSION;
    in.cmd = BIBA_CMD_PING;
    uint8_t buffer[BIBA_PROTO_FRAME_SIZE];
    biba_proto_encode(&in, buffer, sizeof(buffer));
    buffer[BIBA_PROTO_FRAME_SIZE - 1] ^= 0xAA;

    biba_proto_frame_t out;
    TEST_ASSERT_EQUAL_INT(BIBA_PROTO_ERR_CRC,
                          biba_proto_decode(buffer, sizeof(buffer), &out));
}

static void test_encode_rejects_oversized_payload(void)
{
    biba_proto_frame_t in;
    memset(&in, 0, sizeof(in));
    in.version = BIBA_PROTO_VERSION;
    in.payload_len = BIBA_PROTO_PAYLOAD_MAX + 1;
    uint8_t buffer[BIBA_PROTO_FRAME_SIZE];
    TEST_ASSERT_EQUAL_INT(BIBA_PROTO_ERR_PAYLOAD_TOO_BIG,
                          biba_proto_encode(&in, buffer, sizeof(buffer)));
}

static void test_encode_rejects_wrong_buffer_size(void)
{
    biba_proto_frame_t in;
    memset(&in, 0, sizeof(in));
    in.version = BIBA_PROTO_VERSION;
    uint8_t buffer[BIBA_PROTO_FRAME_SIZE + 4];
    TEST_ASSERT_EQUAL_INT(BIBA_PROTO_ERR_SIZE,
                          biba_proto_encode(&in, buffer, sizeof(buffer)));
}

static void test_encode_telemetry_roundtrip(void)
{
    biba_proto_telemetry_t tlm;
    memset(&tlm, 0, sizeof(tlm));
    tlm.setpoint_left_q15 = -12000;
    tlm.setpoint_right_q15 = 9000;
    tlm.current_left_ma = 3200;
    tlm.current_right_ma = -450;
    tlm.vbat_mv = 24800;
    tlm.rail_12v_mv = 11950;
    tlm.gyro_z_cdps = -4500;
    tlm.crsf_rssi = 185;
    tlm.crsf_link_quality = 99;
    tlm.crsf_snr_db = 12;
    tlm.error_flags = BIBA_PROTO_FLAG_CRSF_ALIVE | BIBA_PROTO_FLAG_ARMED;
    tlm.uptime_ms = 1234567;

    uint8_t buffer[BIBA_PROTO_FRAME_SIZE];
    TEST_ASSERT_EQUAL_INT(BIBA_PROTO_OK,
                          biba_proto_encode_telemetry(7, BIBA_PROTO_FLAG_ARMED, &tlm,
                                                      buffer, sizeof(buffer)));

    biba_proto_frame_t decoded;
    TEST_ASSERT_EQUAL_INT(BIBA_PROTO_OK,
                          biba_proto_decode(buffer, sizeof(buffer), &decoded));
    TEST_ASSERT_EQUAL_UINT8(BIBA_TLM_SNAPSHOT, decoded.cmd);
    TEST_ASSERT_EQUAL_UINT8(7, decoded.seq);
    TEST_ASSERT_EQUAL_UINT8(sizeof(biba_proto_telemetry_t), decoded.payload_len);

    biba_proto_telemetry_t out;
    memcpy(&out, decoded.payload, sizeof(out));
    TEST_ASSERT_EQUAL_INT(tlm.setpoint_left_q15, out.setpoint_left_q15);
    TEST_ASSERT_EQUAL_INT(tlm.current_right_ma, out.current_right_ma);
    TEST_ASSERT_EQUAL_UINT16(tlm.vbat_mv, out.vbat_mv);
    TEST_ASSERT_EQUAL_UINT8(tlm.crsf_link_quality, out.crsf_link_quality);
    TEST_ASSERT_EQUAL_INT(tlm.uptime_ms, out.uptime_ms);
}

static void run_all(void)
{
    RUN_TEST(test_crc16_ccitt_known_vector_123456789);
    RUN_TEST(test_crc16_empty_input_returns_init);
    RUN_TEST(test_encode_then_decode_round_trips);
    RUN_TEST(test_decode_rejects_wrong_sync);
    RUN_TEST(test_decode_rejects_wrong_version);
    RUN_TEST(test_decode_rejects_crc_flip);
    RUN_TEST(test_encode_rejects_oversized_payload);
    RUN_TEST(test_encode_rejects_wrong_buffer_size);
    RUN_TEST(test_encode_telemetry_roundtrip);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
