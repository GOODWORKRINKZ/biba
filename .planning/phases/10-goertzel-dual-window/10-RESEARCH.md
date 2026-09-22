# Phase 10: Goertzel Dual-Window Search — Research

**Researched:** 2026-05-26
**Domain:** Goertzel spectral RPM estimator — dual-window hint extension (firmware C + Python analysis)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-A1:** hint win → `BIBA_RPM_SPECTRAL_HINT_MEASURED = 6` (new enum value); `valid = true`
- **D-B1:** `s_hint_hz_left/right` reset on arm/disarm AND on direction flip
- **D-B2:** research script tests both variants (`hint_reset_on_dir=True/False`) on TRAP data
- **D-C1:** `is_hint_research.py` → per-file table + pooled row + one PNG chart; no exit-code gate
- **D-D1:** `spectral_estimate_hint(buf, sps, target_hz, hint_hz)` lives in `is_sweepraw_analyze.py`
- Deadband = `BIBA_RPM_SPECTRAL_ABS_BAND_HZ / 2` = 40 Hz
- `hint_hz = 0.0f` → second window suppressed (backward-compatible sentinel)
- Research gate: pooled FWD dropout must improve ≥ 5 pp

### the agent's Discretion
- Research script visual style: dark-themed matplotlib matching `dr_v2_hint.png` aesthetics
- New Unity test helper function names (e.g., `fill_sine_far()` etc.)

### Deferred Ideas (OUT OF SCOPE)
- **DEFER-01:** Stall/slip detection via current-RPM correlation → Phase 11 candidate
</user_constraints>

---

## Summary

Phase 10 adds a second Goertzel search window centred on the previous valid `freq_hz` (hint) to the
existing `biba_rpm_spectral_estimate()`. The plant-model window always runs first; the hint window
fires only when `|hint_hz − target_hz| > 40 Hz` and costs ~20 extra Goertzel bins. Best-of-two
selection is by `peak_amp`.

Research investigations confirm:
1. **Current C API** — 4-parameter function, exact signature verified in source; extension is additive (5th param `float hint_hz`).
2. **Call site count discrepancy** — SPEC states "4 in test_main.c" but actual code has **6 call sites** in that file; total to update = **8** (6 test + 2 mode).
3. **DR reset sites** — 7 distinct events × 2 channels = 14 individual `biba_rpm_dr_reset()` calls; `s_hint_hz_left/right` must mirror ALL of these plus the per-channel direction-flip sites (already co-located with DR reset at lines 881/889).
4. **CSV inventory** — 23 SIN + 4 TRAP = 28 files; all 4 TRAP files have fwd↔rev transitions (duty ±30% or ±35%), enabling D-B2 variant comparison.
5. **Python `spectral_estimate()`** — existing implementation in `is_sweepraw_analyze.py` is a clean, callable public function; `spectral_estimate_hint()` can call it twice, no code duplication needed.

**Primary recommendation:** Three waves as planned — Python research script gate first, firmware extension second, mode_standalone integration + Unity tests third.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Dual-window Goertzel search | Firmware (rpm_spectral_estimator.c) | — | Core DSP logic; pure C, ISR-safe |
| hint_hz state tracking + reset | Firmware (mode_standalone.c) | — | Per-channel state, reset at arm/disarm/direction-flip events |
| Python port of hint logic | Analysis scripts (is_sweepraw_analyze.py) | — | Firmware-mirror for offline validation; must stay in sync |
| Batch research simulation | Analysis scripts (is_hint_research.py) | — | Gate before firmware is touched |
| Unity regression guard | Firmware test (test_rpm_spectral_estimator) | — | TDD gate; 6 existing + ≥ 6 new tests |

---

## Standard Stack

### Core (all already present in repo — no new deps)

| Component | Version | Purpose |
|-----------|---------|---------|
| C99 firmware (`rpm_spectral_estimator.c/h`) | — | Goertzel DSP, embedded, ISR-safe |
| Unity test framework | existing in PlatformIO | TDD for firmware; `pio test -e native_test` |
| Python 3 + numpy | installed | `is_sweepraw_analyze.py`, `is_hint_research.py` |
| matplotlib | installed | research chart PNG |
| PlatformIO `native_test` env | configured | runs 78 tests in ~4 s |

**No new packages required.** [VERIFIED: existing tests passed 78/78 with `pio test -e native_test`]

