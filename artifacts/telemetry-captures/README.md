# Telemetry Capture Artifacts

This directory stores serial/VCP telemetry captures for field validation runs.

## Capture command

Use the repository capture tool:

```bash
python3 scripts/vcp_capture.py --help
```

Typical run:

```bash
python3 scripts/vcp_capture.py --device /dev/ttyACM0 --baud 115200
```

Default output path:

- `artifacts/telemetry-captures/vcp-YYYYMMDD-HHMMSS.log`

## Filename format

Prefer explicit run IDs when possible:

- `vcp-YYYYMMDD-HHMMSS-<run_id>.log`

## Required metadata keys

Each capture set must include metadata (sidecar file or UAT record):

- `run_id`
- `capture_file`
- `timestamp_start`
- `timestamp_end`
- `operator`
- `firmware_target`
- `git_revision`
- `battery_pack_id`
- `result`

## Validation mapping

Telemetry captures support:

- event timeline reconstruction for 30-minute protocol
- correlation with current trace artifacts
- evidence completeness checks in `docs/field-validation.md`
