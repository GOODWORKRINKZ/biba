# PID Tuning Page Design

## Goal

Add a lightweight field-tuning page that lets an operator inspect, change, apply, and persist stabilized-drive tuning values without editing files or redeploying for every iteration.

The immediate goal is a simple phone-friendly page exposed by the existing controller tools server, with live apply only while the robot is disarmed and persistent storage in `/data` so tuned values survive restarts.

## Decision

Implement the feature inside the existing controller process and extend the current tools server instead of adding a new service.

- keep the existing `/motor-test` page and add `/pid-tuning`
- expose JSON endpoints for reading current tuning and submitting updates
- persist tuned values to `/data/pid-tuning.json`
- apply updates only from the main loop while the robot is disarmed
- rebuild the assisted-drive controller from a validated tuning snapshot

This avoids a second port, avoids a new frontend stack, and keeps controller ownership of runtime state in one place.

## Exposed Parameters

Version 1 should expose the field-tuning set that actually matters during robot tuning:

- `DRIVE_MODE_YAW_RATE_KP`
- `DRIVE_MODE_YAW_RATE_KI`
- `DRIVE_MODE_YAW_RATE_KD`
- `DRIVE_MODE_YAW_RATE_DEADBAND_DPS`
- `DRIVE_MODE_YAW_RATE_FILTER_HZ`
- `stabilization_min_throttle`
- `neutral_stabilization_steering_limit`
- `neutral_stabilization_max_throttle`

These cover both the core yaw-rate loop and the low-speed stabilization behavior that currently causes most field tuning churn.

## UI Shape

Expose a page at `/pid-tuning` with:

- one section for PID gains (`Kp`, `Ki`, `Kd`)
- one section for yaw-rate filtering and deadband
- one section for low-speed stabilization limits
- current values loaded from the running controller snapshot
- a visible `armed` or `disarmed` status badge
- an `Apply` action that saves and requests a live update
- a `Reset to defaults` action that restores env-backed defaults
- clear success/error feedback after each request

The page should stay intentionally simple, with inline HTML/CSS/JS like the existing motor-test page rather than a separate web app.

## API Contract

Expose:

- `GET /api/pid-tuning` → current values, defaults, armed/disarmed status, apply status, last error if any
- `POST /api/pid-tuning` → validate and persist requested tuning, queue pending apply for the main loop

Recommended response shape:

```json
{
  "armed": false,
  "applied_revision": 3,
  "pending_revision": null,
  "values": {
    "yaw_rate_kp": 0.01,
    "yaw_rate_ki": 0.0,
    "yaw_rate_kd": 0.001,
    "yaw_rate_deadband_dps": 4.0,
    "yaw_rate_filter_hz": 5.0,
    "stabilization_min_throttle": 0.1,
    "neutral_stabilization_steering_limit": 0.12,
    "neutral_stabilization_max_throttle": 0.25
  },
  "defaults": {
    "yaw_rate_kp": 0.01,
    "yaw_rate_ki": 0.0,
    "yaw_rate_kd": 0.001,
    "yaw_rate_deadband_dps": 4.0,
    "yaw_rate_filter_hz": 5.0,
    "stabilization_min_throttle": 0.1,
    "neutral_stabilization_steering_limit": 0.12,
    "neutral_stabilization_max_throttle": 0.25
  },
  "last_error": null
}
```

Validation rules should bound values conservatively and reject malformed requests with `400`.

If the robot is armed, `POST` should return `409` and leave both persisted and running values unchanged.

## Runtime Ownership Model

The HTTP server must not mutate the assisted-drive controller directly from its own thread.

Instead:

- the HTTP handler validates input
- the handler writes a persisted JSON file and updates a lock-protected tuning store
- the main loop polls that store
- when disarmed and a new revision is pending, the main loop rebuilds the controller and marks the revision applied

This keeps all live controller mutation inside the control-loop owner thread and avoids cross-thread state corruption.

## Persistence Model

Env/config values remain the factory defaults.

After the first field save, `/data/pid-tuning.json` becomes the persistent operator override source. On startup, the controller should:

- read env-backed defaults
- load `/data/pid-tuning.json` if present
- validate persisted values
- merge persisted values over defaults
- build the initial controller from that merged snapshot

The file write should be atomic using the same temp-file plus `os.replace()` pattern already used for motor trim persistence.

## Safety Rules

Version 1 is disarmed-only by design.

- applying while armed is rejected
- page status must make the current armed state obvious
- controller rebuild resets transient control state cleanly
- no partial live mutation of one coefficient at a time

This keeps field tuning predictable and avoids introducing a new “tune while moving” hazard path.

## Module Layout

Recommended layout:

- extend `/home/builder/biba/biba-controller/motor_test_api.py` with PID-tuning page and JSON endpoints
- add a small new helper module for tuning state and persistence, for example `/home/builder/biba/biba-controller/pid_tuning.py`
- extend `/home/builder/biba/biba-controller/main.py` to load persisted values, expose armed state to the store, and apply pending revisions
- extend `/home/builder/biba/biba-controller/config.py` with any missing defaults and the persisted settings path

## Testing Strategy

Add focused coverage for:

1. tuning request validation and bounds checks
2. `GET /api/pid-tuning` response shape
3. `POST /api/pid-tuning` success while disarmed
4. `POST /api/pid-tuning` rejection while armed
5. persisted tuning load on startup
6. main-loop rebuild from a pending revision
7. page rendering and basic navigation between `/motor-test` and `/pid-tuning`

Avoid mixing control-law behavior tests with HTTP plumbing tests. Keep controller behavior in `tests/test_assisted_drive.py` and the new operator surface in API/main tests.

## Non-Goals

- no tuning while armed
- no charts or live graphs in v1
- no authentication layer in v1
- no new JS framework or separate frontend build
- no change to the stabilized-drive algorithm itself as part of this page