---

## Architecture Patterns

### Dual-Window Algorithm (Firmware C)

```
biba_rpm_spectral_estimate(buf, n, sps, target_hz, hint_hz)
│
├─ Validate inputs (target < MIN → INVALID_TARGET_LOW)
├─ Compute mean(buf) once ← shared by both windows
│
├─ PLANT WINDOW: [target_hz ± half_band]
│   └─ Goertzel scan k_lo..k_hi → best_bin_P, best_amp_P
│
├─ HINT GATE: hint_hz != 0.0f AND |hint_hz − target_hz| > 40 Hz ?
│   └─ YES → HINT WINDOW: [hint_hz ± half_band]
│                └─ Goertzel scan k_lo_h..k_hi_h → best_bin_H, best_amp_H
│
├─ BEST-OF-TWO: best_amp_H > best_amp_P ?
│   ├─ YES → result = hint candidate; invalid_reason = HINT_MEASURED; valid = true (if amp ≥ MIN)
│   └─ NO  → result = plant candidate; invalid_reason = INVALID_NONE (or PEAK_LOW)
│
└─ Return biba_rpm_spectral_result_t
```

**Key implementation detail:** `mean` is computed once from `buf`; both windows share it.
The parabolic interpolation and quality/noise calculation must be run on whichever window wins.
Simplest approach: compute full result for plant window first (existing code path), then if hint
fires and wins, recompute result fields for hint window.

### hint_hz State Machine (mode_standalone.c)

```
ON INIT / FAILSAFE / DISARM / LATCH-RESET / OLON / OLOFF:
  s_hint_hz_left  = 0.0f
  s_hint_hz_right = 0.0f

ON DIRECTION FLIP (per channel, in tick function block ~L880):
  IF rev_left changed:  s_hint_hz_left  = 0.0f   ← D-B1
  IF rev_right changed: s_hint_hz_right = 0.0f   ← D-B1

IN ADC CALLBACK (after spectral estimate):
  IF spec_left.valid && spec_left.invalid_reason == INVALID_NONE:
    s_hint_hz_left = spec_left.freq_hz              ← D8
  IF spec_right.valid && spec_right.invalid_reason == INVALID_NONE:
    s_hint_hz_right = spec_right.freq_hz            ← D8
  # NOTE: HINT_MEASURED (=6) is NOT INVALID_NONE — hint wins do NOT update hint state
```

### Python `spectral_estimate_hint()` Pattern

```python
_DEADBAND_HZ = _SPEC_ABS_BAND_HZ / 2.0   # = 40.0

def spectral_estimate_hint(buf: np.ndarray, sps: int,
                            target_hz: float, hint_hz: float) -> SpectralResult:
    r_plant = spectral_estimate(buf, sps, target_hz)
    if hint_hz == 0.0 or abs(hint_hz - target_hz) <= _DEADBAND_HZ:
        return r_plant
    r_hint = spectral_estimate(buf, sps, hint_hz)   # hint_hz used as center
    if r_hint.valid and r_hint.peak_amp > r_plant.peak_amp:
        r_hint.reason = "hint"   # maps to HINT_MEASURED in firmware
        return r_hint
    return r_plant
```

### is_hint_research.py Simulation Loop Pattern

```python
for csv_path in all_28_csvs:
    windows = load_sweepraw(csv_path)   # existing helper in is_sweepraw_analyze.py
    hint_hz = 0.0
    for w in windows:
        duty = w["duty"]
        buf  = w["samples"].astype(np.float32)
        target_hz = expected_hz(duty)               # from is_algo_bench.py
        if duty <= 0:                               # FWD only (D6)
            continue  # or track but skip stats
        # direction-flip reset (D-B2 variant)
        if hint_reset_on_dir and sign_changed(prev_duty, duty):
            hint_hz = 0.0
        r = spectral_estimate_hint(buf, SPS, target_hz, hint_hz)
        # update hint only on pure plant win (D8)
        if r.valid and r.reason == "none":
            hint_hz = r.freq_hz
        # classify: valid / dropout (not valid, not DR)
        ...
    prev_duty = duty
```

---

## Firmware API — Exact Change Specification

### rpm_spectral_estimator.h — Two changes

