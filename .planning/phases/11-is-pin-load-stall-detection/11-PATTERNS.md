# Phase 11: IS-Pin Load & Stall Detection — Pattern Map

**Mapped:** 2026-05-26
**Files analyzed:** 8 (3 new Python, 1 ADR doc, 2 firmware headers/c, 1 firmware cpp, 1 firmware test)
**Analogs found:** 7 / 8 (ADR has no code analog)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `scripts/is_load_detector_research.py` | utility/research | batch transform | `scripts/is_hint_research.py` | exact |
| `scripts/is_batsag_research.py` | utility/research | batch transform | `scripts/is_hint_research.py` | exact |
| `scripts/is_load_disambiguate.py` | utility/research | batch transform | `scripts/is_sweepraw_analyze.py` | role-match |
| `.planning/phases/11-is-pin-load-stall-detection/11-LOAD-DISAMBIGUATE-ADR.md` | docs | — | none | none |
| `firmware/src/app/rpm_spectral_estimator.h` | model/config | — | self (existing struct/enum) | exact |
| `firmware/src/app/rpm_spectral_estimator.c` | service | request-response | self (existing function) | exact |
| `firmware/src/poc/is_rpm_poc_main.cpp` | utility/poc | request-response | self (existing cmd_sweepraw_both) | exact |
| `firmware/test/test_rpm_spectral_estimator/test_main.c` | test | CRUD | `firmware/test/test_rpm_pi/test_main.c` | exact |

---

## Pattern Assignments

### `scripts/is_load_detector_research.py` (utility/research, batch transform)

**Analog:** `scripts/is_hint_research.py`

**Imports pattern** (lines 1–32):
```python
#!/usr/bin/env python3
"""<one-line description>"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from is_sweepraw_analyze import (  # noqa: E402
    spectral_estimate,
    spectral_estimate_hint,
    load_sweepraw,
    expected_hz,
)
from is_algo_bench import SPS  # noqa: E402

ARTIFACTS_DIR = _SCRIPTS_DIR / "artifacts" / "is-sweepraw"
OUT_PNG = _SCRIPTS_DIR / "artifacts" / "is_load_detector_research.png"
```

**Per-window aggregation pattern** (mirrors groupby pattern used across all is_*.py scripts):
```python
# Per-window DC mean — standard pattern verified in is_sweepraw_analyze.py context
dc_by_win = df.groupby('win_idx')['adc_raw'].mean()
# Paired L/R: merge left and right DataFrames on win_idx
merged = df_l.merge(df_r, on='win_idx', suffixes=('_l', '_r'))
```

**Gate simulation pattern** (mirrors run_simulation() in is_hint_research.py lines 80–122):
```python
def apply_load_gate(dc_primary: float, dc_other: float,
                    quality: float,
                    ratio_thresh: float, quality_max: float,
                    abs_thresh: float) -> bool:
    """Return True if the window should be REJECTED (HIGH_LOAD)."""
    ratio = dc_primary / (dc_other + 1e-6)
    if ratio > ratio_thresh and quality < quality_max:
        return True
    if dc_primary > abs_thresh:
        return True
    return False
```

**Output/plot save pattern** (lines 140–160 in is_hint_research.py):
```python
fig, axes = plt.subplots(2, 1, figsize=(12, 8))
# ... fill axes ...
fig.tight_layout()
fig.savefig(str(OUT_PNG), dpi=140)
print(f"saved: {OUT_PNG}")
```

**Entry point pattern** (lines 135–175 in is_hint_research.py):
```python
def main() -> None:
    csv_files = sorted(ARTIFACTS_DIR.glob("sweepraw_*softhold*.csv"))
    if not csv_files:
        print(f"ERROR: no CSV files found in {ARTIFACTS_DIR}", file=sys.stderr)
        sys.exit(1)
    # ... run simulation, print table, save plot ...

if __name__ == "__main__":
    main()
```

---

### `scripts/is_batsag_research.py` (utility/research, batch transform)

**Analog:** `scripts/is_hint_research.py`

Same imports and structure as `is_load_detector_research.py` above.

**Key additional pattern — scipy.stats for Pearson-r** (standard across scipy usage):
```python
from scipy.stats import pearsonr

r, p = pearsonr(dc_l_series, dc_r_series)
print(f"Pearson-r = {r:.3f}  p = {p:.2e}")
```

