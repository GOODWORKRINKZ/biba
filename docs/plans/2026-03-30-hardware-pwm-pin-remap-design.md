# Hardware PWM Pin Remap Design

**Goal:** Align BiBa's default BTS7960 pin mapping with the robot's new physical wiring so both motors can use non-conflicting Raspberry Pi hardware PWM channels.

## Context

The previous default mapping used left motor pins `18/13` and right motor pins `12/19`. On Raspberry Pi Zero 2W, GPIO `12` and `18` share one hardware PWM channel, while GPIO `13` and `19` share the other. That made simultaneous dual-motor hardware PWM impossible with the old two-motor layout.

The robot wiring has now been physically remapped to:

- `LEFT_MOTOR_RPWM=12`
- `LEFT_MOTOR_LPWM=18`
- `RIGHT_MOTOR_RPWM=19`
- `RIGHT_MOTOR_LPWM=13`

This layout gives each motor one pin on each hardware PWM channel, so the existing `BTS7960_PWM_MODE=HARDWARE` path remains valid without changing driver logic.

## Scope

Update only configuration defaults, deployment defaults, and documentation that describe the motor PWM pins.

Files in scope:

- `biba-controller/config.py`
- `docker-compose.yml`
- `.env.example`
- tests that assert default pin mappings or build motor-synth pin groups
- `docs/wiring.md`

## Non-Goals

- No changes to BTS7960 driver behavior.
- No changes to current limiting, ramping, or buzzer synthesis logic.
- No deployment to the robot in this task.

## Validation

- Update tests first so the old defaults fail.
- Change runtime defaults to the new pin layout.
- Run focused pytest coverage for config, main wiring/grouping, and related motor/voice entry points.
