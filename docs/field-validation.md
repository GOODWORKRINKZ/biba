# Field Validation Protocol (Phase 3)

This protocol defines pass/fail evidence for Phase 3 field readiness.

## Hardware prerequisites

- BTS7960 modules are wired per [wiring.md](wiring.md).
- Common ground between controller and motor-power domains is confirmed.
- Motor power path and enable lines are electrically stable at idle.
- Current and telemetry capture paths are prepared:
  - `artifacts/current-trace/`
  - `artifacts/telemetry-captures/`
- Operator has a checklist copy and run ID for this session.

## Heat-sink installation evidence

Collect before any run:

- Photo of each BTS7960 mounted on a metal plate/heat sink.
- Photo showing thermal interface (pad/paste) and mechanical fixation.
- Note ambient temperature and weather conditions.
- Record run metadata (operator, date/time, battery pack ID, firmware revision).

## Thermal reset contract (locked decisions)

The brushed BTS7960 path uses the enable/inhibit reset path:

- D-01: Thermal-fault recovery uses BTS7960 EN/INH behavior, not SSR power-cut reset.
- D-02: Reset sequence drives both enable lines LOW, then HIGH before motion is allowed.
- D-03: Reset pulse holds enable LOW for **100 us**.
- D-04: PWM remains zero while enable is LOW and until enable returns HIGH.

## 30-minute drive protocol

1. Start in a safe open area with obstacle clearance.
2. Arm system and perform 5-minute warm-up with mixed throttle/steering.
3. Execute a 30-minute intensive run with repeated accelerations, turns, and reverse transitions.
4. Every 5 minutes record observed behavior:
   - motor response consistency
   - thermal smell/noise anomalies
   - any failsafe interventions
5. If thermal latch behavior is observed, record:
   - timestamp
   - whether EN reset sequence recovered safely
   - whether repeated events occurred

## Abort criteria

Abort immediately if any condition occurs:

- uncontrolled motion or delayed disarm
- repeated thermal shutdown with no stable recovery
- visible smoke, burning smell, or unsafe enclosure temperature
- power instability (brownout/reboot behavior)

## Required artifacts

Place artifacts in repository paths:

- Current trace bundle in `artifacts/current-trace/`
- VCP/telemetry capture logs in `artifacts/telemetry-captures/`
- Heat-sink photos and run notes referenced in UAT

Required metadata per run:

- `run_id`
- `timestamp_start` and `timestamp_end`
- `operator`
- `firmware_target` and git revision
- `battery_pack_id`
- `ambient_temp_c`
- `outcome` (pass/fail)

## Pass/fail rubric

Pass:

- No unsafe thermal event during the 30-minute intensive run.
- If a thermal latch event occurs, EN reset behavior is safe and controlled.
- Evidence set is complete and auditable (logs + metadata + photos + checklist).

Fail:

- Any abort criterion triggered.
- Missing mandatory evidence artifacts or metadata.
- Thermal behavior inconsistent with D-01..D-04 contract.
