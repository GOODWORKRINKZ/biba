#ifndef BIBA_BUZZER_MOTOR_H
#define BIBA_BUZZER_MOTOR_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Inject a short tone of `freq_hz` for `duration_ms`. Implemented by
 * briefly modulating motor PWM or driving the auxiliary buzzer pin. */
void biba_buzzer_play_tone(uint16_t freq_hz, uint16_t duration_ms);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_BUZZER_MOTOR_H */
