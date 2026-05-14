/* Minimal Unity-like assertion shim used by native host tests.
 *
 * PlatformIO's native env links against Unity, so when the tests are run
 * via `pio test -e native_test` this header simply forwards to the real
 * Unity macros. In the repository sandbox we also want to compile the
 * tests with plain gcc (no PlatformIO available) so that the portable
 * modules can be verified during normal development. To support that,
 * define BIBA_TEST_STANDALONE when building with gcc to get a tiny
 * self-contained implementation. */

#ifndef BIBA_TEST_SUPPORT_H
#define BIBA_TEST_SUPPORT_H

#if defined(BIBA_TEST_STANDALONE)

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

extern int biba_test_failures;
extern int biba_test_cases;
extern const char *biba_test_current_name;

#define UNITY_BEGIN() do { biba_test_failures = 0; biba_test_cases = 0; } while (0)

#define UNITY_END() (biba_test_failures)

#define RUN_TEST(fn) do { \
    biba_test_current_name = #fn; \
    int prev_failures = biba_test_failures; \
    biba_test_cases += 1; \
    fn(); \
    if (biba_test_failures != prev_failures) { \
        fprintf(stderr, "FAIL %s\n", #fn); \
    } else { \
        fprintf(stdout, "ok   %s\n", #fn); \
    } \
} while (0)

#define BIBA_FAIL(...) do { \
    biba_test_failures += 1; \
    fprintf(stderr, "  in %s: ", biba_test_current_name ? biba_test_current_name : "?"); \
    fprintf(stderr, __VA_ARGS__); \
    fprintf(stderr, "\n"); \
} while (0)

#define TEST_ASSERT_TRUE(cond) do { if (!(cond)) BIBA_FAIL("expected %s to be true", #cond); } while (0)
#define TEST_ASSERT_FALSE(cond) do { if ((cond)) BIBA_FAIL("expected %s to be false", #cond); } while (0)
#define TEST_ASSERT_EQUAL_INT(expected, actual) do { \
    long long _e = (long long)(expected); long long _a = (long long)(actual); \
    if (_e != _a) BIBA_FAIL("expected %lld got %lld (%s vs %s)", _e, _a, #expected, #actual); \
} while (0)
#define TEST_ASSERT_EQUAL_UINT(expected, actual) TEST_ASSERT_EQUAL_INT(expected, actual)
#define TEST_ASSERT_EQUAL_UINT8(expected, actual) TEST_ASSERT_EQUAL_INT(expected, actual)
#define TEST_ASSERT_EQUAL_UINT16(expected, actual) TEST_ASSERT_EQUAL_INT(expected, actual)
#define TEST_ASSERT_EQUAL_HEX16(expected, actual) do { \
    unsigned long _e = (unsigned long)(expected) & 0xFFFFu; \
    unsigned long _a = (unsigned long)(actual) & 0xFFFFu; \
    if (_e != _a) BIBA_FAIL("expected 0x%04lx got 0x%04lx", _e, _a); \
} while (0)
#define TEST_ASSERT_EQUAL_size_t(expected, actual) TEST_ASSERT_EQUAL_INT(expected, actual)
#define TEST_ASSERT_EQUAL_MEMORY(expected, actual, len) do { \
    if (memcmp((expected), (actual), (len)) != 0) \
        BIBA_FAIL("memory mismatch over %zu bytes", (size_t)(len)); \
} while (0)
#define TEST_ASSERT_FLOAT_WITHIN(delta, expected, actual) do { \
    double _e = (double)(expected); double _a = (double)(actual); double _d = (double)(delta); \
    double _diff = _a - _e; if (_diff < 0) _diff = -_diff; \
    if (_diff > _d) BIBA_FAIL("expected %g within %g, got %g", _e, _d, _a); \
} while (0)
#define TEST_ASSERT_EQUAL_FLOAT(expected, actual) TEST_ASSERT_FLOAT_WITHIN(1e-6, expected, actual)

#define BIBA_TEST_STANDALONE_MAIN(runner) \
    int biba_test_failures = 0; \
    int biba_test_cases = 0; \
    const char *biba_test_current_name = NULL; \
    int main(void) { \
        UNITY_BEGIN(); \
        runner(); \
        int failed = UNITY_END(); \
        fprintf(stdout, "ran %d tests, %d failed\n", biba_test_cases, failed); \
        return failed == 0 ? 0 : 1; \
    }

#ifdef __cplusplus
}
#endif

#else /* BIBA_TEST_STANDALONE */

#include <unity.h>

#endif /* BIBA_TEST_STANDALONE */

#endif /* BIBA_TEST_SUPPORT_H */