**Scatter plot pattern** (matplotlib, consistent with project artifacts):
```python
fig, ax = plt.subplots(figsize=(8, 6))
ax.scatter(dc_r_vals, dc_l_vals, alpha=0.6, s=30)
ax.set_xlabel("DC_R (ADC counts)")
ax.set_ylabel("DC_L (ADC counts)")
ax.set_title(f"Battery sag cross-talk  r={r:.3f}  p={p:.2e}")
fig.tight_layout()
fig.savefig(str(OUT_PNG), dpi=140)
print(f"saved: {OUT_PNG}")
```

---

### `scripts/is_load_disambiguate.py` (utility/research, batch transform)

**Analog:** `scripts/is_sweepraw_analyze.py`

**Imports pattern** (same as above research scripts):
```python
#!/usr/bin/env python3
"""Throttle vs load disambiguation: inter-window (Δfreq, ΔDC) gradients."""
from __future__ import annotations
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))
from is_sweepraw_analyze import spectral_estimate  # noqa: E402
from is_algo_bench import SPS                      # noqa: E402
```

**Inter-window delta computation pattern** (uses per-window aggregation then diff()):
```python
# Build per-window summary from both L and R CSVs
dc_l = df_l.groupby('win_idx')['adc_raw'].mean()
# Run spectral_estimate per window, collect freq_hz
freqs_l = []
for win_idx, grp in df_l.groupby('win_idx'):
    buf = grp['adc_raw'].values.astype(np.float32)
    r = spectral_estimate(buf, SPS, expected_hz(grp['duty_pct'].iloc[0]))
    freqs_l.append({'win_idx': win_idx, 'freq_hz': r.freq_hz, 'valid': r.valid})
summary = pd.DataFrame(freqs_l).set_index('win_idx')
summary['dc_l'] = dc_l
summary['d_freq'] = summary['freq_hz'].diff()
summary['d_dc']   = summary['dc_l'].diff()
```

**Classification scatter pattern:**
```python
fig, ax = plt.subplots(figsize=(8, 6))
colors = {'throttle_up': 'green', 'load_up': 'red', 'stall': 'black', 'other': 'gray'}
for label, grp in summary.groupby('class'):
    ax.scatter(grp['d_dc'], grp['d_freq'], label=label,
               color=colors.get(label, 'blue'), alpha=0.7)
ax.axhline(0, color='k', lw=0.5)
ax.axvline(0, color='k', lw=0.5)
ax.set_xlabel("ΔDC (ADC counts)")
ax.set_ylabel("Δfreq_hz")
```

---

### `firmware/src/app/rpm_spectral_estimator.h` (model/config, modified)

**Analog:** self — existing file [firmware/src/app/rpm_spectral_estimator.h](firmware/src/app/rpm_spectral_estimator.h)

**Existing enum to extend** (lines 18–27 of file):
```c
typedef enum {
    BIBA_RPM_SPECTRAL_INVALID_NONE = 0,
    BIBA_RPM_SPECTRAL_INVALID_TARGET_LOW = 1,
    BIBA_RPM_SPECTRAL_INVALID_NO_BAND = 2,
    BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW = 3,
    BIBA_RPM_SPECTRAL_INVALID_QUALITY_LOW = 4,
    BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED = 5,   /* DR fallback active */
    BIBA_RPM_SPECTRAL_HINT_MEASURED = 6,           /* hint window was better than plant window */
    /* NEW → */ BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD = 7,
} biba_rpm_spectral_invalid_reason_t;
```

**Existing result struct to extend** (lines 29–37 of file):
```c
typedef struct {
    float freq_hz;
    float candidate_hz;
    float quality;
    float peak_amp_lsb;
    float second_amp_lsb;
    biba_rpm_spectral_invalid_reason_t invalid_reason;
    bool valid;
    /* NEW → */ float mean_adc;   /* DC mean of ADC buffer; used by load gate */
} biba_rpm_spectral_result_t;
```

**New function declaration to add** (after the existing `biba_rpm_spectral_estimate` declaration):
```c
/* Load gate: mutates *primary in-place; sets valid=false and
 * invalid_reason=BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD when the ratio
 * primary_mean / other_mean exceeds LOAD_RATIO_THRESH and quality is
 * below LOAD_QUALITY_MAX, or when primary_mean > LOAD_ABS_THRESH_ADC. */
void biba_rpm_spectral_apply_load_gate(
    biba_rpm_spectral_result_t *primary,
    float primary_mean_adc,
    float other_mean_adc);
```

