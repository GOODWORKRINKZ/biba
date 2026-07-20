# Phase 11: IS-Pin Load & Stall Detection — Research

**Researched:** 2026-05-26
**Domain:** Embedded C (RP2040), Python signal analysis, serial protocol extension
**Confidence:** HIGH — all key claims verified against source files and live data

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-A1:** Load gate = two-step in Phase 11:
1. Python sim (`is_load_detector_research.py`) validates thresholds on softhold dataset.
2. Firmware: `BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD = 7`; gate inside estimator OR post-check in `mode_standalone.c`.

**D-A2:** Gate condition: `mean_IS_channel / mean_IS_other > LOAD_RATIO_THRESH AND quality < LOAD_QUALITY_MAX` → `valid=false`, `invalid_reason=HIGH_LOAD`.

**D-A3:** Fallback absolute gate: `mean_IS > LOAD_ABS_THRESH_ADC` when both channels are loaded. Both constants in `biba_config.h`.

**D-A4:** `LOAD_RATIO_THRESH` and `LOAD_QUALITY_MAX` are `biba_config.h` constants.

**D-B1:** Add `vbat=<raw> ibat=<raw>` to `SWEEPRAW2_WIN` header. One `biba_hal_adc_sample()` call each before IS window starts.

**D-B2:** Floating pin noise is acceptable — no sentinel value needed.

**D-B3:** Python parser: adds `vbat_raw` and `ibat_raw` CSV columns.

**D-B4:** Old firmware (no vbat/ibat fields) → `NaN` backfill.

**D-C1:** Analyze softhold dataset: DC_L vs DC_R scatter + Pearson-r.

**D-C2:** If |r| > 0.3 → new controlled capture + sag coefficient `k_sag`.

**D-C3:** Compensation formula research in Python only; firmware deferred to Phase 12.

**D-D1:** Throttle vs load disambiguation: Phase 11 scope = research + ADR only.

**D-D2:** Hypothesis: throttle↑ → d_freq>0 AND d_DC>0; load↑ → d_freq<0 AND d_DC>0; stall → d_freq→0 AND d_DC>>0.

**D-D3:** Research script `is_load_disambiguate.py` → (Δfreq, ΔDC) scatter + decision boundary.

**D-D4:** Output: `11-LOAD-DISAMBIGUATE-ADR.md`.

### Agent's Discretion

Not specified in CONTEXT.md — all major decisions are locked.

### Deferred Ideas (OUT OF SCOPE)

- VBAT/IBAT sensor calibration (sensor not yet installed)
- Battery sag compensation firmware (Phase 12)
- Throttle-vs-load firmware rule (Phase 12+)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID      | Description | Research Support |
|---------|-------------|------------------|
| LOAD-01 | IS-pin DC ratio gate: invalidate win3 and win18 (stall false-positives) without rejecting win14 (light-load valid) | Verified: RATIO=1.5, QMAX=10.0 classify all known windows correctly (§1.4) |
| LOAD-02 | VBAT/IBAT raw ADC columns in SWEEPRAW captures for battery-sag characterisation | Protocol extension design in §2; biba_hal_adc_sample(ch=2/3) available (§2.3) |
| LOAD-03 | Research throttle-vs-load disambiguation from inter-window current+frequency gradients | Data available in softhold CSV; Python-only ADR in Phase 11 (§4, §5) |
</phase_requirements>

---

## Summary

Phase 11 adds a DC-level load gate to the Goertzel spectral RPM estimator to eliminate false-positive valid readings during motor stall or heavy load. The softhold dataset (60 windows, TRAP 50%, 6 s period) contains two confirmed false positives (win3: DC_L=2588 but quality=3.7; win18: DC_L=3586, quality=9.4) and one true valid under light load (win14: DC_L=1139, quality=11.1). Threshold analysis on live data confirms that `LOAD_RATIO_THRESH=1.5` and `LOAD_QUALITY_MAX=10.0` cleanly separate all cases.

