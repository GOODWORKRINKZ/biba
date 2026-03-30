# Trim Mode Sounds Design

## Goal

Add two distinct short two-channel motor-synth sounds for motor trim mode transitions:

- entering trim mode after the confirmation hold gesture while disarmed
- saving trim and exiting trim mode after the same hold gesture while disarmed

The sounds must be clearly distinguishable from `arm`, `disarm`, `connected`, and `disconnected` cues, and they must play even when mute is active so trim workflow feedback is still available.

## Constraints

- Reuse the existing motor-synth named-melody path instead of adding a new audio subsystem.
- Keep both sounds short so they do not block trim workflow or driving tests immediately after entering trim mode.
- Preserve the current trim gesture behavior, trim persistence, and telemetry `t` badge behavior.
- Avoid voice playback; the request is specifically for two-channel synthesized sounds.

## Sound Design

### Enter Trim Mode

- Character: opening/service-mode scan
- Duration target: about 0.8 seconds
- Shape: ascending two-channel motif with slight left/right offset so it sounds wider than a mono chirp
- Meaning: trim mode is now active and live CH9 trim is being applied

### Exit Trim Mode

- Character: save/confirm close
- Duration target: about 0.6 seconds
- Shape: compact two-channel confirmation figure with a stable ending
- Meaning: trim value was persisted and trim mode is now inactive

## Implementation Approach

1. Add named BLHeli melodies for `trim_enter` and `trim_exit` to the melody catalog.
2. Reuse `buzzer.play_named_async(...)` through the existing `_play_named_async_if_allowed(...)` helper.
3. Trigger `trim_enter` immediately after trim mode transitions from inactive to active.
4. Trigger `trim_exit` immediately after the trim value is saved and trim mode transitions back to inactive.
5. Pass `allow_when_muted=True` for both transitions.

## Testing Strategy

- Add focused unit tests in `tests/test_main.py` that verify:
  - entering trim mode triggers `trim_enter`
  - saving and exiting trim mode triggers `trim_exit`
  - both sounds are requested through the existing named-sound helper path
- Add focused tests in `tests/test_motor_synth.py` or existing melody-surface tests to verify the new named melodies are present in the catalog.
- Run the focused test slice first, then a broader regression slice covering controller and buzzer behavior.

## Risks And Mitigations

- Risk: sounds collide semantically with existing arm/disarm cues.
  - Mitigation: use a wider two-channel contour and different rhythm from current short arm/disarm ramps.
- Risk: mute suppresses trim feedback.
  - Mitigation: explicitly allow the sound when muted.
- Risk: long sounds interfere with control resumption.
  - Mitigation: keep both cues under 1 second.