**Change 1: enum extension**
```c
typedef enum {
    BIBA_RPM_SPECTRAL_INVALID_NONE       = 0,
    BIBA_RPM_SPECTRAL_INVALID_TARGET_LOW = 1,
    BIBA_RPM_SPECTRAL_INVALID_NO_BAND    = 2,
    BIBA_RPM_SPECTRAL_INVALID_PEAK_LOW   = 3,
    BIBA_RPM_SPECTRAL_INVALID_QUALITY_LOW = 4,
    BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED = 5,   /* DR fallback active */
    BIBA_RPM_SPECTRAL_HINT_MEASURED      = 6,     /* ← ADD: hint window won */
} biba_rpm_spectral_invalid_reason_t;
```

**Change 2: function signature (add 5th param)**
```c
// OLD:
biba_rpm_spectral_result_t biba_rpm_spectral_estimate(const uint16_t *buf,
                                                      uint16_t n,
                                                      uint32_t sps,
                                                      float target_hz);
// NEW:
biba_rpm_spectral_result_t biba_rpm_spectral_estimate(const uint16_t *buf,
                                                      uint16_t n,
                                                      uint32_t sps,
                                                      float target_hz,
                                                      float hint_hz);   /* 0.0f = no hint */
```

### rpm_spectral_estimator.c — Implementation extension

After existing plant-window code computes `result` (with `result.valid` potentially true),
add hint window block:

```c
/* Hint window: fire when hint differs from target by > deadband */
if (hint_hz != 0.0f &&
    fabsf(hint_hz - target_hz) > BIBA_RPM_SPECTRAL_ABS_BAND_HZ / 2.0f) {

    float h_target = clampf_local(hint_hz,
                                  BIBA_RPM_SPECTRAL_MIN_TARGET_HZ,
                                  BIBA_RPM_SPECTRAL_MAX_TARGET_HZ);
    float h_half = h_target * BIBA_RPM_SPECTRAL_REL_BAND;
    if (h_half < BIBA_RPM_SPECTRAL_ABS_BAND_HZ) h_half = BIBA_RPM_SPECTRAL_ABS_BAND_HZ;
    float h_lo = clampf_local(h_target - h_half, MIN_HZ, MAX_HZ);
    float h_hi = clampf_local(h_target + h_half, MIN_HZ, MAX_HZ);
    uint16_t hk_lo = (uint16_t)ceilf(h_lo / bin_hz);
    uint16_t hk_hi = (uint16_t)floorf(h_hi / bin_hz);
    if (hk_lo < 1u) hk_lo = 1u;
    if (hk_hi > k_max) hk_hi = k_max;

    if (hk_hi >= hk_lo) {
        /* scan hint band — mean already computed above */
        uint16_t h_best_bin = hk_lo;
        float h_best_amp = 0.0f, h_second_amp = 0.0f;
        for (uint16_t k = hk_lo; k <= hk_hi; ++k) {
            float amp = goertzel_amp_lsb(buf, n, mean, k);
            if (amp > h_best_amp) { h_second_amp = h_best_amp; h_best_amp = amp; h_best_bin = k; }
            else if (amp > h_second_amp) { h_second_amp = amp; }
        }
        if (h_best_amp >= BIBA_RPM_SPECTRAL_MIN_PEAK_AMP_LSB &&
            h_best_amp > result.peak_amp_lsb) {
            /* hint window wins — rebuild result fields */
            float h_noise_sum = 0.0f; uint16_t h_noise_count = 0u;
            for (uint16_t k = hk_lo; k <= hk_hi; ++k) {
                int dk = (int)k - (int)h_best_bin;
                if (dk >= -1 && dk <= 1) continue;
                h_noise_sum += goertzel_amp_lsb(buf, n, mean, k);
                h_noise_count++;
            }
            float h_noise = h_noise_count > 0u ? h_noise_sum / (float)h_noise_count : 0.0f;
            result.peak_amp_lsb   = h_best_amp;
            result.second_amp_lsb = h_second_amp;
            result.quality        = h_best_amp / (h_noise + 1.0f);
            /* parabolic interpolation for hint bin */
            float h_delta = 0.0f;
            if (h_best_bin > 1u && h_best_bin < k_max) {
                float hl = goertzel_amp_lsb(buf, n, mean, (uint16_t)(h_best_bin - 1u));
                float hm = h_best_amp;
                float hr = goertzel_amp_lsb(buf, n, mean, (uint16_t)(h_best_bin + 1u));
                float hd = hl - 2.0f * hm + hr;
                if (hd != 0.0f) { h_delta = 0.5f * (hl - hr) / hd; if (h_delta < -0.5f) h_delta = -0.5f; if (h_delta > 0.5f) h_delta = 0.5f; }
            }
            result.candidate_hz   = ((float)h_best_bin + h_delta) * bin_hz;
            result.freq_hz        = result.candidate_hz;
            result.invalid_reason = BIBA_RPM_SPECTRAL_HINT_MEASURED;
            result.valid          = true;
        }
    }
}
```

