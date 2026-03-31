# Disarm Synth Audibility Redesign Design

## Goal

Make the synth `disarm` event clearly audible on the BTS7960 software-PWM setup while keeping it playful and making it read as a descending answer to the existing `arm` phrase.

## Problem

`arm` is currently easy to hear, but `disarm` is weak on real hardware.

The playback path is not the issue:

- `arm` and `disarm` use the same synth routing and async trigger path
- the current percentage detune is already active globally
- the main difference is the melody itself

The current `disarm` phrase starts with a short high note and then descends into a weaker phrase. On the BTS7960 software-PWM setup, that opening does not carry enough perceptual weight.

## Constraints

- Do not change synth routing or detune logic for this task.
- Do not change `arm` or unrelated system events.
- Keep voice and spectral modes untouched.
- Preserve the BiBa synth identity introduced in the redesign.
- Favor low-to-mid notes and short, dense phrases that survive software-PWM quantization better.

## Chosen Approach

Treat `disarm` as a mirrored command response to `arm`.

- `arm` stays as the short rising confirmation.
- `disarm` becomes a short descending confirmation with similar energy and similar total duration.
- The phrase should be fun and readable, not a long fade-out.

This keeps the command pair coherent while borrowing the acoustic strength of the already successful `arm` shape.

## Melody Direction

### Mono BLHeli

Replace the current `disarm` phrase with a tighter descending gesture in the software-PWM-friendly band.

Target qualities:

- similar density to `arm`
- descending contour
- no reliance on a lone high transient
- readable as an immediate answer to `arm`

### Split BLHeli

Keep left and right phrases distinct, but make both sides feel like coordinated halves of the same descending reply.

Target qualities:

- similar total energy to `arm`
- left and right remain intentionally different
- both sides stay in the friendly mid-band

## Testing Strategy

- Update catalog expectations first.
- Keep all system synth entries parseable.
- Keep `disarm` within the software-PWM-friendly band already enforced by tests.
- Run focused buzzer and motor synth regressions after the melody change.

## Non-Goals

- No change to detune ratio or floor.
- No change to startup, arm, failsafe, or other event melodies.
- No change to WAV or spectral playback.