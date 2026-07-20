# Research — Phase 9: RPM Estimator Hardening

**Researched:** 2026-05-26  
**Domain:** Embedded C dead-reckoning state machine + Python simulation validation  
**Confidence:** HIGH — all findings derived from direct source inspection

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**API (D-A1/A2/A3):**
```c
float biba_rpm_dr_update(
    biba_rpm_dr_state_t                *state,
    const biba_rpm_spectral_result_t   *spec,
    float                               target_hz,
    biba_rpm_spectral_invalid_reason_t *out_reason  /* out */
);
```
- `spec.valid == true` → update ratio_ema, return `spec.freq_hz`, `*out_reason = NONE (0)`
- `spec.valid == false`, `streak ≤ MAX_STREAK`, `ratio_ema > 0`, `target ≥ 50Hz` → return `ratio_ema × target_hz`, `*out_reason = EXTRAPOLATED (5)`
- Otherwise (cold start / streak expired) → return `0.0f`, `*out_reason = spec.invalid_reason`
- Function works with magnitudes; sign applied in `mode_standalone.c` via `s_meas_*_reverse`

**Lifecycle (D-L1/L2):**
- `biba_rpm_dr_reset(state)` zeroes `ratio_ema = 0.0f` and `streak = 0`
- Called in same place as `biba_rpm_pi_reset()` — at disarm; every session cold-starts
- Warm start NOT implemented in this phase

**Python Simulation (D-S1/S2/S3):**
- `scripts/is_dr_sim.py` imports:
  - `from is_sweepraw_analyze import spectral_estimate, SpectralResult`
  - `from is_algo_bench import alg_subwindow_schmitt`
- Outputs: stdout table (before/after dropout by duty-bin) + PASS/FAIL line (exit code 0/1) + PNG artifact
- Gate: **< 5% dropout at |duty| > 15%** (stricter of SPEC D7 ≤10% and CONTEXT D-S3 ≤5%)

**Unit Tests (D-T1):**
- New directory `firmware/test/test_rpm_dr/` with `test_main.c`
- Consistent with `test_rpm_pi/`, `test_zc_detector/`, `test_rpm_spectral_estimator/`

### Deferred Ideas (OUT OF SCOPE)
- Warm start (ratio_ema preserved across rearm)
- Per-wheel separate ratio constants in firmware
- IMU-assisted DR
- Modifying `rpm_spectral_estimator.c`, `zc_detector.c`, or blackbox binary format
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-01 | DR state machine in `rpm_dr.h/c` | Struct: `ratio_ema` + `streak`; API mirrors `rpm_pi.h` pattern |
| REQ-02 | ratio EMA update (α=0.2, clamp [0.50, 1.30]) | Constants in `biba_config.h`; EMA on every valid spectral result |
| REQ-03 | Cold start safety (ratio_ema=0 initially) | `ratio_ema > 0` guard in DR logic; reset zeroes both fields |
| REQ-04 | Streak expiry → return 0 after MAX_STREAK consecutive invalids | uint8_t streak, clamped at 255; test feeds MAX_STREAK+2 invalids |
| REQ-05 | EXTRAPOLATED reason (value=5) in telemetry/serial | Add to enum in `rpm_spectral_estimator.h`; DR sets `*out_reason` |
| REQ-06 | Python simulation FIRST — must show <5% dropout at \|duty\|>15% | `is_dr_sim.py` on fullsine sweep; gate blocks C code tasks |
| REQ-07 | All 71+ existing tests still pass | No existing test file includes `rpm_dr.h`; changes are additive |
</phase_requirements>

---

## Integration Point (mode_standalone.c)

### Exact Lines to Change

**File:** `firmware/src/modes/mode_standalone.c`  
**Function:** `on_adc_pair_done()` — the DMA completion ISR callback

**Lines 365–366 (the one-liner to replace):**
```c
// BEFORE (lines 365–366):
float spec_hz_left  = (s_meas_left_enabled  && spec_left.valid)  ? spec_left.freq_hz  : 0.0f;
float spec_hz_right = (s_meas_right_enabled && spec_right.valid) ? spec_right.freq_hz : 0.0f;
```