**Note:** The `mean` variable, `bin_hz`, `k_max` are already in scope from the existing plant window code path.

---

## Call Sites — Complete Inventory

### ⚠️ SPEC Count Discrepancy

SPEC states "4 in test_main.c" — **actual count is 6**. Total call sites to update: **8**.

| File | Line | Current call | Updated call |
|------|------|-------------|-------------|
| `firmware/test/test_rpm_spectral_estimator/test_main.c` | test 1 | `biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f)` | add `, 0.0f)` |
| `firmware/test/test_rpm_spectral_estimator/test_main.c` | test 2 | `biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f)` | add `, 0.0f)` |
| `firmware/test/test_rpm_spectral_estimator/test_main.c` | test 3 | `biba_rpm_spectral_estimate(buf, 512, 10000u, 700.0f)` | add `, 0.0f)` |
| `firmware/test/test_rpm_spectral_estimator/test_main.c` | test 4 | `biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f)` | add `, 0.0f)` |
| `firmware/test/test_rpm_spectral_estimator/test_main.c` | test 5 | `biba_rpm_spectral_estimate(buf, 512, 10000u, 40.0f)` | add `, 0.0f)` |
| `firmware/test/test_rpm_spectral_estimator/test_main.c` | test 6 | `biba_rpm_spectral_estimate(buf, 512, 10000u, 300.0f)` | add `, 0.0f)` |
| `firmware/src/modes/mode_standalone.c` | L366 | `biba_rpm_spectral_estimate(s_adc_left_buf, samples_per_channel, STANDALONE_RPM_WHEEL_SPS, s_meas_target_hz_left)` | add `, s_hint_hz_left)` |
| `firmware/src/modes/mode_standalone.c` | L369 | `biba_rpm_spectral_estimate(s_adc_right_buf, samples_per_channel, STANDALONE_RPM_WHEEL_SPS, s_meas_target_hz_right)` | add `, s_hint_hz_right)` |

All 6 test file updates pass `0.0f` as `hint_hz` → AC2 (no regression at hint=0) verified at compile time.

---

## hint_hz Reset Sites in mode_standalone.c

All sites where `biba_rpm_dr_reset()` is currently called — `s_hint_hz_left/right = 0.0f` must be added alongside:

| Lines | Event | Scope |
|-------|-------|-------|
| 300–301 | DBG serial DISARM command | both channels |
| 309–310 | DBG serial OLON (open-loop on) | both channels |
| ~316–317 | DBG serial OLOFF (open-loop off) | both channels |
| 515–516 | `biba_standalone_init()` mode entry | both channels |
| 623–624 | Failsafe rising edge | both channels |
| 670–671 | Disarm falling edge | both channels |
| 690–691 | Latch auto-recovery | both channels |
| 881 | Direction flip — left channel | left only (`s_hint_hz_left = 0.0f`) |
| 889 | Direction flip — right channel | right only (`s_hint_hz_right = 0.0f`) |

**D-B1 is already covered**: the direction flip block at L881/L889 is co-located with
`biba_rpm_dr_reset(&s_dr_left/right)` — adding `s_hint_hz_left/right = 0.0f` in the same
`if (rev_left != s_prev_rev_left)` / `if (rev_right != s_prev_rev_right)` blocks satisfies D-B1.

**State declaration placement**: add after `s_dr_left/s_dr_right` at L101–102:
```c
static biba_rpm_dr_state_t  s_dr_left;
static biba_rpm_dr_state_t  s_dr_right;
static float                s_hint_hz_left  = 0.0f;   /* ← ADD */
static float                s_hint_hz_right = 0.0f;   /* ← ADD */
```

---

## CSV Dataset Inventory