**Constants belong in `biba_config.h`** — copy the `#ifndef` guard pattern already used there (lines 33–60 of biba_config.h):
```c
/* --- IS-pin load gate thresholds --------------------------------------- */
#ifndef BIBA_RPM_LOAD_RATIO_THRESH
#  define BIBA_RPM_LOAD_RATIO_THRESH    1.5f   /* primary_mean / other_mean */
#endif
#ifndef BIBA_RPM_LOAD_QUALITY_MAX
#  define BIBA_RPM_LOAD_QUALITY_MAX    10.0f   /* quality below this → gate active */
#endif
#ifndef BIBA_RPM_LOAD_ABS_THRESH_ADC
#  define BIBA_RPM_LOAD_ABS_THRESH_ADC 3500.0f /* absolute IS threshold (OCP approach) */
#endif
```

---

### `firmware/src/app/rpm_spectral_estimator.c` (service, request-response, modified)

**Analog:** self — existing file [firmware/src/app/rpm_spectral_estimator.c](firmware/src/app/rpm_spectral_estimator.c)

**Existing mean computation** (lines 72–75 of file — currently a local variable):
```c
    float sum = 0.0f;
    for (uint16_t i = 0; i < n; ++i) sum += (float)buf[i];
    float mean = sum / (float)n;
    /* ← after this phase: result.mean_adc = mean; */
```

**Existing result initialisation pattern** (lines 38–44 of file — copy for new function):
```c
biba_rpm_spectral_result_t result = {
    0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    BIBA_RPM_SPECTRAL_INVALID_NONE,
    false
};
```

**New function implementation pattern** (copy guard-and-mutate style from existing code):
```c
void biba_rpm_spectral_apply_load_gate(
    biba_rpm_spectral_result_t *primary,
    float primary_mean_adc,
    float other_mean_adc)
{
    if (!primary || !primary->valid) return;  /* only gate currently-valid results */

    float ratio = primary_mean_adc / (other_mean_adc + 1.0f);
    bool ratio_gate = (ratio > BIBA_RPM_LOAD_RATIO_THRESH)
                      && (primary->quality < BIBA_RPM_LOAD_QUALITY_MAX);
    bool abs_gate   = (primary_mean_adc > BIBA_RPM_LOAD_ABS_THRESH_ADC);

    if (ratio_gate || abs_gate) {
        primary->valid          = false;
        primary->invalid_reason = BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD;
    }
}
```

---

### `firmware/src/poc/is_rpm_poc_main.cpp` (utility/poc, modified)

**Analog:** self — existing `cmd_sweepraw_both()` in [firmware/src/poc/is_rpm_poc_main.cpp](firmware/src/poc/is_rpm_poc_main.cpp)

**Current SWEEPRAW2_WIN printf lines** (lines 1293–1298 of file):
```cpp
        Serial.printf("SWEEPRAW2_WIN %lu %lu %.1f L\n",
                      (unsigned long)w, (unsigned long)t_now, duty * 100.0f);
        _print_win(s_buf, RPMRUN_N_SAMPLES);
        Serial.printf("SWEEPRAW2_WIN %lu %lu %.1f R\n",
                      (unsigned long)w, (unsigned long)t_now, duty * 100.0f);
        _print_win(s_win_r, RPMRUN_N_SAMPLES);
```

**Pattern for VBAT/IBAT insertion** — sample once before the IS capture loop, emit on L header only:
```cpp
        /* Sample VBAT/IBAT once per window pair before IS captures.
         * Sensor not yet installed — values will be floating-pin noise.
         * D-B2: no sentinel, columns present in CSV, calibrated later. */
        uint16_t vbat_raw = biba_hal_adc_sample(BIBA_ADC_CHAN_VBAT);
        uint16_t ibat_raw = biba_hal_adc_sample(BIBA_ADC_CHAN_IBAT);
        /* ... IS_LEFT capture into s_buf ... */
        /* ... IS_RIGHT capture into s_win_r ... */
        Serial.printf("SWEEPRAW2_WIN %lu %lu %.1f L %u %u\n",
                      (unsigned long)w, (unsigned long)t_now, duty * 100.0f,
                      (unsigned)vbat_raw, (unsigned)ibat_raw);
        _print_win(s_buf, RPMRUN_N_SAMPLES);
        Serial.printf("SWEEPRAW2_WIN %lu %lu %.1f R\n",   /* R unchanged */
                      (unsigned long)w, (unsigned long)t_now, duty * 100.0f);
        _print_win(s_win_r, RPMRUN_N_SAMPLES);
```

