#include <stdint.h>
#include <string.h>

#include "crsf.h"
#include "biba_test_support.h"

/* Build a CRSF frame into `out`. Returns total length. */
static size_t make_frame(uint8_t type, const uint8_t *payload, size_t payload_len, uint8_t *out)
{
    out[0] = CRSF_SYNC_BYTE;
    out[1] = (uint8_t)(payload_len + 2);
    out[2] = type;
    memcpy(&out[3], payload, payload_len);
    out[3 + payload_len] = biba_crsf_crc8_dvb_s2(&out[2], 1 + payload_len);
    return payload_len + 4;
}

static void pack_channels(const uint16_t *channels, uint8_t out[22])
{
    /* 16 channels * 11 bits = 176 bits = 22 bytes, little-endian packing. */
    uint32_t accumulator = 0;
    unsigned bits = 0;
    size_t idx = 0;
    memset(out, 0, 22);
    for (unsigned ch = 0; ch < CRSF_RC_CHANNEL_COUNT; ++ch) {
        accumulator |= ((uint32_t)(channels[ch] & 0x7FFu)) << bits;
        bits += 11;
        while (bits >= 8 && idx < 22) {
            out[idx++] = (uint8_t)(accumulator & 0xFFu);
            accumulator >>= 8;
            bits -= 8;
        }
    }
    if (idx < 22 && bits > 0) {
        out[idx] = (uint8_t)(accumulator & 0xFFu);
    }
}

static void test_crc8_known_vector_matches_python(void)
{
    /* Same inputs asserted in tests/test_crsf.py::test_crc8_rejects_known_bad_data */
    uint8_t a = biba_crsf_crc8_dvb_s2((const uint8_t *)"\x16\x01\x02\x03", 4);
    uint8_t b = biba_crsf_crc8_dvb_s2((const uint8_t *)"\x16\x01\x02\x04", 4);
    TEST_ASSERT_TRUE(a != b);
    uint8_t a2 = biba_crsf_crc8_dvb_s2((const uint8_t *)"\x16\x01\x02\x03", 4);
    TEST_ASSERT_EQUAL_UINT8(a, a2);
}

static void test_parse_frame_roundtrip(void)
{
    const uint8_t payload[] = {0x01, 0x02, 0x03, 0x04};
    uint8_t frame[8];
    size_t len = make_frame(CRSF_FRAMETYPE_RC_CHANNELS, payload, sizeof(payload), frame);
    const uint8_t *got_payload = NULL;
    size_t got_len = 0;
    uint8_t type = biba_crsf_parse_frame(frame, len, &got_payload, &got_len);
    TEST_ASSERT_EQUAL_UINT8(CRSF_FRAMETYPE_RC_CHANNELS, type);
    TEST_ASSERT_EQUAL_INT((int)sizeof(payload), (int)got_len);
    TEST_ASSERT_EQUAL_MEMORY(payload, got_payload, got_len);
}

static void test_parse_frame_rejects_crc_mismatch(void)
{
    const uint8_t payload[] = {0x10, 0x20};
    uint8_t frame[8];
    size_t len = make_frame(CRSF_FRAMETYPE_RC_CHANNELS, payload, sizeof(payload), frame);
    frame[len - 1] ^= 0xFF;
    TEST_ASSERT_EQUAL_UINT8(0, biba_crsf_parse_frame(frame, len, NULL, NULL));
}

static void test_unpack_channels_matches_pack(void)
{
    uint16_t expected[CRSF_RC_CHANNEL_COUNT] = {
        172, 300, 600, 900, 992, 1200, 1400, 1600,
        1811, 500, 700, 800, 1000, 1100, 1300, 1500
    };
    uint8_t packed[22];
    pack_channels(expected, packed);
    uint16_t got[CRSF_RC_CHANNEL_COUNT];
    TEST_ASSERT_TRUE(biba_crsf_unpack_channels(packed, sizeof(packed), got));
    for (unsigned i = 0; i < CRSF_RC_CHANNEL_COUNT; ++i) {
        TEST_ASSERT_EQUAL_UINT16(expected[i], got[i]);
    }
}

static void test_unpack_channels_rejects_short_payload(void)
{
    uint8_t packed[21] = {0};
    uint16_t got[CRSF_RC_CHANNEL_COUNT];
    TEST_ASSERT_FALSE(biba_crsf_unpack_channels(packed, sizeof(packed), got));
}