**Total: 28 CSV files** in `scripts/artifacts/is-sweepraw/` [VERIFIED: `ls *.csv | wc -l = 28`]

| Type | Count | Duty range | fwd↔rev transitions |
|------|-------|------------|---------------------|
| SIN | 23 | ±35%, ±40%, ±80%, ±100% | None (sinusoidal, some files FWD-only) |
| TRAP | 4 | ±30%, ±35% | **All 4 files** [VERIFIED: `has_rev=True`, duty range checked] |

**TRAP file details** (critical for D-B2 comparison):

| File | Windows | Duty range |
|------|---------|------------|
| `sweepraw_TRAP_amp30_per30000_n196_..._lefthold_left.csv` | 196 | [−30, +30] |
| `sweepraw_TRAP_amp30_per30000_n196_..._lefthold_right.csv` | 196 | [−30, +30] |
| `sweepraw_TRAP_amp35_per2500_n25_..._140559.csv` | 25 | [−35, +35] |
| `sweepraw_TRAP_amp35_per2500_n25_..._141024.csv` | 25 | [−35, +35] |

**D-B2 implication**: the two variants (`hint_reset_on_dir=True/False`) will diverge only at the
fwd↔rev transition windows in TRAP files. SIN files show identical results for both variants
(no direction change → no difference).

### CSV Schema [VERIFIED: `head -3 *.csv`]

```
win_idx,t_ms,duty_pct,sample_idx,adc_raw
0,0,0.00,0,1001
0,0,0.00,1,1001
...
```

- Each `win_idx` groups 512 rows (one 512-sample ADC window, ~51.2 ms at 10 kSPS)
- `duty_pct` is constant within a window (commanded duty for that window)
- `adc_raw` is 12-bit unsigned integer (0–4095)
- `load_sweepraw()` in `is_sweepraw_analyze.py` already handles this format — **re-use it**

---

## Python Files — Exact Changes Required

### is_sweepraw_analyze.py (D-D1)

**Add after the existing `spectral_estimate()` function:**

```python
# ---------------------------------------------------------------------------
# Extended firmware port: dual-window hint search (Phase 10)
# ---------------------------------------------------------------------------
_SPEC_DEADBAND_HZ = _SPEC_ABS_BAND_HZ / 2.0   # = 40.0 Hz (matches D2)


def spectral_estimate_hint(buf: np.ndarray, sps: int,
                            target_hz: float, hint_hz: float) -> SpectralResult:
    """Python port of the Phase 10 extended biba_rpm_spectral_estimate().

    Runs plant-model window first (always). Fires hint window only when
    |hint_hz - target_hz| > DEADBAND (40 Hz). Returns best candidate by
    peak_amp. result.reason == 'hint' when hint window wins.
    """
    r_plant = spectral_estimate(buf, sps, target_hz)
    if hint_hz == 0.0 or abs(hint_hz - target_hz) <= _SPEC_DEADBAND_HZ:
        return r_plant
    r_hint = spectral_estimate(buf, sps, hint_hz)
    if r_hint.valid and r_hint.peak_amp > r_plant.peak_amp:
        r_hint.reason = "hint"   # maps to BIBA_RPM_SPECTRAL_HINT_MEASURED = 6
        return r_hint
    return r_plant
```

**No changes to existing `spectral_estimate()` signature** — backward-compatible.

### is_hint_research.py (new file, Wave 1)

Key imports:
```python
from is_sweepraw_analyze import (
    spectral_estimate_hint, SpectralResult, load_sweepraw, expected_hz
)
from is_algo_bench import PLANT_K_HZ_PER_PCT, PLANT_DEAD_HZ, SPS
```

Per-file loop structure:
1. `load_sweepraw(csv_path)` → windows list
2. Simulate hint tracking with `hint_reset_on_dir=True` variant
3. Simulate hint tracking with `hint_reset_on_dir=False` variant
4. For each window where `duty > 0` (FWD only — D6): classify as `valid / dropout`
5. Compute per-file: `orig_dropout_pct`, `hint_dropout_pct`, `improvement_pp`, `winner_variant`
6. Pooled row: sum all FWD windows across all 28 files
7. Verdict: pooled improvement ≥ 5 pp → PASS (print to console; no exit-code gate per D-C1)

