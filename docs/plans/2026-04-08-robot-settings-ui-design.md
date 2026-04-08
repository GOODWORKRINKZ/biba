# Robot Settings UI Design

## Goal

Replace the ad-hoc pair of controller tools pages with a proper robot settings surface that lives in the same controller container but has a clearer backend/frontend split.

Version 1 should cover the settings that are actively tuned in the field right now:

- stabilized-drive PID and low-speed stabilization values
- persistent motor trim value
- the existing motor sound test functionality

The page should feel like an operator-facing settings screen, not a debugging form, and it should use a new animated BiBa neon logo where each letter has its own motion pattern.

## Decision

Keep the feature inside the current controller process and current container.

- no extra container
- no Node/Vite/React toolchain
- Python backend routes stay inside the controller runtime
- frontend moves out of inline HTML strings into dedicated static assets

This keeps deployment simple on the Pi Zero 2W while still giving a real frontend/backend structure.

## User-Facing Shape

Expose a new primary page at `/settings`.

The screen layout should be:

1. animated neon BiBa header
2. platform status strip (`armed`, `disarmed`, pending revisions, trim mode)
3. stabilized tuning section
4. motor trim section
5. motor sound test section

The page should be mobile-friendly, fast to load, and readable from a phone in the field.

## Frontend Structure

The frontend should be served from static assets in the controller repository, for example:

- `/home/builder/biba/biba-controller/web/settings.html`
- `/home/builder/biba/biba-controller/web/settings.css`
- `/home/builder/biba/biba-controller/web/settings.js`
- `/home/builder/biba/biba-controller/web/biba-neon-sign.svg`

The Python backend should only serve files and JSON endpoints. It should no longer own the main UI markup as large inline strings.

That gives us a clean split:

- backend: state, validation, persistence, actions
- frontend: layout, polling, form state, operator feedback

## Logo Direction

Do not animate the existing `docs/biba-logo-gradient.svg` in place.

Instead, create a separate animated SVG for the settings UI. The new logo should:

- keep the BiBa neon aesthetic
- use four independent letter groups (`Б`, `и`, `Б`, `а`)
- keep a subtle terminal or signboard framing language
- animate each letter differently

Recommended motion language:

- first `Б`: slow breathing pulse
- `и`: quick intermittent flicker
- second `Б`: stronger glow surges with long calm periods
- `а`: slight shimmer or phase-shifted pulse

The effect should feel like a living neon sign, not random glitch noise.

## Backend Routes

Recommended routes:

- `GET /settings` → main settings page HTML
- `GET /settings/assets/<name>` → static assets (`css`, `js`, `svg`)
- `GET /api/settings` → aggregated runtime/settings status for the whole page
- `POST /api/settings/pid-tuning` → update stabilized tuning values
- `POST /api/settings/motor-trim` → update persistent trim value
- `POST /api/settings/motor-test` → run the existing motor test action

Legacy compatibility should remain for now:

- `/motor-test` can redirect to `/settings#motor-test`
- `/pid-tuning` can redirect to `/settings#stabilized-tuning`
- `/api/motor-test` can remain as a compatibility alias to the new motor test action

This avoids breaking existing habits while making `/settings` the real entry point.

## Aggregated API Shape

`GET /api/settings` should return one payload that is enough to bootstrap and refresh the entire page.

Suggested shape:

```json
{
  "platform": {
    "armed": false,
    "trim_mode_active": false
  },
  "pid_tuning": {
    "current": {},
    "defaults": {},
    "pending": null,
    "applied_revision": 3,
    "pending_revision": null,
    "last_error": null
  },
  "motor_trim": {
    "current": 0.08,
    "pending": null,
    "applied_revision": 2,
    "pending_revision": null,
    "live_value": null,
    "last_error": null
  },
  "motor_test": {
    "active": false,
    "default_pwm_mode": "SOFTWARE",
    "frequency_options_hz": [100, 160, 200]
  }
}
```

The frontend should poll this endpoint on an interval and use it as the single source of truth for operator status.

## PID Tuning Behavior

The current persisted PID tuning behavior stays, but moves under the `/settings` page.

- disarmed-only updates
- persisted to `/data/pid-tuning.json`
- main loop remains the only owner that applies revisions
- page shows pending vs applied state

No change to the actual stabilized-drive algorithm is part of this UI refactor.

## Motor Trim Behavior

Motor trim needs two control paths at once:

1. existing RC gesture workflow remains supported
2. new UI can inspect and update the saved trim directly

The UI-managed trim should be the saved persistent trim, not the temporary live `CH9` value used during trim mode.

The page should show:

- saved trim (`current`)
- pending trim revision if a UI update is queued
- whether trim mode is active
- live trim value while trim mode is active, if available

UI trim updates should be disarmed-only for consistency and safety.

When the RC gesture saves a new trim, the backend state exposed to the page must update so the page reflects the new persistent value without a restart.

## Motor Sound Test Behavior

Keep the current motor test functionality as-is, but present it as one section inside the new settings page instead of as the primary tool.

Version 1 should keep:

- software/hardware PWM mode choice
- left/right frequency fields
- left/right duty fields
- duration
- busy protection

No new synth/voice test mode is required in this version.

## Runtime Ownership Model

As with PID tuning, the HTTP thread must not mutate controller-owned runtime state directly.

Use store objects with main-loop ownership for any live values that affect control behavior.

Recommended stores:

- existing `PidTuningStore`
- new `MotorTrimStore`

The main loop should:

- load both persisted settings on startup
- feed stores with current armed state
- apply pending PID revisions by rebuilding the controller
- apply pending trim revisions by updating the saved trim value used in the loop
- push back RC-driven trim saves into the trim store state

## Module Layout

Recommended layout:

- add `/home/builder/biba/biba-controller/settings_store.py` for motor trim state and any small shared settings-state helpers
- refactor `/home/builder/biba/biba-controller/motor_test_api.py` into a settings-oriented backend while preserving compatibility helpers
- keep `/home/builder/biba/biba-controller/pid_tuning.py`
- extend `/home/builder/biba/biba-controller/main.py` with trim store ownership and `/settings` server wiring
- add frontend assets under `/home/builder/biba/biba-controller/web/`

## Testing Strategy

Add focused coverage for:

1. motor trim store load, save, pending revisions, and disarmed-only updates
2. aggregated `/api/settings` response shape
3. `/settings` static asset serving
4. legacy redirect or compatibility routes
5. main-loop trim store integration with both UI updates and RC gesture saves
6. frontend asset references and logo inclusion

Do not try to browser-test animation details in pytest. Validate the asset exists, the page references it, and the API contracts are correct.

## Non-Goals

- no full env editor in version 1
- no authentication layer in version 1
- no separate web container
- no JS framework
- no removal of existing RC trim workflow
- no redesign of motor test logic itself