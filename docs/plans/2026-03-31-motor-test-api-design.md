# Motor Test API Design

## Goal

Add a fast manual motor test control surface that lets an operator send a short left/right PWM command to the robot without touching CRSF control flow.

The immediate goal is a simple page with independent left/right frequency and duty sliders plus a duration field, backed by a robot-side HTTP endpoint that applies the requested square waves for a bounded time and then always stops both channels.

## Decision

Implement the feature inside the existing controller process using only the Python standard library.

- serve a small HTML page from the controller
- expose a JSON POST endpoint for motor test commands
- execute the test through the existing split motor PWM path already used by `MotorSynth`
- reject test requests when a previous test is still running

This avoids adding a new package, a second process, or a second transport layer.

## UI Shape

Expose a page at `/motor-test` with these controls:

- left frequency: `100..8000` Hz
- left duty: `0..100` %
- right frequency: `100..8000` Hz
- right duty: `0..100` %
- duration: configurable milliseconds, default `2000`
- send button

The page should be intentionally minimal and functional rather than a full application.

## API Contract

Expose `POST /api/motor-test` accepting JSON:

```json
{
  "left_frequency_hz": 1000,
  "left_duty_percent": 40,
  "right_frequency_hz": 1200,
  "right_duty_percent": 55,
  "duration_ms": 2000
}
```

Validation rules:

- left/right frequency: `100..8000`
- left/right duty: `0..100`
- duration: bounded positive integer, recommended `100..10000`

Response rules:

- `200` when the test is accepted and completed
- `400` for malformed or out-of-range input
- `409` when another motor test is already active
- `503` when motor test hardware is unavailable

## Runtime Integration

The controller currently constructs a `MotorSynth` instance for motor sound playback. That instance already knows the exact left and right forward and complementary pins, and already contains the low-level split-PWM application path.

The fastest and least duplicative approach is:

- add one public `MotorSynth` method for bounded manual split output
- reuse its existing pin grouping and stop behavior
- keep the HTTP layer separate from PWM mechanics

This is preferable to re-implementing pigpio pin selection in a separate module.

## Concurrency Model

Use a dedicated executor object with a lock.

Behavior:

- exactly one test may run at a time
- the HTTP handler blocks until the current test completes
- the executor always calls `off()` in a `finally` block
- a concurrent request gets `409`

The motor test path is intentionally short-lived and human-triggered, so a synchronous request is acceptable and simpler than introducing background job plumbing.

## Safety and Conflict Rules

The design intentionally stays conservative:

- no queued requests
- no indefinite playback
- no silent failure path
- guaranteed stop on exception

For the first version, the endpoint only checks whether the test executor is already active. It does not try to integrate deeply with armed/disarmed controller state, because the HTTP server lives inside the same process and the main loop already has many responsibilities. If needed later, an additional guard can reject requests while armed.

## Module Layout

Add a small dedicated module, for example `biba-controller/motor_test_api.py`, containing:

- request payload parsing and validation
- an executor class that receives a `MotorSynth`
- an HTTP handler factory
- embedded HTML for the small control page

Main runtime changes should stay narrow:

- create the motor test server only when pigpio and buzzer are available
- start it on a background thread
- shut it down in controller cleanup

## Configuration

Add environment variables for:

- enable flag
- bind host
- bind port

Reasonable defaults:

- enabled by default for now, since this is a manual engineering tool
- host `0.0.0.0`
- port `8765`

Compose should publish the port so the page is reachable from the local network.

## Testing Strategy

Add focused unit coverage for:

1. payload validation and range checks
2. concurrent-request rejection
3. duty-percent conversion
4. guaranteed `off()` on normal completion and on exception
5. HTTP page serving and JSON responses

Avoid end-to-end hardware tests in pytest. Hardware verification belongs to deployment validation on the robot.

## Non-Goals

- no persistent UI state
- no authentication layer in this first pass
- no websocket streaming
- no command queue or scheduling
- no extra standalone client application