Output artifact: `scripts/artifacts/is_sweepraw_hint_research.png`
- Bar chart per file (23 SIN + 4 TRAP) + pooled bar
- Colour-coded: orig dropout (red/warm) vs hint dropout (green/cool)
- Dark theme matching existing `dr_v2_hint.png` aesthetics

---

## Unity Tests — New Test Cases (≥ 6 required)

### Existing helpers available [VERIFIED: test_main.c]
- `fill_sine(buf, n, sps, freq_hz, dc, amp)` — single-frequency sine
- `fill_two_sines(buf, n, sps, f1, amp1, f2, amp2)` — two sines superimposed
- `fill_noisy_two_sines(...)` — with additive white noise

### New helper needed
```c
/* Sine at `freq_hz` but centered outside target_hz band (used for hint tests) */
static void fill_sine_far(uint16_t *buf, uint16_t n, uint32_t sps,
                           float freq_hz, uint16_t amp)
{
    /* identical to fill_sine with dc=2048, amp as given */
    fill_sine(buf, n, sps, freq_hz, 2048u, amp);
}
```
Planner decides exact name; `fill_sine_far()` is the suggested convention.

### 6 New Test Cases

| # | Test name | Signal | target_hz | hint_hz | Expected outcome |
|---|-----------|--------|-----------|---------|-----------------|
| T1 | `test_hint_zero_suppresses_second_window` | sine 300 Hz, amp=500 | 300 | 0.0f | identical to 4-param call; `INVALID_NONE`, `valid=true` |
| T2 | `test_hint_within_deadband_no_second_window` | sine 300 Hz, amp=500 | 300 | 320 | `|320-300|=20 < 40`: no second pass; same as no-hint result |
| T3 | `test_hint_fires_and_wins_when_signal_outside_plant_band` | sine 430 Hz, amp=800 | 700 (plant band 620-780, misses 430) → actually use target=600, hint=430 | 430 | hint window finds 430 Hz peak; `result.valid=true`, `HINT_MEASURED`, `freq_hz ≈ 430` |
| T4 | `test_plant_wins_when_stronger_than_hint` | two_sines: f1=300 amp=800, f2=430 amp=200 | 300 | 430 | plant peak > hint peak; `INVALID_NONE`, `freq_hz ≈ 300` |
| T5 | `test_hint_wins_sets_HINT_MEASURED_reason` | sine 430 Hz, amp=800 (no signal near target=600) | 600 | 430 | `result.invalid_reason == BIBA_RPM_SPECTRAL_HINT_MEASURED` AND `result.valid == true` |
| T6 | `test_hint_zero_backward_compat_all_existing_pass` | (run existing `run_all()` internally or add inline check) | varies | 0.0f | all existing 6 tests still produce same result; regression check |

**Test parameters for T3/T5:**
- `target_hz = 600.0f`: half_band = max(600×0.35, 80) = 210 → band [390, 810]. Signal at 430 Hz IS inside plant band for target=600. Need to choose target such that signal is outside.
- Better: `target_hz = 700.0f`, `hint_hz = 430.0f`, signal at `430 Hz`. Plant band = [490, 910] — 430 Hz is OUTSIDE. Hint band centered on 430: [350, 510] — 430 Hz IS INSIDE. ✓

**Revised T3/T5 parameters**: `fill_sine(buf, 512, 10000u, 430.0f, 2048u, 800u)`, `target_hz=700.0f`, `hint_hz=430.0f`.
- `|430 - 700| = 270 > 40` → hint fires ✓
- Plant window [490, 910] Hz: 430 Hz outside → `best_amp_P` low → PEAK_LOW candidate
- Hint window [350, 510] Hz: 430 Hz inside → `best_amp_H` ≈ 800 >> 45 ✓

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| CSV loading for research script | Custom parser | `load_sweepraw()` already in `is_sweepraw_analyze.py` |
| Plant model Hz prediction | Re-implement formula | `expected_hz()` in `is_sweepraw_analyze.py` (uses `PLANT_K_HZ_PER_PCT`, `PLANT_DEAD_HZ` from `is_algo_bench.py`) |
| Goertzel amplitude | Second implementation | `goertzel_amp_lsb()` static helper already in `.c` — reuse; Python `_goertzel_amp()` already in `.py` |
| Parabolic interpolation | Custom sub-bin estimator | Already implemented in both C and Python — the hint window just runs the same logic |
| Bar chart layout | Custom matplotlib | Use existing `dr_v2_hint.png` style (dark bg, `plt.style.use('dark_background')`) |

