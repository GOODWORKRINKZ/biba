---
phase: 03-field-ready
plan: 02
subsystem: docs
tags: [variants, field-validation, artifacts]
autonomous: true
---

# Phase 3 Plan 02: Canonical Variants + Field Evidence Docs

## Outcome
Completed the canonical hardware variant matrix, field-validation protocol, and artifact evidence contracts for THERM-02 / VARIANT requirements.

## Delivered
- Created canonical variant matrix:
  - `docs/variants.md`
- Added Phase 3 field protocol:
  - `docs/field-validation.md`
- Added artifact evidence contracts:
  - `artifacts/current-trace/README.md`
  - `artifacts/telemetry-captures/README.md`
- Added backlinks to canonical docs:
  - `docs/system_architecture.md`
  - `docs/deployment.md`
  - `docs/wiring.md`

## Verification
- Variants schema check command passed:
  - header matches required columns
  - rows for `Pi Zero 2W`, `RP2040`, `STM32F103` present
  - statuses constrained to `ready/WIP/planned`
  - implementation links present for required rows
- Grep checks passed for:
  - thermal reset wording (`EN/INH`, `100 us`, `PWM`) in `docs/field-validation.md`
  - backlinks (`variants.md`, `field-validation.md`) in `docs/wiring.md`
- Focused tests:
  - `python3 -m pytest tests/test_config.py -q` -> 35 passed
  - `python3 -m pytest tests/test_vcp_capture.py -q` -> 3 passed

## Known Test Gap
- `python3 -m pytest tests/test_main.py -q` fails with many `ModuleNotFoundError`-style failures in current workspace environment (87 failed), indicating a broader test-environment/setup issue not caused by the documentation-only changes in this plan.

## Requirement Traceability
- `VARIANT-01`: satisfied via canonical matrix in `docs/variants.md`.
- `VARIANT-02`: satisfied via implementation links and statuses in matrix rows.
- `THERM-02`: satisfied by explicit field protocol + evidence contract + thermal behavior wording aligned to D-01..D-04.