**biba_hal_adc_sample call pattern** (verified from CONTEXT.md — same HAL used elsewhere in poc):
```cpp
uint16_t vbat_raw = biba_hal_adc_sample(BIBA_ADC_CHAN_VBAT);   /* ch=2, GP28 */
uint16_t ibat_raw = biba_hal_adc_sample(BIBA_ADC_CHAN_IBAT);   /* ch=3, GP29 */
```

---

### `scripts/is_poc_sweepraw.py` (utility, request-response, modified)

**Analog:** self — existing `_parse_both_windows()` in [scripts/is_poc_sweepraw.py](scripts/is_poc_sweepraw.py)

**Current SWEEPRAW2_WIN parser** (lines ~100–113 of file):
```python
        if line.startswith("SWEEPRAW2_WIN"):
            # SWEEPRAW2_WIN <idx> <t_ms> <duty_pct> <L|R>
            parts = line.split()
            current_chan = parts[4] if len(parts) >= 5 else "L"
            current_meta = {"idx": int(parts[1]), "t_ms": int(parts[2]),
                            "duty": float(parts[3])}
            continue
```

**Extended parser pattern** (D-B3/D-B4 — add vbat_raw/ibat_raw, NaN for R or old firmware):
```python
        if line.startswith("SWEEPRAW2_WIN"):
            parts = line.split()
            current_chan = parts[4] if len(parts) >= 5 else "L"
            current_meta = {"idx": int(parts[1]), "t_ms": int(parts[2]),
                            "duty": float(parts[3])}
            if current_chan == "L" and len(parts) >= 7:
                current_meta["vbat_raw"] = int(parts[5])
                current_meta["ibat_raw"] = int(parts[6])
            else:
                current_meta["vbat_raw"] = float("nan")   # D-B4: backfill
                current_meta["ibat_raw"] = float("nan")
            continue
```

**Current `_write_csv()` pattern** (lines ~130–137 of file):
```python
def _write_csv(path: Path, windows: list[dict]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["win_idx", "t_ms", "duty_pct", "sample_idx", "adc_raw"])
        for win in windows:
            for i, v in enumerate(win["samples"]):
                w.writerow([win["idx"], win["t_ms"], f"{win['duty']:.2f}", i, v])
```

**Extended `_write_csv()` pattern** (add vbat_raw/ibat_raw columns, same per-sample repetition):
```python
def _write_csv(path: Path, windows: list[dict]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["win_idx", "t_ms", "duty_pct", "vbat_raw", "ibat_raw",
                    "sample_idx", "adc_raw"])
        for win in windows:
            vbat = win.get("vbat_raw", float("nan"))
            ibat = win.get("ibat_raw", float("nan"))
            for i, v in enumerate(win["samples"]):
                w.writerow([win["idx"], win["t_ms"], f"{win['duty']:.2f}",
                            vbat, ibat, i, v])
```

---

### `firmware/test/test_rpm_spectral_estimator/test_main.c` (test, CRUD)

**Analog:** `firmware/test/test_rpm_pi/test_main.c`

**File-level structure** (lines 1–10 and 189–196 of analog):
```c
/* Unity tests for firmware/src/app/rpm_spectral_estimator.c */

#include <math.h>
#include <stdint.h>
#include <string.h>

#include "rpm_spectral_estimator.h"
#include "biba_config.h"
#include "biba_test_support.h"
```

**Test function style** — one function per behaviour, descriptive name, isolated setup (lines 30–45 of analog):
```c
static void test_load_gate_rejects_high_ratio_low_quality(void)
{
    /* win3 case: DC_L=2588, DC_R=1383, quality=3.7 → ratio=1.87 > 1.5, quality<10 → REJECT */
    biba_rpm_spectral_result_t r = {
        .freq_hz      = 352.4f,
        .quality      = 3.7f,
        .invalid_reason = BIBA_RPM_SPECTRAL_INVALID_NONE,
        .valid        = true,
        .mean_adc     = 2588.0f,
    };
    biba_rpm_spectral_apply_load_gate(&r, 2588.0f, 1383.0f);
    TEST_ASSERT_FALSE(r.valid);
    TEST_ASSERT_EQUAL_INT(BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD, r.invalid_reason);
}
```

