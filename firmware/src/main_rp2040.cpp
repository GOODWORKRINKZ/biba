/* Arduino-framework entry point for RP2040 BiBa firmware.
 *
 * The earlephilhower arduino-pico core defines main() internally and
 * calls setup() once, then loop() forever.  setup() calls the BiBa boot
 * sequence which never returns (biba_mode_dispatcher_run_forever loops
 * indefinitely), so loop() is left empty.
 *
 * printf() / puts() from all C translation units are routed to USB CDC
 * by the strong _write() override in hal/biba_hal_serial.cpp (the
 * framework's own _write() stub discards output unless
 * DEBUG_RP2040_PORT is defined at framework-compile time). */

#include <Arduino.h>
#include <stdio.h>

extern "C" {
#include "modes/mode_dispatcher.h"
}

void setup()
{
    Serial.begin(115200);
    /* SerialUSB::write() silently discards data while tud_cdc_connected()
     * is false (host hasn't asserted DTR).  Ignore flow control so logs
     * flow even before the host fully opens the CDC port (the POC
     * entry points do the same). */
    Serial.ignoreFlowControl(true);
    /* The arduino-pico core's _isatty() returns 0, so newlib treats
     * stdout as a non-TTY and fully buffers printf() output.  Force
     * unbuffered mode so logs reach USB CDC immediately. */
    setvbuf(stdout, NULL, _IONBF, 0);
    delay(150); /* let USB-CDC enumerate on the host before first printf */

    printf("\r\n[biba] RP2040 boot " __DATE__ " " __TIME__
#if defined(BIBA_TARGET_RPICO_RP2040_BLDC)
           " target=BLDC"
#endif
#if defined(BIBA_TARGET_RPICO_RP2040)
           " target=RP2040"
#endif
#if defined(BIBA_MODE_STANDALONE)
           " mode=standalone"
#elif defined(BIBA_MODE_COMPANION)
           " mode=companion"
#elif defined(BIBA_MODE_COMBINED)
           " mode=combined"
#endif
           "\r\n");

    biba_mode_dispatcher_boot();
    biba_mode_dispatcher_run_forever();
}

void loop() {}
