/* Non-blocking two-voice motor melody player.
 *
 * Note frequencies are standard equal temperament (A4 = 440 Hz).
 * Melodies are ported from biba-controller/buzzer/melodies.py using the
 * same BLHeli note notation; tempo and note durations are identical.
 *
 * Audio quality note (RP2040 vs Python):
 *   Python pigpio uses software PWM and drives RPWM / LPWM of the same
 *   motor at slightly different frequencies to create a "beat" tone.
 *   Here we use hardware PWM with channel-B inversion (push-pull):
 *   RPWM and LPWM are driven as true complements at the note frequency,
 *   producing maximum current swing through the motor coil and louder,
 *   cleaner sound without the beat-frequency compromise.
 */

#include "melody.h"
#include "hal/biba_hal.h"

/* ---- Melody catalog --------------------------------------------------- */

/*
 * Note frequency table (Hz), equal temperament:
 *   D4=294  D#4=311  E4=330  F4=349  F#4=370
 *   G4=392  G#4=415  A4=440  A#4=466  B4=494
 *   C5=523  D5=587   E5=659  F5=698  G5=784
 */

/* startup — "F4 A4 G4 F4" / "D#4 F4 D#4 G4"  @152 BPM
 * quarter=395 ms  1/16≈99 ms  1/8≈197 ms */
static const biba_note_t s_startup_l[] = {
    {349,  99}, {440,  99}, {392, 197}, {349, 197},
};
static const biba_note_t s_startup_r[] = {
    {311,  99}, {349,  99}, {311, 197}, {392, 197},
};
const biba_melody_t biba_melody_startup = {
    s_startup_l, s_startup_r,
    sizeof(s_startup_l) / sizeof(s_startup_l[0]),
};

/* arm — "G4 D#4" / "F4 A4"  @176 BPM
 * quarter=341 ms  1/16≈85 ms  1/8≈170 ms */
static const biba_note_t s_arm_l[] = {
    {392, 85}, {311, 170},
};
static const biba_note_t s_arm_r[] = {
    {349, 85}, {440, 170},
};
const biba_melody_t biba_melody_arm = {
    s_arm_l, s_arm_r,
    sizeof(s_arm_l) / sizeof(s_arm_l[0]),
};

/* disarm — "A4 F4" / "G#4 D4"  @176 BPM */
static const biba_note_t s_disarm_l[] = {
    {440, 85}, {349, 170},
};
static const biba_note_t s_disarm_r[] = {
    {415, 85}, {294, 170},
};
const biba_melody_t biba_melody_disarm = {
    s_disarm_l, s_disarm_r,
    sizeof(s_disarm_l) / sizeof(s_disarm_l[0]),
};

/* failsafe — "D4 F4 D4" / "F4 D#4 D4"  @124 BPM
 * quarter=484 ms  1/8≈242 ms  1/4≈484 ms */
static const biba_note_t s_failsafe_l[] = {
    {294, 242}, {349, 242}, {294, 484},
};
static const biba_note_t s_failsafe_r[] = {
    {349, 242}, {311, 242}, {294, 484},
};
const biba_melody_t biba_melody_failsafe = {
    s_failsafe_l, s_failsafe_r,
    sizeof(s_failsafe_l) / sizeof(s_failsafe_l[0]),
};

/* sos — "A4 F4 A4 P D#4 P A4" / "F4 D#4 F4 P G4 P F4"  @132 BPM
 * quarter=455 ms  1/16=114 ms  1/8=227 ms */
static const biba_note_t s_sos_l[] = {
    {440, 114}, {349, 114}, {440, 114}, {0, 114}, {311, 227}, {0, 114}, {440, 114},
};
static const biba_note_t s_sos_r[] = {
    {349, 114}, {311, 114}, {349, 114}, {0, 114}, {392, 227}, {0, 114}, {349, 114},
};
const biba_melody_t biba_melody_sos = {
    s_sos_l, s_sos_r,
    sizeof(s_sos_l) / sizeof(s_sos_l[0]),
};

/* trim_enter — ascending "F4 G4 A4" / "D#4 F4 G4"  @172 BPM
 * quarter≈349 ms  1/16≈87 ms  1/8≈175 ms */
static const biba_note_t s_trim_enter_l[] = { {349, 87}, {392, 87}, {440, 175} };
static const biba_note_t s_trim_enter_r[] = { {311, 87}, {349, 87}, {392, 175} };
const biba_melody_t biba_melody_trim_enter = {
    s_trim_enter_l, s_trim_enter_r,
    sizeof(s_trim_enter_l) / sizeof(s_trim_enter_l[0]),
};

/* trim_exit — descending "A4 G4 F4" / "G4 F4 D#4"  @168 BPM
 * quarter≈357 ms  1/16≈89 ms  1/8≈179 ms */
static const biba_note_t s_trim_exit_l[] = { {440, 89}, {392, 89}, {349, 179} };
static const biba_note_t s_trim_exit_r[] = { {392, 89}, {349, 89}, {311, 179} };
const biba_melody_t biba_melody_trim_exit = {
    s_trim_exit_l, s_trim_exit_r,
    sizeof(s_trim_exit_l) / sizeof(s_trim_exit_l[0]),
};

/* backup_pip — single A5 beep (880 Hz, 100 ms) played periodically while reversing */
static const biba_note_t s_pip_l[] = { {880, 100} };
static const biba_note_t s_pip_r[] = { {880, 100} };
const biba_melody_t biba_melody_backup_pip = {
    s_pip_l, s_pip_r, 1,
};

/* ---- Player ----------------------------------------------------------- */

void biba_melody_player_start(biba_melody_player_t *p, const biba_melody_t *m)
{
    biba_melody_player_stop(p);
    p->melody      = m;
    p->pos         = 0;
    p->note_end_ms = 0;  /* triggers first note on the very next tick */
    p->active      = true;
    biba_hal_motor_audio_begin();
}

void biba_melody_player_stop(biba_melody_player_t *p)
{
    if (p->active) {
        biba_hal_motor_audio_end();
        p->active = false;
    }
}

bool biba_melody_player_tick(biba_melody_player_t *p, uint32_t now_ms)
{
    if (!p->active) return false;

    /* Still waiting for the current note to finish. */
    if (now_ms < p->note_end_ms) return true;

    /* Melody finished. */
    if (p->pos >= p->melody->count) {
        biba_hal_motor_audio_end();
        p->active = false;
        return false;
    }

    /* Emit next note. */
    biba_note_t ln = p->melody->left [p->pos];
    biba_note_t rn = p->melody->right[p->pos];
    p->pos++;

    uint32_t freq[4] = { ln.freq_hz, 0u, rn.freq_hz, 0u };
    float    duty[4] = { 0.5f,       0.0f, 0.5f,     0.0f };
    biba_hal_motor_audio_set_all(freq, duty);

    uint16_t dur = (ln.dur_ms > rn.dur_ms) ? ln.dur_ms : rn.dur_ms;
    p->note_end_ms = now_ms + (uint32_t)dur;
    return true;
}
