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
}

void setup()
{
    Serial.begin(115200);
    biba_mode_dispatcher_boot();
    biba_mode_dispatcher_run_forever();
}

void loop() {}
