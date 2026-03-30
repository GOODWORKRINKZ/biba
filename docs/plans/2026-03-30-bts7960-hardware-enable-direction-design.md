# BTS7960 Hardware PWM Enable-Direction Design

**Goal:** Make `BTS7960_PWM_MODE=HARDWARE` work with the current robot wiring by using one hardware PWM channel per motor pair and selecting direction through `REN` and `LEN` instead of independent `RPWM` and `LPWM` duties.

## Context

The current robot wiring is:

- `LEFT_MOTOR_RPWM=12`
- `LEFT_MOTOR_LPWM=18`
- `RIGHT_MOTOR_RPWM=19`
- `RIGHT_MOTOR_LPWM=13`

On Raspberry Pi Zero 2W, GPIO `12` and `18` share hardware PWM channel 0, while GPIO `13` and `19` share hardware PWM channel 1. That means the current `BTS7960MotorDriver` hardware path cannot treat `RPWM` and `LPWM` as two independent hardware-PWM outputs for a single motor, because each pair is really one shared channel.

The software PWM path works around this, but it gives up duty resolution and top frequency. The robot was rewired specifically to keep hardware PWM, so the fix should change driver semantics instead of falling back to software by default.

## Proposed Hardware Model

For `BTS7960_PWM_MODE=HARDWARE`, each motor uses:

- one shared hardware PWM duty applied to both `RPWM` and `LPWM`
- direction selected by the enable pins

State table:

| Command | RPWM | LPWM | REN | LEN |
| --- | --- | --- | --- | --- |
| Forward, duty > 0 | PWM | PWM | 1 | 0 |
| Reverse, duty > 0 | PWM | PWM | 0 | 1 |
| Stop / zero | 0 | 0 | 0 | 0 |

This keeps the actual duty source on the hardware PWM channel while giving direction control to `REN` and `LEN`. Both motors can then run simultaneously because the left motor only consumes PWM0 and the right motor only consumes PWM1.

## Behavior Rules

- `SOFTWARE` mode keeps the current implementation unchanged.
- `HARDWARE` mode changes only the BTS7960 low-level pin behavior.
- `set_speed(value)` still accepts `-1.0..1.0`.
- `inverted=True` still flips the sign before direction selection.
- `stop()` in hardware mode disables both enable pins and sets PWM duty to zero on both PWM pins.

## Ramping Interaction

The existing ramp in `SpeedRamp` already enforces the important motion semantics:

- separate acceleration and deceleration rates
- deceleration to zero before sign change
- optional zero hold after reversal

That means the new hardware mode does not need extra reverse-delay logic. The low-level driver only needs to reflect the sign and magnitude it receives. The safe zero transition is already handled one layer up in `DifferentialDrive`.

With current defaults, ordinary release-to-zero and reverse transitions are already soft. Only explicit `stop()` and `emergency_stop()` remain immediate, which is appropriate for initialization and shutdown paths.

## Scope

Files in scope:

- `biba-controller/motors/driver.py`
- `tests/test_motors.py`
- `tests/test_config.py`
- `docker-compose.yml`
- `.env.example`
- `docs/deployment.md`
- `docs/wiring.md`

## Non-Goals

- No change to `MotorSynth` or `wav_player`; they already use `hardware_PWM()` directly.
- No change to the software PWM BTS7960 path.
- No change to ramp coefficients in this task.
- No change to current limiting or telemetry.

## Validation

- Add failing tests that describe the new hardware `REN/LEN` semantics.
- Keep existing software-mode tests passing.
- Restore `HARDWARE` as the documented and configured default for BTS7960.
- Run focused tests for `motors`, `config`, and `main` wiring paths.