/* Non-blocking USB-CDC serial line reader — Arduino framework wrapper.
 *
 * Compiled only for RP2040 Arduino-framework targets (not excluded by
 * rp2040_src_filter, and `<Arduino.h>` is unavailable in other envs).
 *
 * Routes serial input from USB CDC (Arduino Serial) into a line buffer;
 * biba_hal_serial_readline() returns true when a complete line is ready.
 * This is the read-side companion to the _write() override below that
 * routes printf() to Serial. */

#include "biba_hal.h"

#include <Arduino.h>
#include <string.h>
#include <sys/types.h>

/* Strong override of the arduino-pico core's weak, no-op _write().
 *
 * The framework compiles cores/rp2040/posix.cpp with a _write() stub
 * that discards everything unless DEBUG_RP2040_PORT is defined when the
 * framework itself is compiled, so C printf() output from the mode/app
 * code never reaches the host.  Defining our own strong _write() here
 * wins at link time and routes stdout/stderr to the USB-CDC Serial.
 * STM32 targets exclude this file and use the semihosting override in
 * hal/biba_hal_debug.c instead. */
extern "C" ssize_t _write(int fd, const void *buf, size_t count)
{
    (void)fd;
    return (ssize_t)Serial.write((const uint8_t *)buf, count);
}

extern "C" bool biba_hal_serial_readline(char *buf, size_t max_len)
{
    static char   s_line[128];
    static size_t s_fill = 0u;

    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\r') continue;   /* strip CR from CRLF line endings */
        if (c == '\n') {
            if (s_fill > 0u) {
                s_line[s_fill] = '\0';
                if (buf && max_len > 0u) {
                    strncpy(buf, s_line, max_len - 1u);
                    buf[max_len - 1u] = '\0';
                }
                s_fill = 0u;
                return true;
            }
            /* else: empty line — discard */
        } else if (s_fill < sizeof(s_line) - 1u) {
            s_line[s_fill++] = c;
        }
        /* else: line too long — drop the byte (buffer stays intact) */
    }
    return false;
}

extern "C" void biba_hal_serial_write_bytes(const uint8_t *buf, size_t len)
{
    Serial.write(buf, len);
}

extern "C" void biba_hal_serial_write_str(const char *s)
{
    Serial.print(s);
}