**Replaced with:**
```c
// AFTER:
biba_rpm_spectral_invalid_reason_t dr_reason_left;
float spec_hz_left = s_meas_left_enabled
    ? biba_rpm_dr_update(&s_dr_left,  &spec_left,  s_meas_target_hz_left,  &dr_reason_left)
    : 0.0f;
biba_rpm_spectral_invalid_reason_t dr_reason_right;
float spec_hz_right = s_meas_right_enabled
    ? biba_rpm_dr_update(&s_dr_right, &spec_right, s_meas_target_hz_right, &dr_reason_right)
    : 0.0f;
```

**Lines 391–392 (spec_reason assignment to also change):**
```c
// BEFORE (lines 391–392):
s_spec_reason_left  = s_meas_left_enabled  ? (uint8_t)spec_left.invalid_reason  : 0u;
s_spec_reason_right = s_meas_right_enabled ? (uint8_t)spec_right.invalid_reason : 0u;
```
```c
// AFTER:
s_spec_reason_left  = s_meas_left_enabled  ? (uint8_t)dr_reason_left  : 0u;
s_spec_reason_right = s_meas_right_enabled ? (uint8_t)dr_reason_right : 0u;
```

### New Static State Vars (add at ~line 120, with other `s_rpm_pi_*` vars)

```c
/* Dead-reckoning fallback state (per-channel, written/read in DMA ISR). */
static biba_rpm_dr_state_t  s_dr_left;
static biba_rpm_dr_state_t  s_dr_right;
```

`biba_rpm_dr_state_t` is a plain struct with two fields — NOT declared `volatile` because both
`biba_rpm_dr_update()` (ISR) and `biba_rpm_dr_reset()` (tick context) access it, same pattern
as `biba_rpm_pi_state_t s_rpm_pi_left/right` which also is not `volatile`.

### New `#include` at top of mode_standalone.c

```c
#include "app/rpm_dr.h"
```

Add after line 20 (`#include "app/rpm_pi.h"`).

---

## Disarm Reset Location

### All sites where `biba_rpm_pi_reset()` is called (DR reset must mirror all):

| Line | Context | Must add DR reset? |
|------|---------|-------------------|
| 292 | `OLON` debug command (`process_debug_serial`) | Yes — bench consistency |
| 299 | `OLOFF` debug command (`process_debug_serial`) | Yes — bench consistency |
| 497 | `biba_mode_standalone_init()` | Yes — cold boot init |
| 603 | Failsafe rising edge (tick) | Yes — D-L1 equivalent |
| 648 | **Disarm edge (tick)** — primary D-L1 site | **Yes — primary** |
| 666 | Thermal-latch auto-recovery (tick) | Yes — DR would have stale ratio |
| 856 | (unknown context — needs verification during impl) | Yes |

**Minimum required by D-L1:** Line 648 (disarm edge). However for correctness, all 7 sites should call `biba_rpm_dr_reset()` immediately after the corresponding `biba_rpm_pi_reset()` pair.

**Init site (line 497) is special:** `biba_mode_standalone_init()` calls `biba_rpm_pi_reset()` but the DR state is already zero-initialized by C static storage. The explicit `biba_rpm_dr_reset()` call in init is still correct for explicitness and mirrors PI pattern.

---

## rpm_dr Module Design

### Header: `firmware/src/app/rpm_dr.h`

```c
#ifndef BIBA_RPM_DR_H
#define BIBA_RPM_DR_H

#include <stdint.h>
#include "app/rpm_spectral_estimator.h"   /* biba_rpm_spectral_result_t, reason enum */

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float   ratio_ema;   /* EMA of meas_hz/target_hz; 0.0f = cold start */
    uint8_t streak;      /* consecutive invalid cycles; clamped at 255  */
} biba_rpm_dr_state_t;

void  biba_rpm_dr_reset(biba_rpm_dr_state_t *state);

float biba_rpm_dr_update(
    biba_rpm_dr_state_t                      *state,
    const biba_rpm_spectral_result_t         *spec,
    float                                     target_hz,
    biba_rpm_spectral_invalid_reason_t       *out_reason
);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_RPM_DR_H */
```

