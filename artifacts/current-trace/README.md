# Current Trace Artifacts

This directory stores current-trace evidence used by Phase 3 field validation.

## Filename format

Use one run file per validation session:

- `current-trace-YYYYMMDD-HHMMSS-<run_id>.jsonl`

Example:

- `current-trace-20260516-173000-phase3-run01.jsonl`

## Runtime controls

Current trace in controller runtime is controlled by:

- `MOTOR_CURRENT_TRACE_ENABLED=1`
- `MOTOR_CURRENT_TRACE_PATH=/data/current-trace.jsonl`

These values are read by `biba-controller/main.py` and written as JSONL records.

## Required metadata keys

Each run must include metadata (in a companion `.meta.json` file or header record):

- `run_id`
- `timestamp_start`
- `timestamp_end`
- `operator`
- `firmware_target`
- `git_revision`
- `battery_pack_id`
- `ambient_temp_c`
- `protocol_version`
- `result`

## Validation mapping

This evidence supports:

- thermal behavior review during the 30-minute protocol
- pass/fail decisions in `docs/field-validation.md`
- requirement traceability in Phase 3 UAT