The critical architectural finding is that `biba_rpm_spectral_estimate()` computes `mean` internally as a local variable — it is NOT exposed in `biba_rpm_spectral_result_t`. The ratio gate (`mean_L/mean_R`) requires both channel means simultaneously, which means the gate is a **post-processing step in `mode_standalone.c::on_adc_pair_done()`** where both buffers (`s_adc_left_buf`, `s_adc_right_buf`) are available. The `mean_adc` field must either be added to the result struct, or computed again in the post-check.

Battery sag cross-talk is confirmed strong: Pearson-r = **0.890** (p=1.9e-21) between DC_L and DC_R across all 60 windows — well above the |r|>0.3 trigger for Phase D-C2 controlled capture.

**Primary recommendation:** Add `float mean_adc` to `biba_rpm_spectral_result_t`; implement ratio+absolute gate as `biba_rpm_spectral_apply_load_gate(result_l, result_r)` in `rpm_spectral_estimator.c`; call it in `mode_standalone.c::on_adc_pair_done()` after both estimates are computed.

---

## 1. Load Detector: Current API & Integration Point

### 1.1 Estimator Signature (VERIFIED)

```c
// firmware/src/app/rpm_spectral_estimator.h
biba_rpm_spectral_result_t biba_rpm_spectral_estimate(
    const uint16_t *buf,   // 12-bit ADC buffer
    uint16_t n,            // sample count (min 64)
    uint32_t sps,          // sample rate (e.g. 10000)
    float target_hz,       // plant model estimate
    float hint_hz          // Phase 10 dual-window hint (0.0f = disabled)
);
```

Result struct [VERIFIED: rpm_spectral_estimator.h]:
```c
typedef struct {
    float freq_hz;
    float candidate_hz;
    float quality;
    float peak_amp_lsb;
    float second_amp_lsb;
    biba_rpm_spectral_invalid_reason_t invalid_reason;
    bool valid;
} biba_rpm_spectral_result_t;
```

**`mean_adc` is NOT in the result struct.** The DC mean is computed as a local variable inside the function:
```c
float sum = 0.0f;
for (uint16_t i = 0; i < n; ++i) sum += (float)buf[i];
float mean = sum / (float)n;
```

### 1.2 Existing Invalid Reason Enum (VERIFIED)

```c
typedef enum {
    BIBA_RPM_SPECTRAL_INVALID_NONE = 0,
    BIBA_RPM_SPECTRAL_INVALID_TARGET_LOW = 1,
    BIBA_RPM_SPECTRAL_INVALID_NO_BAND = 2,
    BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW = 3,
    BIBA_RPM_SPECTRAL_INVALID_QUALITY_LOW = 4,    // NOTE: currently unused — quality low still returns valid=true
    BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED = 5,   // DR fallback
    BIBA_RPM_SPECTRAL_HINT_MEASURED = 6,           // hint window beat plant window
    /* NEW: */ BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD = 7,
} biba_rpm_spectral_invalid_reason_t;
```

### 1.3 Best Integration Point (VERIFIED)

`firmware/src/modes/mode_standalone.c::on_adc_pair_done()` (ISR callback, lines 355–430) is the correct place for the **ratio gate post-check**:

```c
// Lines 372–378 — both results are computed here
biba_rpm_spectral_result_t spec_left  = biba_rpm_spectral_estimate(
    s_adc_left_buf, samples_per_channel, STANDALONE_RPM_WHEEL_SPS,
    s_meas_target_hz_left, s_hint_hz_left);
biba_rpm_spectral_result_t spec_right = biba_rpm_spectral_estimate(
    s_adc_right_buf, samples_per_channel, STANDALONE_RPM_WHEEL_SPS,
    s_meas_target_hz_right, s_hint_hz_right);
// ← INSERT LOAD GATE POST-CHECK HERE before DR update
```