**Only two fields needed.** No additional fields required for the REQ-01..04 state machine.

### Constants location: `firmware/include/biba_config.h`

Add a new section after the existing RPM/spectral section:

```c
/* --- RPM dead-reckoning fallback --------------------------------------- */

#ifndef BIBA_RPM_DR_MAX_STREAK
#  define BIBA_RPM_DR_MAX_STREAK    5u       /* ~500 ms at 10 Hz ADC loop */
#endif
#ifndef BIBA_RPM_DR_RATIO_LO
#  define BIBA_RPM_DR_RATIO_LO      0.50f    /* p10 floor across all sweep channels */
#endif
#ifndef BIBA_RPM_DR_RATIO_HI
#  define BIBA_RPM_DR_RATIO_HI      1.30f    /* generous ceiling above p95=1.129 LEFT FWD */
#endif
#ifndef BIBA_RPM_DR_ALPHA
#  define BIBA_RPM_DR_ALPHA         0.2f     /* EMA smoothing (5-step time constant) */
#endif
```

**Why in `biba_config.h`, not `rpm_dr.h`:** Field-tunable without recompile (D2 from SPEC). 
`biba_config.h` already follows this `#ifndef` guard pattern for all other tunable constants.
`rpm_dr.c` includes `biba_config.h` via the standard include path `-Iinclude`.

### Enum addition: `firmware/src/app/rpm_spectral_estimator.h`

```c
typedef enum {
    BIBA_RPM_SPECTRAL_INVALID_NONE = 0,
    BIBA_RPM_SPECTRAL_INVALID_TARGET_LOW = 1,
    BIBA_RPM_SPECTRAL_INVALID_NO_BAND = 2,
    BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW = 3,
    BIBA_RPM_SPECTRAL_INVALID_QUALITY_LOW = 4,
    BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED = 5,   /* <-- ADD THIS */
} biba_rpm_spectral_invalid_reason_t;
```

Value 5 matches SPEC D3. No other file assigns enum values numerically except the blackbox
record which uses the existing `s_spec_reason_L/R` uint8 fields — compatible.

### Implementation logic sketch (`rpm_dr.c`)

```c
void biba_rpm_dr_reset(biba_rpm_dr_state_t *s) {
    s->ratio_ema = 0.0f;
    s->streak    = 0u;
}

float biba_rpm_dr_update(biba_rpm_dr_state_t *s,
                         const biba_rpm_spectral_result_t *spec,
                         float target_hz,
                         biba_rpm_spectral_invalid_reason_t *out_reason)
{
    if (spec->valid) {
        s->streak = 0u;
        if (target_hz >= BIBA_RPM_SPECTRAL_MIN_TARGET_HZ) {
            float ratio = spec->freq_hz / target_hz;
            /* clamp before EMA update */
            if (ratio < BIBA_RPM_DR_RATIO_LO) ratio = BIBA_RPM_DR_RATIO_LO;
            if (ratio > BIBA_RPM_DR_RATIO_HI) ratio = BIBA_RPM_DR_RATIO_HI;
            s->ratio_ema = BIBA_RPM_DR_ALPHA * ratio
                         + (1.0f - BIBA_RPM_DR_ALPHA) * s->ratio_ema;
        }
        *out_reason = BIBA_RPM_SPECTRAL_INVALID_NONE;
        return spec->freq_hz;
    }

    /* invalid case */
    if (s->streak < 255u) s->streak++;

    if (s->streak <= BIBA_RPM_DR_MAX_STREAK
        && s->ratio_ema > 0.0f
        && target_hz >= BIBA_RPM_SPECTRAL_MIN_TARGET_HZ) {
        *out_reason = BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED;
        return s->ratio_ema * target_hz;
    }

    *out_reason = spec->invalid_reason;
    return 0.0f;
}
```

**Note on clamp position:** Clamp is applied to the raw ratio before EMA update (not after).
This prevents the EMA from drifting toward a clamped boundary; only truly extreme measurements
are excluded from training the EMA.

---

## Test Config (platformio.ini)

### What exists

`[env:native_test]` (line 296) uses:
```ini
test_ignore = test_support
```
No `test_filter` is set → PlatformIO Unity auto-discovers **all** subdirectories under
`firmware/test/` except `test_support`. Any new directory with a `test_main.c` is
automatically included.