static void test_pop_frame_skips_noise_and_oversized(void)
{
    uint8_t buffer[64];
    uint8_t valid_frame[8];
    const uint8_t payload[] = {0xAA, 0xBB};
    size_t valid_len = make_frame(CRSF_FRAMETYPE_RC_CHANNELS, payload, sizeof(payload), valid_frame);

    size_t offset = 0;
    buffer[offset++] = 0x00;
    buffer[offset++] = 0x01;            /* noise */
    buffer[offset++] = CRSF_SYNC_BYTE;
    buffer[offset++] = CRSF_MAX_FRAME_SIZE; /* oversized length */
    memcpy(&buffer[offset], valid_frame, valid_len);
    offset += valid_len;

    uint8_t out[CRSF_MAX_FRAME_SIZE];
    size_t out_len = 0;
    size_t buflen = offset;

    uint8_t type;
    /* Iterate until we either pop the valid frame or run out. */
    unsigned iterations = 0;
    while (iterations++ < 32) {
        type = biba_crsf_pop_frame(buffer, &buflen, out, sizeof(out), &out_len);
        if (type != 0) break;
        if (buflen == 0) break;
    }
    TEST_ASSERT_EQUAL_UINT8(CRSF_FRAMETYPE_RC_CHANNELS, type);
    TEST_ASSERT_EQUAL_INT((int)valid_len, (int)out_len);
    TEST_ASSERT_EQUAL_MEMORY(valid_frame, out, valid_len);
}

static void test_pop_frame_leaves_trailing_partial_in_buffer(void)
{
    uint8_t buffer[64];
    uint8_t first[8];
    uint8_t second[8];
    const uint8_t payload[] = {0xAA, 0xBB};
    size_t flen = make_frame(CRSF_FRAMETYPE_RC_CHANNELS, payload, sizeof(payload), first);
    (void)make_frame(CRSF_FRAMETYPE_LINK_STATS, payload, sizeof(payload), second);
    memcpy(buffer, first, flen);
    /* Include only 3 bytes of the second frame so it is incomplete. */
    memcpy(buffer + flen, second, 3);
    size_t buflen = flen + 3;

    uint8_t out[CRSF_MAX_FRAME_SIZE];
    size_t out_len = 0;
    uint8_t type = biba_crsf_pop_frame(buffer, &buflen, out, sizeof(out), &out_len);
    TEST_ASSERT_EQUAL_UINT8(CRSF_FRAMETYPE_RC_CHANNELS, type);
    /* Partial second frame must stay in the buffer. */
    TEST_ASSERT_EQUAL_INT(3, (int)buflen);
    TEST_ASSERT_EQUAL_UINT8(CRSF_SYNC_BYTE, buffer[0]);
}

static void test_parse_link_stats_reads_all_fields(void)
{
    uint8_t payload[10] = {120, 130, 95, (uint8_t)(int8_t)-8, 1, 2, 3, 100, 80, (uint8_t)(int8_t)-4};
    biba_crsf_link_stats_t stats;
    memset(&stats, 0, sizeof(stats));
    TEST_ASSERT_TRUE(biba_crsf_parse_link_stats(payload, sizeof(payload), &stats));
    TEST_ASSERT_EQUAL_UINT8(120, stats.uplink_rssi_1);
    TEST_ASSERT_EQUAL_UINT8(95, stats.uplink_link_quality);
    TEST_ASSERT_EQUAL_INT(-8, stats.uplink_snr);
    TEST_ASSERT_EQUAL_INT(-4, stats.downlink_snr);
}

static void run_all(void)
{
    RUN_TEST(test_crc8_known_vector_matches_python);
    RUN_TEST(test_parse_frame_roundtrip);
    RUN_TEST(test_parse_frame_rejects_crc_mismatch);
    RUN_TEST(test_unpack_channels_matches_pack);
    RUN_TEST(test_unpack_channels_rejects_short_payload);
    RUN_TEST(test_pop_frame_skips_noise_and_oversized);
    RUN_TEST(test_pop_frame_leaves_trailing_partial_in_buffer);
    RUN_TEST(test_parse_link_stats_reads_all_fields);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