Both `s_adc_left_buf` and `s_adc_right_buf` are in scope. Both spec results are available. The existing hint feedback guard checks `spec_left.invalid_reason == BIBA_RPM_SPECTRAL_INVALID_NONE` — the new `HIGH_LOAD=7` reason will correctly suppress hint feedback automatically (existing guard already blocks any reason ≠ NONE).

### 1.4 Threshold Verification (VERIFIED against softhold data)

Live computation on `sweepraw_TRAP_amp50_per6000_n60_20260526-135642_softhold_{left,right}.csv`:

| win | DC_L  | DC_R  | ratio | quality | gate(R=1.5,Q=10) | expected |
|-----|-------|-------|-------|---------|-------------------|----------|
|   3 | 2588  | 1383  | 1.87  |   3.7   | **True**          | REJECT ✓ |
|  14 | 1139  |  860  | 1.33  |  11.1   | False             | KEEP   ✓ |
|  18 | 3586  | 1503  | 2.39  |   9.4   | **True**          | REJECT ✓ |
|  19 | 4095  | 1207  | 3.39  |   0.0   | already invalid   | N/A    ✓ |
|   5 |  676  |  864  | 0.78  |  27.5   | False             | KEEP   ✓ |

`LOAD_RATIO_THRESH = 1.5` and `LOAD_QUALITY_MAX = 10.0` correctly classify all known windows.

### 1.5 Recommended Implementation Design

**Option A (recommended):** Add `float mean_adc` to `biba_rpm_spectral_result_t`; add new function:

```c
// rpm_spectral_estimator.h — new declaration
void biba_rpm_spectral_apply_load_gate(
    biba_rpm_spectral_result_t *primary,
    float primary_mean_adc,
    float other_mean_adc);
```

Call sequence in `mode_standalone.c`:
1. `spec_left = biba_rpm_spectral_estimate(s_adc_left_buf, ...)`  — now also returns `mean_adc`
2. `spec_right = biba_rpm_spectral_estimate(s_adc_right_buf, ...)`
3. `biba_rpm_spectral_apply_load_gate(&spec_left,  spec_left.mean_adc,  spec_right.mean_adc)`
4. `biba_rpm_spectral_apply_load_gate(&spec_right, spec_right.mean_adc, spec_left.mean_adc)`

This keeps all gate logic in `rpm_spectral_estimator.c` where it is **unit-testable** from `test_rpm_spectral_estimator/test_main.c`.

**Option B (minimal):** Post-check entirely in `mode_standalone.c`, compute means inline:
```c
float mean_l = 0.0f;
for (uint16_t i = 0; i < samples_per_channel; ++i) mean_l += s_adc_left_buf[i];
mean_l /= samples_per_channel;
// ... same for right
// then apply gate logic inline
```
This avoids touching the result struct but duplicates mean computation and is harder to unit-test.

The planner chooses between A and B. Option A is recommended for testability.

---

## 2. SWEEPRAW Protocol: Current Format & Extension Points

### 2.1 Current SWEEPRAW2_WIN Format (VERIFIED)

The `cmd_sweepraw_both()` function (lines 1240–1310, `firmware/src/poc/is_rpm_poc_main.cpp`) emits **two `SWEEPRAW2_WIN` lines per window** — one for L channel, one for R channel:

```c
// Line 1293
Serial.printf("SWEEPRAW2_WIN %lu %lu %.1f L\n",
              (unsigned long)w, (unsigned long)t_now, duty * 100.0f);
_print_win(s_buf, RPMRUN_N_SAMPLES);
// Line 1296
Serial.printf("SWEEPRAW2_WIN %lu %lu %.1f R\n",
              (unsigned long)w, (unsigned long)t_now, duty * 100.0f);
_print_win(s_win_r, RPMRUN_N_SAMPLES);
```

**Current positional format:**
```
SWEEPRAW2_WIN <win_idx>  <t_ms>  <duty_pct>  <L|R>
              parts[1]   parts[2] parts[3]    parts[4]
```

