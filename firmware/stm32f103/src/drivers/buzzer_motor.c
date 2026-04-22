#include "buzzer_motor.h"

#include "hal/biba_hal.h"

void biba_buzzer_play_tone(uint16_t freq_hz, uint16_t duration_ms)
{
    /* Placeholder: the full motor-audio synth lives on the Pi side.
     * Here we just pulse the status LED so operators get feedback that
     * the firmware received the command. */
    (void)freq_hz;
    uint32_t deadline = biba_hal_now_ms() + duration_ms;
    while ((int32_t)(biba_hal_now_ms() - deadline) < 0) {
        biba_hal_status_led_set(true);
        biba_hal_delay_ms(30);
        biba_hal_status_led_set(false);
        biba_hal_delay_ms(30);
    }
}