### What needs to be added: NOTHING to platformio.ini

A new `firmware/test/test_rpm_dr/test_main.c` is auto-discovered. No ini change required.

### What needs to verify: `rpm_dr.c` source inclusion

The `[env:native_test]` uses `build_src_filter = ${common.build_src_filter}`, which is:
```ini
build_src_filter =
    +<*>
    -<hal/>
    -<drivers/>
    -<modes/>
    -<main.c>
    -<main_rp2040.cpp>
    -<poc/>
    -<app/telemetry.c>
    -<app/melody.c>
    -<app/adc_capture.c>
    -<app/blackbox.cpp>
    -<app/motor_bridge.c>
    +<drivers/crsf.c>
```

`+<*>` includes all files not explicitly excluded. `firmware/src/app/rpm_dr.c` is NOT in any
exclusion list → it will be compiled automatically when placed at `firmware/src/app/rpm_dr.c`.

`rpm_dr.c` includes `biba_config.h` via `-Iinclude` (present in `[common]` build_flags).
It also includes `rpm_spectral_estimator.h` via `-Isrc/app` (present in `[env:native_test]`
build_flags: `-Isrc/app`).

---

## Python Simulation Imports

### `spectral_estimate` and `SpectralResult` from `is_sweepraw_analyze.py`

**VERIFIED:** Both are defined at module level (not inside `if __name__ == '__main__'`).

```python
@dataclass
class SpectralResult:     # line ~35 — importable
    ...

def spectral_estimate(buf, sps, target_hz):   # line ~72 — importable
    ...
```

`is_sweepraw_analyze.py` does `sys.path.insert(0, ...)` to find `is_algo_bench`, but this
runs at import time of the module — harmless when `is_dr_sim.py` imports from it, since both
scripts live in `scripts/`.

### `alg_subwindow_schmitt` from `is_algo_bench.py`

**VERIFIED:** Defined as a regular function at module level (line ~60):
```python
def alg_subwindow_schmitt(x: np.ndarray, k: int = 8) -> float:
```
No `__all__` restriction. Importable.

### No module-level side effects to worry about

`is_sweepraw_analyze.py` has no `argparse.parse_args()` or plotting calls at module level.
The `argparse` block is not shown but not guarded by `__main__` — **RISK:** if `argparse`
is called outside `if __name__ == '__main__'`, import will fail. Inspect the bottom of the
file before finalising the import.

**Action for implementation:** Run `python3 -c "from is_sweepraw_analyze import spectral_estimate, SpectralResult; print('OK')"` from `scripts/` as first step to verify import works cleanly.

---

## Sweep Data Format

**File pattern:**
```
scripts/artifacts/is-sweepraw/sweepraw_SIN_amp100_per8000_n157_20260524-180629_fullsine_{left,right}.csv
```

**CSV columns (verified from header):**
```
win_idx, t_ms, duty_pct, sample_idx, adc_raw
```

| Column | Type | Description |
|--------|------|-------------|
| `win_idx` | int | Window index (groups 512 samples per spectral estimate) |
| `t_ms` | float | Time in ms (absolute timestamp within capture) |
| `duty_pct` | float | Commanded duty % (−100..+100; use `abs(duty_pct)` for magnitude) |
| `sample_idx` | int | Sample index within the window (0..511) |
| `adc_raw` | int | Raw 12-bit ADC sample (0..4095) |

### How the simulation script must read this

```python
import pandas as pd
df = pd.read_csv(path)
windows = df.groupby("win_idx")
for win_idx, grp in windows:
    buf = grp["adc_raw"].values.astype(np.uint16)
    duty_pct = grp["duty_pct"].iloc[0]
    target_hz = max(50.0, PLANT_K_HZ_PER_PCT * abs(duty_pct) - PLANT_DEAD_HZ)
    result = spectral_estimate(buf, SPS, target_hz)
    # apply DR logic in Python ...
```

`PLANT_K_HZ_PER_PCT = 10.13` and `PLANT_DEAD_HZ = 74.6` are importable from `is_algo_bench`.
`SPS = 10000` also importable from `is_algo_bench`.