Example:
```
SWEEPRAW2_WIN 3 307 50.0 L
<1024 comma-separated values>
SWEEPRAW2_WIN 3 307 50.0 R
<1024 comma-separated values>
```

### 2.2 Python Parser Current Logic (VERIFIED)

`scripts/is_poc_sweepraw.py::_parse_both_windows()` (lines ~100–125):

```python
if line.startswith("SWEEPRAW2_WIN"):
    parts = line.split()
    current_chan = parts[4] if len(parts) >= 5 else "L"
    current_meta = {"idx": int(parts[1]), "t_ms": int(parts[2]),
                    "duty": float(parts[3])}
```

`_write_csv()` (line ~130) writes: `win_idx, t_ms, duty_pct, sample_idx, adc_raw`.

**Confirmed from live file:**
```
win_idx,t_ms,duty_pct,sample_idx,adc_raw
0,0,0.00,0,22
...
```

### 2.3 ADC Availability for VBAT/IBAT (VERIFIED from CONTEXT.md)

```
GP26=ADC0=IS_RIGHT (BIBA_ADC_CHAN_IS_RIGHT=1)
GP27=ADC1=IS_LEFT  (BIBA_ADC_CHAN_IS_LEFT=0)
GP28=ADC2=VBAT     (BIBA_ADC_CHAN_VBAT=2)
GP29=ADC3=IBAT     (BIBA_ADC_CHAN_IBAT=3)
```

All 4 pins are already `adc_gpio_init()`'d in `biba_hal_rp2040.c:149`. `biba_hal_adc_sample(ch)` returns `uint16_t` (12-bit, 0–4095).

### 2.4 Extension Design

**OPEN QUESTION for planner:** CONTEXT D-B1 describes `SWEEPRAW2_WIN win=N n=1024 dc_l=X dc_r=Y vbat=<raw> ibat=<raw>` — a key=value format with both channels combined. The CURRENT protocol emits two separate L/R headers per window. The research recommends the minimal-change approach:

**Recommended: Extend L header only (sampled once per window pair)**

```c
// Sample vbat/ibat once before IS capture loop
uint16_t vbat_raw = biba_hal_adc_sample(BIBA_ADC_CHAN_VBAT);
uint16_t ibat_raw = biba_hal_adc_sample(BIBA_ADC_CHAN_IBAT);
// ... IS_LEFT capture ...
// Print L WIN header with 2 extra positional fields
Serial.printf("SWEEPRAW2_WIN %lu %lu %.1f L %u %u\n",
              (unsigned long)w, (unsigned long)t_now,
              duty * 100.0f, (unsigned)vbat_raw, (unsigned)ibat_raw);
```

New positional format for L headers:
```
SWEEPRAW2_WIN <idx>  <t_ms>  <duty>  L  <vbat_raw>  <ibat_raw>
              [1]    [2]     [3]    [4]  [5]         [6]
```

R headers remain unchanged (parts[4]='R', only 5 tokens → Python detects `len(parts) < 7` and skips vbat/ibat extraction).

**Parser extension:**
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
        current_meta["vbat_raw"] = float("nan")
        current_meta["ibat_raw"] = float("nan")
