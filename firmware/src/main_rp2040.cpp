/* Arduino-framework entry point for RP2040 BiBa firmware.
 *
 * The earlephilhower arduino-pico core defines main() internally and
 * calls setup() once, then loop() forever.  setup() calls the BiBa boot
 * sequence which never returns (biba_mode_dispatcher_run_forever loops
 * indefinitely), so loop() is left empty.
 *
 * printf() / puts() from all C translation units are routed to USB CDC
 * by the mbed-based arduino-pico framework's own _write() stub in
 * mbed_retarget.cpp — no _write() override is needed here. */

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
