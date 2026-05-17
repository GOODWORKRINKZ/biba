# Phase 4 Validation Test Report

## Purpose

This report captures the validation evidence available in the repository for the Phase 4 thermal-hardening path.

## Validation Summary

- Native firmware unit tests passed for the thermal reset path and the control-loop current limiter.
- The repository contains field log evidence showing current-limit activity and arm/disarm cycling.
- The available field log is **not** a 60+ minute continuous load run, so the phase acceptance criterion for long-run validation is still pending external execution.

## Repository Validation Executed

Command used:

```bash
cd /home/ros2/Downloads/biba/firmware && pio test -e native_test -f test_control_loop -f test_bts7960
```

Result:

- `test_bts7960`: passed
- `test_control_loop`: passed

What this proves:

- the BTS7960 reset path still zeroes PWM and toggles enable lines in a deterministic order;
- the current limiter still scales motor output independently when current or power exceeds the configured limit;
- the firmware change did not break the portable thermal-control logic.

## Field Evidence Available In Repo

Referenced log:

- [robot-stand-tremor-2026-04-06.log](../../../artifacts/current-trace/robot-stand-tremor-2026-04-06.log)

Observed properties from that log:

- the system arms and disarms cleanly;
- current-limit related warnings are present during loaded driving;
- the run demonstrates control-loop activity under motion;
- the log does not reach the 60+ minute thermal target, so it is evidence of behavior, not proof of the phase acceptance criterion.

## Required Metadata Status

| Field | Status |
|-------|--------|
| run_id | pending external field session |
| timestamp_start | not captured in a 60+ minute run here |
| timestamp_end | not captured in a 60+ minute run here |
| operator | not captured |
| firmware_target | RP2040 thermal-hardening path |
| git revision | current workspace revision |
| battery_pack_id | not captured |
| ambient_temp_c | not captured |
| outcome | partial validation only |

## Outcome

The firmware-side thermal path is verified enough for repository review, but the long-duration field requirement is still outstanding. This report should be treated as a validation checkpoint, not the final acceptance proof for the phase.