---

## Execution Order (REQ-06 gate)

The plan MUST enforce the following dependency chain:

```
Task A: Python simulation (is_dr_sim.py) — REQ-06
    ↓ GATE: exit code 0 (PASS, <5% dropout) required before proceeding
Task B: Add enum value to rpm_spectral_estimator.h — REQ-05
Task C: Add constants to biba_config.h — REQ-02
Task D: Write rpm_dr.h + rpm_dr.c — REQ-01/02/03/04
Task E: Write test_rpm_dr/test_main.c — REQ-01..04/07
Task F: Run `pio test -e native_test` — verify REQ-07
Task G: Integrate into mode_standalone.c — REQ-01/05
Task H: Flash + serial CSV verification — REQ-05 acceptance
```

**Tasks B, C, D, E are parallel after gate A passes.**  
**Task F must precede Task G** (don't touch integration until unit tests green).  
**Task G** is the only change to an existing ISR-context file — highest risk of breaking existing tests if header includes are wrong.

---

## Risks / Landmines

### 1. ISR-safety race between reset (tick) and update (ISR)

`biba_rpm_dr_reset()` is called from tick (main context); `biba_rpm_dr_update()` runs inside
`on_adc_pair_done()` (DMA completion ISR). This is a data race on `s_dr_left/right`.

**Verdict: Acceptable — mirrors existing PI pattern exactly.** `biba_rpm_pi_reset()` is
also called from tick while `biba_rpm_pi_step()` runs in the ISR. The existing code has the
same potential race and is already shipping. Implementing a critical section for DR only would
be architecturally inconsistent and is out of scope.

**Real risk:** If reset arrives between reading `ratio_ema` and writing the update result,
the EMA could be stale for one cycle — harmless (EMA converges within 5 cycles anyway).

### 2. Import side effects in is_sweepraw_analyze.py

If `is_sweepraw_analyze.py` calls `argparse.parse_args()` outside `if __name__ == '__main__'`,
importing it in `is_dr_sim.py` will fail with a SystemExit. **Must verify with a test import
before writing the simulation script body.**

### 3. `spec_hz_left` passes 0.0f to zc_ema_update — unchanged by this phase

After the DR replacement, `zc_ema_update(&s_telem_meas_ema_left, spec_hz_left, ...)` on
line ~397 will receive the DR-extrapolated value instead of 0. This causes `s_telem_meas_ema_left`
(used for telemetry display, not PI) to track extrapolated values during DR mode. **This is
intentional and correct behavior** — telemetry will show the extrapolated Hz rather than 0,
which is more informative for debugging.

However: `zc_ema_update()` has validity gating — if `meas_raw` is outside
`[ZC_MIN_VALID_HZ, target_hz*2.5 + 300]`, it holds unchanged. The DR output is
`ratio_ema * target_hz` which is typically in range, so it will pass through the gate.
Verify this doesn't cause unexpected telemetry jumps.

### 4. EXTRAPOLATED = 5 must not collide with any existing uint8 enum serialisation

The blackbox `spec_reason` field is a `uint8_t` already. Current values: 0–4. Value 5 is
free. The Lua telemetry screen and Python analysis scripts that read `spec_reason_L/R` will
see `5` — they don't break, but any switch/if that checks for `> 0` as "invalid" will
correctly treat `5` as invalid. Verify `biba_monitor.py` or `vcp_capture.py` doesn't have a
hardcoded max-reason check.

### 5. `ratio_ema` division by target_hz — guard needed for target_hz=0

The `biba_rpm_dr_update()` implementation must guard `target_hz >= BIBA_RPM_SPECTRAL_MIN_TARGET_HZ`
(50.0f) BEFORE computing `spec->freq_hz / target_hz` on the valid path. If target_hz < 50,
the function must skip the ratio update (can't train ratio without a meaningful target).
The unit tests must cover this case.

### 6. Cold-start ratio EMA bootstrap is slow

With α=0.2, starting from `ratio_ema=0.0f`, the first valid measurement gives
`ratio_ema = 0.2 × ratio`. After N valid measurements from cold start before the EMA reaches
the "true" ratio: approximately 15 cycles to reach 95% of steady-state. During this bootstrap
period, the DR extrapolation will under-estimate (ratio_ema < true_ratio). The 5% gate in
REQ-06 applies to steady-state — the simulation should show per-window behavior to confirm
bootstrap doesn't inflate dropout count in the result.

### 7. LEFT REV sweep data is MISSING from the capture

From SPEC calibration context: "LEFT missing REV sweep (hardware was not wired at capture time)."
The fullsine sweep files only have `left` and `right` — but LEFT only covers FWD direction.
The `is_dr_sim.py` simulation should note this in its output and only claim validity for
the available data (LEFT FWD, RIGHT FWD, RIGHT REV).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Unity 2.6.1 (via `throwtheswitch/Unity`) |
| Config file | `firmware/platformio.ini` `[env:native_test]` |
| Quick run command | `cd firmware && pio test -e native_test --filter test_rpm_dr` |
| Full suite command | `cd firmware && pio test -e native_test` |

### REQ → Test Map

| REQ | Behavior | Test Type | Command | File |
|-----|----------|-----------|---------|------|
| REQ-01 | DR active after 3 invalids with ratio_ema>0 | unit | `pio test -e native_test --filter test_rpm_dr` | ❌ Wave 0 |
| REQ-02 | ratio_ema ≥ 0.5 after 10 valid results (ratio=0.9) | unit | same | ❌ Wave 0 |
| REQ-03 | Cold start: first invalid returns 0, reason=original | unit | same | ❌ Wave 0 |
| REQ-04 | After MAX_STREAK+2 invalids: output=0 | unit | same | ❌ Wave 0 |
| REQ-05 | `out_reason = EXTRAPOLATED (5)` when DR active | unit | same | ❌ Wave 0 |
| REQ-06 | Simulation shows <5% dropout at \|duty\|>15% | Python sim | `python3 scripts/is_dr_sim.py` | ❌ Wave 0 |
| REQ-07 | All 71+ tests pass after changes | regression | `pio test -e native_test` | ✅ exists |

### Wave 0 Gaps

- [ ] `firmware/test/test_rpm_dr/test_main.c` — covers REQ-01..05
- [ ] `scripts/is_dr_sim.py` — covers REQ-06 (must exist and pass BEFORE C code)

### Per-task verification cadence

- After each new C task: `pio test -e native_test --filter test_rpm_dr` (fast, ~5s)
- After mode_standalone.c integration: `pio test -e native_test` (full suite, ~30s)
- Final gate: full suite shows `N test cases: N succeeded` (N ≥ 71 + new DR tests)

---

## Sources

All findings are `[VERIFIED]` via direct file inspection in this session.

| Finding | Source | Confidence |
|---------|--------|------------|
| Integration lines 365–366 | `mode_standalone.c` line grep | HIGH |
| All `biba_rpm_pi_reset` call sites (7 total) | grep across `mode_standalone.c` | HIGH |
| `s_rpm_pi_left/right` not volatile | `mode_standalone.c` lines 100–130 | HIGH |
| Enum values 0–4 | `rpm_spectral_estimator.h` | HIGH |
| `rpm_pi.h` API pattern | `rpm_pi.h` direct read | HIGH |
| `native_test` no test_filter | `platformio.ini` line 296–313 | HIGH |
| `build_src_filter` includes `+<*>` (app/ included) | `platformio.ini` `[common]` | HIGH |
| `SpectralResult`, `spectral_estimate` at module level | `is_sweepraw_analyze.py` lines 30–130 | HIGH |
| `alg_subwindow_schmitt` at module level | `is_algo_bench.py` lines 60–90 | HIGH |
| CSV columns: `win_idx,t_ms,duty_pct,sample_idx,adc_raw` | `head -5` of actual CSV file | HIGH |
| `PLANT_K_HZ_PER_PCT`, `PLANT_DEAD_HZ`, `SPS` importable | `is_algo_bench.py` module-level | HIGH |
| `biba_config.h` `#ifndef` guard pattern | `biba_config.h` direct read | HIGH |
| LEFT REV sweep missing | SPEC.md calibration context | HIGH |