**run_all / main boilerplate** (lines 179–196 of analog — copy exactly):
```c
static void run_all(void)
{
    RUN_TEST(test_load_gate_rejects_high_ratio_low_quality);
    RUN_TEST(test_load_gate_keeps_light_load);
    RUN_TEST(test_load_gate_rejects_abs_threshold);
    RUN_TEST(test_load_gate_no_effect_when_already_invalid);
}

#if defined(BIBA_TEST_STANDALONE)
BIBA_TEST_STANDALONE_MAIN(run_all)
#else
void setUp(void) {}
void tearDown(void) {}
int main(void) { UNITY_BEGIN(); run_all(); return UNITY_END(); }
#endif
```

**Test cases required** (4 cases covering decision table from RESEARCH.md §1.4):

| Test | Input | Expected |
|------|-------|----------|
| `test_load_gate_rejects_high_ratio_low_quality` | DC_L=2588, DC_R=1383, q=3.7 | valid=false, HIGH_LOAD |
| `test_load_gate_keeps_light_load` | DC_L=1139, DC_R=860, q=11.1 | valid=true unchanged |
| `test_load_gate_rejects_abs_threshold` | DC_L=3586, DC_R=1503, q=9.4 | valid=false, HIGH_LOAD (win18: ratio=2.39>1.5, q=9.4<10) |
| `test_load_gate_no_effect_when_already_invalid` | valid=false, any DC values | valid remains false, reason unchanged |

---

## Shared Patterns

### biba_config.h `#ifndef` guard for new constants
**Source:** `firmware/include/biba_config.h` (lines 33–60)
**Apply to:** New `BIBA_RPM_LOAD_*` constant definitions

```c
#ifndef BIBA_RPM_LOAD_RATIO_THRESH
#  define BIBA_RPM_LOAD_RATIO_THRESH    1.5f
#endif
#ifndef BIBA_RPM_LOAD_QUALITY_MAX
#  define BIBA_RPM_LOAD_QUALITY_MAX    10.0f
#endif
#ifndef BIBA_RPM_LOAD_ABS_THRESH_ADC
#  define BIBA_RPM_LOAD_ABS_THRESH_ADC 3500.0f
#endif
```

### Python artifacts output path
**Source:** `scripts/is_hint_research.py` (lines 34–36)
**Apply to:** All 3 new Python research scripts

```python
ARTIFACTS_DIR = _SCRIPTS_DIR / "artifacts" / "is-sweepraw"
OUT_PNG = _SCRIPTS_DIR / "artifacts" / "is_<name>_research.png"
# Save with: fig.savefig(str(OUT_PNG), dpi=140); print(f"saved: {OUT_PNG}")
```

### matplotlib Agg backend (headless-safe)
**Source:** `scripts/is_hint_research.py` (lines 10–11)
**Apply to:** All 3 new Python research scripts

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
```

### Python sys.path insert for local imports
**Source:** `scripts/is_hint_research.py` (lines 27–29)
**Apply to:** All 3 new Python research scripts

```python
_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))
```

### Firmware test — helper buffer construction
**Source:** `firmware/test/test_rpm_pi/test_main.c` (lines 13–25, `make_default_cfg` pattern)
**Apply to:** `firmware/test/test_rpm_spectral_estimator/test_main.c`

```c
/* Build a synthetic 1024-sample buffer with a known DC mean for gate tests.
 * All samples set to the same value → mean = value exactly. */
static void fill_buf_dc(uint16_t *buf, uint16_t n, uint16_t dc_val)
{
    for (uint16_t i = 0; i < n; ++i) buf[i] = dc_val;
}
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `11-LOAD-DISAMBIGUATE-ADR.md` | docs/ADR | — | ADR documents have no code analog; planner should follow the existing ADR style in `.planning/` or `docs/` |

---

## Metadata

**Analog search scope:** `scripts/`, `firmware/src/app/`, `firmware/src/poc/`, `firmware/test/`, `firmware/include/`
**Files scanned:** 8 source files read
**Pattern extraction date:** 2026-05-26
