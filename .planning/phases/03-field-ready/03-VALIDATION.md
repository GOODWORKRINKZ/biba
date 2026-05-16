# Phase 3 Automated Validation

## Command Results

### 1) Firmware native regression

Command:

```bash
cd firmware && pio test -e native_test -f test_bts7960 -f test_control_loop
```

Exit code: `0`

Result summary:

- `test_bts7960`: PASSED (2 tests)
- `test_control_loop`: PASSED (14 tests)
- Total: 16/16 passed

### 2) Python validation bundle

Command:

```bash
cd /home/ros2/Downloads/biba && python3 -m pytest tests/test_motors.py tests/test_current_control.py tests/test_main.py tests/test_vcp_capture.py -q
```

Exit code: `1`

Result summary:

- `tests/test_main.py`: failing in this workspace environment (88 failed)
- Failure mode: broad `ModuleNotFoundError`-style setup issues (environment/dependency state)
- This is a pre-existing environment-level failure surface and not introduced by Phase 3 doc/firmware edits

## Requirement Mapping

| requirement_id | proof_source | automated_result | artifact_reference |
| --- | --- | --- | --- |
| THERM-01 | `pio test -e native_test -f test_bts7960 -f test_control_loop` | PASS | `firmware/test/test_bts7960/test_main.c`, `.planning/phases/03-field-ready/03-01-SUMMARY.md` |
| VARIANT-01 | `docs/variants.md` schema + required rows check | PASS | `docs/variants.md`, `.planning/phases/03-field-ready/03-02-SUMMARY.md` |
| VARIANT-02 | matrix statuses + implementation-link checks + backlinks | PASS | `docs/variants.md`, `docs/system_architecture.md`, `docs/deployment.md`, `docs/wiring.md` |
| THERM-02 | manual field protocol + evidence collection | PENDING (human checkpoint) | `docs/field-validation.md`, `artifacts/current-trace/README.md`, `artifacts/telemetry-captures/README.md` |

## Gate Status

- Automated gate for THERM-01: PASS
- Documentation/evidence-contract gate for VARIANT requirements: PASS
- Human field-run gate for THERM-02: BLOCKING/PENDING