```

**CSV columns (extended):**
```
win_idx, t_ms, duty_pct, vbat_raw, ibat_raw, sample_idx, adc_raw
```

`vbat_raw`/`ibat_raw` are identical for all 1024 rows of the same window (one sample per window). `NaN` for R-channel rows or old firmware.

### 2.5 SWEEPRAW_START Header (no change needed)

The `SWEEPRAW2_START` header already contains `bl_L` and `bl_R` baseline means. No change required.

---

## 3. Python Research Scripts: Existing Patterns

### 3.1 Analysis Script Pattern (VERIFIED: `scripts/is_sweepraw_analyze.py`)

All `is_*.py` scripts follow the pattern:
- Import from `is_algo_bench.py` for algorithm constants
- Use `pandas` + `numpy` for per-window aggregation
- Use `matplotlib` for plots saved to `scripts/artifacts/`
- Print summary tables to stdout
- Accept `--help` for argparse usage

The `spectral_estimate()` Python port in `is_sweepraw_analyze.py` mirrors `biba_rpm_spectral_estimate()` exactly (same `_SPEC_MIN_HZ`, `_SPEC_ABS_BAND_HZ`, etc.) — the research script `is_load_detector_research.py` should import/replicate this pattern.

### 3.2 CSV Columns (VERIFIED from live file)

Current softhold CSV: `['win_idx', 't_ms', 'duty_pct', 'sample_idx', 'adc_raw']`

Per-window DC mean pattern (standard across all scripts):
```python
dc_by_win = df.groupby('win_idx')['adc_raw'].mean()
```

### 3.3 Available Libraries (VERIFIED: live analysis ran successfully)

- `pandas` — available
- `numpy` — available
- `scipy.stats.pearsonr` — available
- `matplotlib` — available (Agg backend for headless)

---

## 4. Battery Sag: Data & Analysis Results

### 4.1 Cross-Talk Correlation (VERIFIED — computed live)

Pearson-r between DC_L and DC_R across all 60 windows of softhold dataset:
**r = 0.890, p = 1.9e-21**

This exceeds |r| > 0.3 threshold specified in D-C2. Phase 11 **must** plan a controlled VBAT capture (one motor free, one stalled).

### 4.2 Sample Cross-Talk Evidence

During left-motor load events:
- win3: DC_L=2588, DC_R=1383 (right also elevated vs baseline of ~860 at equal load)
- win18: DC_L=3586, DC_R=1503
- win23: DC_L=4082, DC_R=1496

The right channel rises ~60% of the left's rise → shared VBAT bus sag coupling.

### 4.3 Sag Coefficient Estimation

Using win5 as left-free baseline (DC_L=676) and win14 as comparable right reference:
```
k_sag_approx = (DC_R_loaded - DC_R_base) / (DC_L_loaded - DC_L_base)
             = (1383 - 860) / (2588 - 676) = 523 / 1912 ≈ 0.27
```
This is an approximation. The controlled capture (D-C2) will measure k_sag cleanly.

### 4.4 Delta-DC Data (useful for disambiguation research)

Selected transitions showing DC ramp pattern:
```
win1→win2: d_DC_L=+2530  (duty 19→38% — accelerating into stall)
win2→win3: d_DC_L= -532  (stall entering OCP plateau)
win12→win13: d_DC_L=+949 (reverse stall building)
win17→win18: d_DC_L=+2753 (stall onset in reverse hold)
win18→win19: d_DC_L= +509 (OCP latch final step)
```

---

## 5. Wave Plan & Dependencies

### 5.1 Dependency Map

```
softhold CSV (already captured)
        │
        ├──► Wave 1: is_load_detector_research.py
        │         Finds RATIO_THRESH, QUALITY_MAX
        │         Output: threshold constants + plots
        │         [PYTHON ONLY, no firmware deps]
        │
        ├──► Wave 2a: is_sag_research.py (battery sag scatter + Pearson-r)
        │         [PYTHON ONLY]
        │
        ├──► Wave 2b: is_load_disambiguate.py (Δfreq/ΔDC scatter + ADR)
        │         [PYTHON ONLY, needs spectral_estimate() from is_sweepraw_analyze.py]
        │
        └──► Wave 2c: Firmware SWEEPRAW2_WIN VBAT/IBAT extension
                  is_rpm_poc_main.cpp + is_poc_sweepraw.py updates
                  [FIRMWARE+PYTHON, parallel with 2a/2b]

Wave 1 output (RATIO_THRESH, QUALITY_MAX)
        │
        └──► Wave 3: Firmware load gate implementation
                  • Add HIGH_LOAD=7 to enum (rpm_spectral_estimator.h)
                  • Add mean_adc to result struct (if Option A)
                  • Add biba_rpm_spectral_apply_load_gate() (rpm_spectral_estimator.c)
                  • Add LOAD_RATIO_THRESH, LOAD_QUALITY_MAX, LOAD_ABS_THRESH_ADC to biba_config.h
                  • Update on_adc_pair_done() in mode_standalone.c
                  • Unity tests: ≥4 new tests in test_rpm_spectral_estimator/test_main.c
                  • pio test -e native_test: all 84+N tests green
