/* Unity tests for firmware/src/app/blackbox.h struct layout and config.
 *
 * Runs under pio test -e native_test (full Unity runtime).
 * blackbox.cpp is NOT compiled in native_test (it requires LittleFS +
 * Arduino); we only test the header-level definitions here. */

#include <string.h>

#include "blackbox.h"
#include "biba_config.h"
#include "biba_test_support.h"

/* ------------------------------------------------------------------ */

static void test_header_size(void)
{
    TEST_ASSERT_EQUAL_UINT(32u, sizeof(biba_blackbox_header_t));
}

static void test_record_size(void)
{
    TEST_ASSERT_EQUAL_UINT(31u, sizeof(biba_blackbox_record_t));
}

static void test_header_magic(void)
{
    biba_blackbox_header_t hdr;
    memcpy(hdr.magic, "BBD1", 4);
    TEST_ASSERT_EQUAL_INT(0, memcmp(hdr.magic, "BBD1", 4));
}

static void test_rate_hz_fits_byte(void)
{
    TEST_ASSERT_TRUE(BIBA_BLACKBOX_RATE_HZ <= 255);
}

/* ------------------------------------------------------------------ */

static void run_all(void)
{
    RUN_TEST(test_header_size);
    RUN_TEST(test_record_size);
    RUN_TEST(test_header_magic);
    RUN_TEST(test_rate_hz_fits_byte);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