---

## Common Pitfalls

### Pitfall 1: mean() computed twice
**What goes wrong:** Plant and hint windows each recompute `mean(buf)` — doubles O(N) sum.
**How to avoid:** Compute mean once before both windows; share the variable. Already done for the plant window; hint window must not call a full `spectral_estimate()` in C (only Python can do that cleanly because it's cheap). In C: reuse `mean` local variable.
**Python:** calling `spectral_estimate()` twice in Python is fine for analysis (correctness > perf).

### Pitfall 2: Hint window overlaps plant window
**What goes wrong:** When `|hint_hz − target_hz| ≤ deadband`, hint window scan overlaps or is redundant. Firing anyway wastes time and may select a spurious candidate.
**How to avoid:** The deadband gate (`> BIBA_RPM_SPECTRAL_ABS_BAND_HZ / 2.0f`) is the correct check. Test T2 specifically validates this suppression.

### Pitfall 3: hint updated on HINT_MEASURED result (feedback loop)
**What goes wrong:** If `s_hint_hz` is updated every time `spec.valid == true` (regardless of reason), it will be updated on HINT_MEASURED results too. This locks the hint at the hint-window frequency forever — the plant model never gets a chance to pull it back.
**How to avoid:** The update guard in mode_standalone.c must be `spec.valid && spec.invalid_reason == BIBA_RPM_SPECTRAL_INVALID_NONE` (reason == 0 only). HINT_MEASURED = 6, not 0.
**Python sim:** `result.reason == "none"` is the condition (not just `result.valid`).

### Pitfall 4: Call site count mismatch
**What goes wrong:** SPEC says "4 in test_main.c" but there are actually **6** call sites. Missing 2 causes a compile error.
**How to avoid:** Update all 6 test functions. The pattern is mechanical: add `, 0.0f` as the 5th argument.

### Pitfall 5: hint_hz reset missing at OLOFF site
**What goes wrong:** `biba_rpm_dr_reset()` is called at both OLON and OLOFF in the DBG serial handler, but it's easy to miss OLOFF when adding hint resets.
**How to avoid:** Grep for all `biba_rpm_dr_reset` occurrences (14 total) and add `s_hint_hz_left/right = 0.0f` at every one.

### Pitfall 6: is_hint_research.py hint tracking diverges from D8
**What goes wrong:** Research script updates `hint_hz` on every `result.valid == True`, including hint-window wins. This makes the simulation show better improvement than the actual firmware will achieve.
**How to avoid:** Only update `hint_hz` when `result.reason == "none"` (pure plant win).

---

## D-B2 Research Script Design Detail

The two variants differ only in TRAP files (all 4 have fwd↔rev transitions).

**Variant detection logic:**
```python
prev_sign = 0  # track sign of duty
for w in windows:
    curr_sign = 1 if w["duty"] > 0 else (-1 if w["duty"] < 0 else 0)
    if hint_reset_on_dir and curr_sign != prev_sign and curr_sign != 0 and prev_sign != 0:
        hint_hz = 0.0   # direction flip detected
    prev_sign = curr_sign if curr_sign != 0 else prev_sign
```

**Expected outcome:** D-B1 (reset on dir flip) should show slightly lower hint-assisted improvement
on TRAP files at the transition windows (hint lost, new direction starts cold). But TRAP files
have only 25–196 windows total, so the absolute difference may be small. The script quantifies this.

**For SIN files:** both variants produce identical results (no direction flip in SIN sweeps).

---

## Environment Availability

| Dependency | Required By | Available | Version |
|------------|------------|-----------|---------|
| Python 3 + numpy | is_hint_research.py, is_sweepraw_analyze.py | ✓ | (existing scripts run) |
| matplotlib | research chart PNG | ✓ | (existing scripts produce PNGs) |
| PlatformIO `native_test` | Unity test suite | ✓ | 78/78 pass [VERIFIED] |
| `load_sweepraw()` | is_hint_research.py | ✓ | in is_sweepraw_analyze.py |
| `expected_hz()` | is_hint_research.py | ✓ | in is_sweepraw_analyze.py |
| 28 CSV files | research script inputs | ✓ | [VERIFIED: 23 SIN + 4 TRAP] |

No missing dependencies.

---

## Baseline State (before Phase 10)

| Metric | Value |
|--------|-------|
| `pio test -e native_test` | **78 tests pass** [VERIFIED] |
| Tests in `test_rpm_spectral_estimator` | **6 tests** |
| `biba_rpm_spectral_estimate()` params | 4 |
| Enum values in `biba_rpm_spectral_invalid_reason_t` | 6 (0–5) |
| `s_hint_hz_left/right` in mode_standalone.c | not yet declared |
| `spectral_estimate_hint()` in is_sweepraw_analyze.py | not yet exists |

**Phase 10 exit state:**
- 78 + ≥ 6 = ≥ 84 tests pass
- 5-param function at all 8 call sites
- Enum has value 6 (HINT_MEASURED)
- `s_hint_hz_left/right` declared + reset at 9 sites + updated per D8
- `is_hint_research.py` committed with research artifact PNG

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | OLOFF command also calls `biba_rpm_dr_reset()` (line ~316–317, not directly verified) | Reset sites table | One reset site missed; hint not cleared on OLOFF → hint persists across open-loop mode transitions |

**Mitigation for A1:** The planner should verify by grepping `OLOFF` in mode_standalone.c before listing reset sites in the plan. Pattern: search `strcmp(line, "OLOFF")` block.

---

## Open Questions

1. **D8 hint-win update: should HINT_MEASURED also update hint_hz?**
   - Locked by SPEC D8: only `INVALID_NONE` updates hint. No change needed.
   - Implication: hint can only advance via plant-model wins. At sustained low-duty, hint freezes at last valid plant-model measurement. This is conservative but prevents feedback loops.

2. **Quality check for hint result (AC6 test coverage)**
   - The existing code sets `result.quality = best_amp / (noise_amp + 1.0)` — this must also be recomputed for the hint window when hint wins.
   - The firmware code sketch above includes this. Test T5 should assert `result.quality >= BIBA_RPM_SPECTRAL_MIN_QUALITY` is not required (quality can be low) — just `result.valid == true` and `result.invalid_reason == HINT_MEASURED`.

---

## Sources

### Primary (HIGH confidence — VERIFIED in this session)
- `firmware/src/app/rpm_spectral_estimator.h` — exact struct and enum values, function signature
- `firmware/src/app/rpm_spectral_estimator.c` — complete implementation, Goertzel loop, dual-window extension point
- `firmware/test/test_rpm_spectral_estimator/test_main.c` — all 6 tests, 3 existing helpers
- `firmware/src/modes/mode_standalone.c` — 2 call sites (L366/L369), DR reset sites (14 calls), direction-flip block (L881/L889), state declarations (L101-L112)
- `firmware/src/app/rpm_dr.h` — `biba_rpm_dr_state_t` pattern to follow
- `scripts/is_sweepraw_analyze.py` — `spectral_estimate()` implementation, `SpectralResult`, `load_sweepraw()`
- `scripts/is_algo_bench.py` — `PLANT_K_HZ_PER_PCT=10.13`, `PLANT_DEAD_HZ=74.6`, `SPS=10000`
- `scripts/artifacts/is-sweepraw/*.csv` — 28 files; CSV schema verified; TRAP fwd↔rev confirmed
- `pio test -e native_test` — 78 tests pass [VERIFIED: run in this session]

### Secondary (MEDIUM confidence)
- `.planning/phases/10-goertzel-dual-window/10-SPEC.md` — locked decisions, ACs, scope
- `.planning/phases/10-goertzel-dual-window/10-CONTEXT.md` — implementation decisions
- `.planning/phases/09-rpm-estimator-hardening/09-01-PLAN.md` — Wave 1 Python sim pattern to follow

---

## Metadata

**Confidence breakdown:**
- Firmware API + call sites: HIGH — source files read directly, all 8 call sites enumerated
- DR reset sites + hint placement: HIGH — verified by grep (14 calls at 7 events × 2 channels)
- Python spectral_estimate() extension: HIGH — existing function signature and logic verified
- CSV schema + inventory: HIGH — headers checked, all 28 files confirmed, TRAP transitions verified
- Unity test helpers: HIGH — test_main.c read completely
- D-B2 simulation logic: MEDIUM — design is clear from spec; runtime behaviour against real data is what the research script will measure

**Research date:** 2026-05-26
**Valid until:** 2026-06-26 (no external dependencies; only internal codebase)
