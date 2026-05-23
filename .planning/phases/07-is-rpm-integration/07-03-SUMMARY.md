# Plan 07-03 Summary — CALRUN command + IS-RPM calibration script

**Phase**: 07-is-rpm-integration
**Plan**: 07-03
**Status**: Complete
**Branch**: develop
**Commits**: `211de5d`, `7198a22`

---

## Objective Delivered

Closed RPM-INT-03 calibration requirement. Added the `CALRUN` USB CDC command
to the PoC firmware and an offline `scripts/is_rpm_calibrate.py` workflow that
drives the firmware, prompts the operator for tachometer readings, fits a
linear K-coefficient model, and writes a JSON artifact.

This plan is independent of the standalone integration plans (07-01/02/04/05)
and required no changes to production firmware sources.

---

## Changes

### PoC firmware (commit `211de5d`)
- `firmware/src/poc/is_rpm_poc_main.cpp`:
  - Added `static void cmd_calrun(int duty_pct, uint32_t settle_ms)` placed
    just before `setup()`:
    - Validates `0 <= duty_pct <= 100` and `100 <= settle_ms <= IS_POC_MAX_SETTLE_MS (10000)`;
      out-of-range → `Serial.println("ERROR bad args")`.
    - Sets IS_LEFT forward duty via `biba_hal_motor_pwm_left(duty_pct/100.0f)`.
    - Settles, then runs 5× `adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, 1024, s_buf)`
      at 10 kSPS using the existing static `zc_freq_hz()`.
    - Insertion-sorts the 5 results and takes the middle as median.
    - Always stops the motor (`biba_hal_motor_pwm_left(0.0f)`) before returning,
      even on `adc_capture_burst` failure.
    - Reports `IS_HZ <duty_pct> <median_hz_x100>` (0.01 Hz resolution).
  - Added dispatcher entry between `STEPRUN` and `SWEEP`:
    `if (line.startsWith("CALRUN ")) { ... sscanf ... cmd_calrun(...); return; }`

### Calibration script (commit `7198a22`)
- `scripts/is_rpm_calibrate.py` (new, +executable):
  - CLI: `--port`, `--wheel {left,right}`, `--duties`, `--settle-ms`,
    `--dry-run`, `--out-dir`.
  - Real run: opens `pyserial` at 115200, sends `CALRUN <duty> <settle_ms>`,
    parses `IS_HZ` response (timeout 15 s), prompts operator for tach Hz per
    point (skip allowed), sends `STOP` on exit.
  - `--dry-run`: deterministic synthetic points (seed=42, K=10.13,
    dead_hz=74.6, ±2 % noise) — full numeric path with no serial/prompts.
  - Linear fit: `numpy.polyfit(duties, tach, 1)` →
    `K_hz_per_pct = coeffs[0]`, `dead_hz = -coeffs[1]` (matches firmware
    FF model `hz = K*duty - dead_hz`, i.e. `RPMRUN_FF_DEAD_DEFAULT`).
  - R² computed via SSres/SStot; stderr warning printed when R² < 0.95.
  - Artifact written to `<out-dir>/<YYYY-MM-DD>_<wheel>.json`; path printed
    to stdout.
  - Requires ≥3 valid tachometer points or exits with `RuntimeError`.
- `scripts/artifacts/calibration/2026-05-23_left.json` — sample artifact from
  a dry-run, committed alongside as a schema reference (mirrors convention
  used by `scripts/artifacts/is-step/step.csv`).

---

## Verification (all gates green)

| Gate | Result |
|------|--------|
| `pio run -e rpico_rp2040_is_poc` | SUCCESS (5.49 s) |
| `grep -c "CALRUN\|cmd_calrun" firmware/src/poc/is_rpm_poc_main.cpp` | 5 |
| `python3 scripts/is_rpm_calibrate.py --dry-run --wheel left` | exit 0, prints path |
| Sample JSON contains `K_hz_per_pct, dead_hz, r_squared, points` | yes |
| Synthetic-data assertions: K∈[9.5,10.8], dead∈[60,90], R²≥0.95 | K=10.106 dead=74.32 R²=1.0 |
| `--dry-run --wheel right` exit code | 0 |

## Self-Check: PASSED

- Threat mitigations in place:
  - **T-07-03-01** (duty out of range): firmware validates `0..100` before
    touching motor.
  - **T-07-03-02** (settle_ms too large): firmware caps at
    `IS_POC_MAX_SETTLE_MS = 10000` ms.
  - **T-07-03-03** (tachometer input): script wraps `float(val)` in
    try/except, non-numeric → skip with stderr warning, no shell exec.
  - **T-07-03-04** (artifact perms): files written with default umask;
    acceptable for local dev tool.
- Motor is always stopped before `cmd_calrun` returns (including on capture
  failure path).
- No nested `cmd_rpmrun` call from `cmd_calrun` (as required by Task 1).

## Deviations

**Deviation #1 (Rule 1 — fixed bug pre-commit):** Initial `dead_hz` formula
divided by K (`-intercept/K`), which yielded the dead-zone *duty percent*,
not the dead-zone Hz value. The PoC firmware FF model is
`hz = K * duty - dead_hz`, so `dead_hz = -intercept` directly. Fixed before
committing Task 2 so the artifact is drop-in compatible with
`RPMRUN_FF_DEAD_DEFAULT = 74.6`. Synthetic dry-run now produces
`dead_hz ≈ 74.32` (target 74.6).

## Notes for downstream plans

- Plan 07-04's RPM controller (`firmware/src/app/rpm_pi.h/.c`) will read
  K_hz_per_pct + dead_hz from the calibration artifact (loaded by the
  Python side at startup, not from firmware NVRAM) and feed them into the
  FF term `ff_duty = (target_hz + dead_hz) / K`.
- The PoC `IS_HZ` line format is `IS_HZ <duty_pct> <median_hz_x100>`. If
  Plan 07-04 ever needs to call CALRUN from a host integration test, mirror
  the `_read_is_hz()` parser in `scripts/is_rpm_calibrate.py`.