```

### 5.2 Wave 1 Parallelization

| Wave | Plans (can run in parallel) | Dependencies |
|------|----------------------------|--------------|
| 1    | P1: Python load detector research | softhold CSV |
| 2    | P2a: Python sag scatter + Pearson-r report | Wave 1 not needed |
|      | P2b: Python disambiguate ADR | Wave 1 not needed |
|      | P2c: Firmware+Python SWEEPRAW extension | Wave 1 not needed |
| 3    | P3: Firmware load gate + Unity tests | Wave 1 output |

Wave 2 plans (2a, 2b, 2c) are independent and can run in parallel. Wave 3 blocks on Wave 1 for threshold values.

### 5.3 Hidden Dependencies

1. **Wave 3 blocks on Wave 1** — firmware constants `LOAD_RATIO_THRESH` and `LOAD_QUALITY_MAX` must come from Python research, not be guessed. If the plan skips this gate, it risks using wrong thresholds in firmware tests.

2. **Option A requires struct change** — adding `mean_adc` to `biba_rpm_spectral_result_t` changes the struct definition. All existing 12 tests in `test_rpm_spectral_estimator` will still compile (they don't check `mean_adc`), but any code that does `biba_rpm_spectral_result_t result = {0}` in tests needs to remain valid (zero-init is fine for added float field).

3. **mode_standalone.c hint guard** — the existing check `spec_left.invalid_reason == BIBA_RPM_SPECTRAL_INVALID_NONE` at line ~384 will automatically exclude HIGH_LOAD results from hint feedback. No additional guard needed.

4. **DR module** — `biba_rpm_dr_update()` receives `spec_left`/`spec_right` after spectral estimation. If the load gate sets `valid=false`, DR will activate its fallback. This is correct behavior (stalled motor should use DR or zero). No changes to `rpm_dr.c` needed.

5. **VBAT/IBAT sensor not installed** — values will be floating-pin noise (0–4095 random). This is expected per D-B2; columns will be present but not usable until sensor is connected. No calibration code needed in Phase 11.

---

## 6. Validation Architecture

> `nyquist_validation: false` in config.json — Validation Architecture section **SKIPPED** per config.

Unit and integration test obligations from spec_lock (AC-7, AC-8):

| Test type | What to test | How |
|-----------|-------------|-----|
| Unity unit | HIGH_LOAD=7 enum added, no aliasing | `TEST_ASSERT_EQUAL(7, BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD)` |
| Unity unit | High DC + low quality window → invalid=HIGH_LOAD | `fill_sine()` with dc=2588, amp=100 (quality ~3); apply load gate; assert invalid_reason=HIGH_LOAD |
| Unity unit | Light load window → NOT rejected | `fill_sine()` with dc=1139, amp=200 (quality ~11); apply load gate; assert valid=True |
| Unity unit | Absolute threshold: single-channel high DC → HIGH_LOAD even when other_mean=0 | Use large primary_mean_adc > ABS_THRESH; assert rejected |
| Integration | `pio test -e native_test` green | All existing 84 + ≥4 new tests pass |
| Python | `is_load_detector_research.py` reports win3=HIGH_LOAD, win18=HIGH_LOAD, win14=valid | AC-1 |
| Python | `is_sag_research.py` reports Pearson-r=0.890 (or close) | AC-5 |
| Python | `is_load_disambiguate.py` produces scatter + `11-LOAD-DISAMBIGUATE-ADR.md` | AC-6 |
| Hardware | CSV from new firmware includes non-NaN vbat_raw/ibat_raw columns | AC-4 |

### Unity Test Fixture Pattern (VERIFIED from test_rpm_spectral_estimator/test_main.c)

```c
// Existing helper — use dc= to control DC mean (for load gate testing)
static void fill_sine(uint16_t *buf, uint16_t n, uint32_t sps,
                      float freq_hz, uint16_t dc, uint16_t amp)
{
    for (uint16_t i = 0; i < n; ++i) {
        float t = (float)i / (float)sps;
        float v = (float)dc + sinf(2.0f * M_PI * freq_hz * t) * (float)amp;
        // ... clamp to 0–4095
    }
}
```

For Option A (recommended), new tests will:
1. Create buffer with `fill_sine(buf, 1024, 10000, 300.0f, 2588, 100)` → high DC, low AC amplitude → quality ~3.7
2. Call `biba_rpm_spectral_estimate(buf, ...)` → get `result.mean_adc ≈ 2588`
3. Create other-channel mock: `other_mean ≈ 1383` (from softhold win3 data)
4. Call `biba_rpm_spectral_apply_load_gate(&result, 2588.0f, 1383.0f)`
5. Assert `result.valid == false && result.invalid_reason == BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD`

---

## Open Questions

1. **Gate location — Option A vs B?**
   - What we know: ratio gate requires both channel means; Option A (new function) is unit-testable; Option B (inline in mode_standalone.c) is minimal
   - What's unclear: whether adding `mean_adc` to result struct is acceptable API surface
   - Recommendation: Option A (expose mean_adc, new `apply_load_gate()` function). If planner prefers minimal API change, Option B with helper function in mode_standalone.c.

2. **SWEEPRAW2_WIN format: extend L header or both headers?**
   - What we know: VBAT/IBAT is sampled once per window (not per channel); adding to L header only is simplest; R-header unchanged
   - What's unclear: CONTEXT D-B1 description mentions `dc_l=X dc_r=Y` in same header, suggesting a future single-header-per-window design
   - Recommendation: Keep two-header design; add `vbat_raw ibat_raw` positional fields to L header only (parts[5], parts[6]). Parser already handles `len(parts) >= 5` for channel detection.

3. **Absolute threshold value?**
   - What we know: win3 DC_L=2588 should trigger; win14 DC_L=1139 should not
   - Recommendation: `LOAD_ABS_THRESH_ADC = 2000` (midpoint) as starting default; Python research confirms

---

## Sources

### Primary (HIGH confidence — VERIFIED)
- `firmware/src/app/rpm_spectral_estimator.h` — exact struct and enum values, read directly
- `firmware/src/app/rpm_spectral_estimator.c` — mean computation pattern, local variable scope
- `firmware/src/poc/is_rpm_poc_main.cpp:1240–1310` — exact SWEEPRAW2_WIN printf format strings
- `scripts/is_poc_sweepraw.py:_parse_both_windows()` — exact parser field extraction logic
- `scripts/artifacts/is-sweepraw/sweepraw_TRAP_amp50_per6000_n60_20260526-135642_softhold_*.csv` — live data, threshold verification (Pearson-r=0.890 computed live)
- `firmware/src/modes/mode_standalone.c:355–430` — integration point for post-check
- `firmware/test/test_rpm_spectral_estimator/test_main.c` — Unity fixture pattern (12 existing tests confirmed)

### Secondary (MEDIUM confidence)
- `firmware/include/biba_config.h` — `#ifndef`-guarded constant pattern for new constants

---

## Metadata

**Confidence breakdown:**
- Load gate API: HIGH — read source; mean is local var, confirmed no exposure in result struct
- Threshold values: HIGH — computed from live softhold dataset; all 4 known windows classified correctly
- SWEEPRAW extension: HIGH — exact format from printf strings; parser field positions from source
- Battery sag correlation: HIGH — Pearson-r=0.890 computed live from actual CSV
- Wave dependencies: HIGH — traced code paths in mode_standalone.c and firmware test suite

**Research date:** 2026-05-26
**Valid until:** 2026-06-25 (stable firmware, 30-day estimate)
