/* Arduino-framework entry point for RP2040 BiBa firmware.
 *
 * The earlephilhower arduino-pico core defines main() internally and
 * calls setup() once, then loop() forever.  setup() calls the BiBa boot
 * sequence which never returns (biba_mode_dispatcher_run_forever loops
 * indefinitely), so loop() is left empty.
 *
 * Serial.begin() enables USB CDC so that printf() / puts() output from
 * the firmware lands in the host's serial monitor.  The firmware does
 * not block waiting for a USB host; if one is not connected the output
 * is silently discarded.
 */

#include <Arduino.h>

extern "C" {
#include "modes/mode_dispatcher.h"

/* Route printf() / puts() from all C translation units to USB CDC.
 * The arduino-pico newlib stub calls _write() for every printf; we
 * forward it to Serial so that C code needs no changes. */
int _write(int fd, const char *buf, int count)
{
    (void)fd;
    return (int)Serial.write((const uint8_t *)buf, (size_t)count);
}
} /* extern "C" */

void setup()
{
    Serial.begin(115200);

    /* Do not block writes waiting for DTR — output is discarded if no
     * host is connected, but the firmware never stalls. */
    Serial.ignoreFlowControl(true);

    biba_mode_dispatcher_boot();
    biba_mode_dispatcher_run_forever();
}

void loop() {}
