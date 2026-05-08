#ifndef BIBA_MELODY_H
#define BIBA_MELODY_H

/* Non-blocking two-voice motor melody player.
 *
 * Motors are used as speakers via the push-pull audio HAL
 * (biba_hal_motor_audio_begin/set_all/end).  Left and right motors
 * play independent harmonic voices simultaneously, mirroring the
 * play_split_blheli() approach from biba-controller/buzzer/motor_synth.py.
 *
 * Usage:
 *   static biba_melody_player_t player;
 *   biba_melody_player_start(&player, &biba_melody_arm);
 *
 *   // In the main tick (call every loop iteration):
 *   biba_melody_player_tick(&player, biba_hal_now_ms());
 *
 *   // If motors needed (control input active):
 *   biba_melody_player_stop(&player);  // restores traction PWM
 */

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- Types ------------------------------------------------------------ */

/* Single note for one voice.  freq_hz = 0 → rest (silence). */
typedef struct {
    uint16_t freq_hz;
    uint16_t dur_ms;
} biba_note_t;

/* Two-voice melody: left and right motor play separate harmonies.
 * Both arrays must have `count` elements. */
typedef struct {
    const biba_note_t *left;
    const biba_note_t *right;
    size_t             count;
} biba_melody_t;

/* Player state — embed as a static in the owning mode. */
typedef struct {
    const biba_melody_t *melody;
    size_t               pos;
    uint32_t             note_end_ms;
    bool                 active;
} biba_melody_player_t;

/* ---- Melody catalog --------------------------------------------------- */

/* Boot fanfare (152 BPM, 4 notes, ~0.6 s) */
extern const biba_melody_t biba_melody_startup;

/* Arm / disarm tones (176 BPM, 2 notes, ~0.25 s each) */
extern const biba_melody_t biba_melody_arm;
extern const biba_melody_t biba_melody_disarm;

/* Failsafe warning (124 BPM, 3 notes, ~1 s) */
extern const biba_melody_t biba_melody_failsafe;

/* SOS beacon (132 BPM, 7 notes, ~1.1 s — loop while beacon channel active) */
extern const biba_melody_t biba_melody_sos;

/* ---- Player API ------------------------------------------------------- */

/* Start playing a melody from the beginning.
 * Stops any currently active melody first.
 * Calls biba_hal_motor_audio_begin() automatically. */
void biba_melody_player_start(biba_melody_player_t *p, const biba_melody_t *m);

/* Immediately stop playback and restore traction PWM.
 * Safe to call when the player is already idle. */
void biba_melody_player_stop(biba_melody_player_t *p);

/* Advance the state machine.  Call every loop tick.
 * Returns true while a melody is still playing. */
bool biba_melody_player_tick(biba_melody_player_t *p, uint32_t now_ms);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_MELODY_H */
