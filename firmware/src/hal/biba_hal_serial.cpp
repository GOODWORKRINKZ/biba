/* Non-blocking USB-CDC serial line reader — Arduino framework wrapper.
 *
 * Compiled only for RP2040 Arduino-framework targets (not excluded by
 * rp2040_src_filter, and `<Arduino.h>` is unavailable in other envs).
 *
 * Routes serial input from USB CDC (Arduino Serial) into a line buffer;
 * biba_hal_serial_readline() returns true when a complete line is ready.
 * This is the read-side companion to the _write() redirect in
 * main_rp2040.cpp that routes printf() to Serial. */

#include "biba_hal.h"

#include <Arduino.h>
#include <string.h>

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
