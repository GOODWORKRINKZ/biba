# Phase 11: IS-Pin Load & Stall Detection — Context

**Gathered:** 2026-05-27
**Status:** Ready for planning

<domain>
## Phase Boundary

The Goertzel spectral RPM estimator (Phase 9–10) returns `valid=True` even when
the motor is nearly stalled or heavily loaded. Root cause: at the start of a
102ms window the motor was still spinning → residual spectral energy near target
Hz gives quality ≥ MIN_QUALITY=3.0. The estimator has no knowledge of the DC
current level.

IS-pin DC level is a reliable secondary signal:
- Free rotation: DC_L ≈ 676 ADC counts (baseline)
- Heavy load / near-stall: DC_L = 2500–4095 (4095 = OCP latch)
- Ratio DC_loaded / DC_free > 2.5 with quality < 5 → false valid, motor not spinning

This phase adds a DC-level load gate to invalidate such false positives, adds
VBAT/IBAT raw ADC columns to SWEEPRAW captures for battery-sag research, and
researches the throttle-vs-load disambiguation problem (d_freq/d_dc gradients).

### Evidence
Softhold dataset: `scripts/artifacts/is-sweepraw/sweepraw_TRAP_amp50_per6000_n60_20260526-135642_softhold_{left,right}.csv`

| win | duty  | DC_L | AC_L | valid | reason   | freq_hz | quality |
|-----|-------|------|------|-------|----------|---------|---------|
|   5 |  +50  |  676 |  226 | True  | OK       |  400.5  |  27.5   | ← baseline free
|   3 |  +50  | 2588 |  849 | True  | OK       |  352.4  |   3.7   | ← **FALSE POSITIVE** (stall ghost)
|  12 |  -28  | 2387 | 1064 | False | PEAK_LOW |  300.3  |   2.5   | ← correct
|  14 |  -50  | 1139 |  322 | True  | OK       |  379.5  |  11.1   | ← correct (light load)
|  18 |  -50  | 3586 |  530 | True  | OK       |  326.1  |   9.4   | ← **FALSE POSITIVE** (pre-latch)
|  19 |  -39  | 4095 |    0 | False | PEAK_LOW |  263.7  |   0.0   | ← correct (OCP latch)

Win3 and win18 are the false positives to fix in this phase.

### Hardware / Firmware Context (invariants from Phases 5–10)
- RP2040, PlatformIO, `rpico_rp2040_is_poc` target
- ADC: GP26=ADC0=IS_RIGHT, GP27=ADC1=IS_LEFT, GP28=ADC2=VBAT, GP29=ADC3=IBAT
- All 4 ADC pins already `adc_gpio_init()`'d in `biba_hal_rp2040.c:149`
- `biba_hal_adc_sample(ch)` returns uint16_t raw (12-bit, FS=3.3V)
- VBAT/IBAT sensor = APM/Pixhawk power module (0–30V / 0–90A → 0–3.3V analog)
  **Not yet installed** — pins will float; raw values are noise until sensor connected
- `BIBA_ADC_CHAN_VBAT=2`, `BIBA_ADC_CHAN_IBAT=3` in target_config.h
- Spectral estimator: `biba_rpm_spectral_estimate(buf, n, sps, target_hz, hint_hz)`
  (5-arg signature, Phase 10). Enum values: HINT_MEASURED=6
- SWEEPRAW_BOTH command in `firmware/src/poc/is_rpm_poc_main.cpp:cmd_sweepraw_both()`
  Protocol: `SWEEPRAW2_WIN win=N n=1024 dc_l=X dc_r=Y\n` then 1024 raw samples
- Python parser: `scripts/is_poc_sweepraw.py` → CSV files in `scripts/artifacts/is-sweepraw/`

</domain>

<decisions>
## Locked Decisions

### A: Load Detector — Python sim gate → firmware in Phase 11

**D-A1:** The load gate is implemented in **two steps within Phase 11**:
1. Python simulation research (`is_load_detector_research.py`): tries candidate
   thresholds on softhold dataset, finds ratio + quality pair that correctly
   invalidates win3 and win18 without rejecting win14 (light-load valid).
2. Firmware implementation: new `BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD = 7` enum
   value; gate inside `biba_rpm_spectral_estimate()` or as post-check in
   `mode_standalone.c`. Location decided after Python research.

**D-A2:** Gate condition (starting point, exact thresholds from research):
  `mean_IS_channel / mean_IS_other > LOAD_RATIO_THRESH AND quality < LOAD_QUALITY_MAX`
  → set `valid = false`, `invalid_reason = BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD`

**D-A3:** Baseline for ratio: use other channel's DC as proxy (not a stored
baseline). If both channels are loaded simultaneously, the gate uses absolute
threshold `mean_IS > LOAD_ABS_THRESH_ADC`. Research defines both.

**D-A4:** `LOAD_RATIO_THRESH` and `LOAD_QUALITY_MAX` are `biba_config.h`
constants, not hard-coded inline.

### B: VBAT/IBAT in SWEEPRAW_BOTH Firmware

**D-B1:** Add 2 fields to the `SWEEPRAW2_WIN` header line:
  `SWEEPRAW2_WIN win=N n=1024 dc_l=X dc_r=Y vbat=<raw> ibat=<raw>`
  One `biba_hal_adc_sample()` call each, taken before the IS window starts.

**D-B2:** With sensor not installed, values are floating-pin noise. This is
acceptable — columns will be present in CSV with noise, calibrated later.
No masking or sentinel value needed at this stage.

**D-B3:** Python parser `is_poc_sweepraw.py`: adds `vbat_raw` and `ibat_raw`
columns to the same CSV output (not a separate file).

**D-B4:** Backward compatibility: if parser encounters a `SWEEPRAW2_WIN` line
without vbat/ibat fields (old firmware), it fills those columns with `NaN`.

### C: Battery Sag Cross-talk

**D-C1:** Phase 11 first analyses existing softhold dataset for DC_L vs DC_R
correlation during load events (one channel loads, check if other channel rises).
Produces a scatter plot and Pearson-r coefficient.

**D-C2:** If correlation is confirmed (|r| > 0.3), a new controlled capture is
planned in a Phase 11 sub-plan: SWEEPRAW_BOTH with one motor free and one
manually held (stall). Computes sag coefficient `k_sag = ΔDC_free / DC_free_base`.

**D-C3:** Compensation formula research (Python only, no firmware in Phase 11):
`DC_corrected_L = DC_L - k_sag * (DC_R - DC_R_base)`.
Firmware implementation deferred to Phase 12.

### D: Throttle vs Load Disambiguation

**D-D1:** Phase 11 scope = research + ADR only. No firmware.

**D-D2:** Research hypothesis: when throttle increases → `d_freq > 0` AND
`d_DC > 0` simultaneously (motor accelerating, more current). When load
increases → `d_freq < 0` AND `d_DC > 0` (motor slowing down under load).
Stall: `d_freq → 0` AND `d_DC >> 0`.

**D-D3:** Research script (`is_load_disambiguate.py`) computes inter-window
`(Δfreq, ΔDC)` vectors from existing softhold dataset, plots classification
scatter, reports decision boundary.

**D-D4:** Output: `11-LOAD-DISAMBIGUATE-ADR.md` — Architecture Decision Record
with findings and proposed firmware detection rule. Implementation in Phase 12+.

</decisions>

<spec_lock>
## Acceptance Criteria (pre-lock)

1. `is_load_detector_research.py` reports that load gate correctly marks win3
   and win18 as `HIGH_LOAD` (was false-valid) and does NOT reject win14 (true
   valid, light load), using softhold dataset.
2. `firmware/src/poc/is_rpm_poc_main.cpp` cmd_sweepraw_both() outputs `vbat=<raw>
   ibat=<raw>` in SWEEPRAW2_WIN header; firmware builds and flashes without error.
3. `is_poc_sweepraw.py` saves `vbat_raw` and `ibat_raw` columns in CSV output;
   NaN backfill when fields absent (old protocol).
4. New softhold capture CSV includes non-empty vbat_raw/ibat_raw columns (even
   if noise — confirms pipeline end-to-end).
5. Battery sag: DC_L vs DC_R scatter plot + Pearson-r reported for existing
   softhold dataset. If |r| > 0.3, a controlled capture procedure is documented.
6. `11-LOAD-DISAMBIGUATE-ADR.md` exists with Δfreq/ΔDC scatter plot + decision
   boundary from softhold data.
7. `BIBA_RPM_SPECTRAL_INVALID_HIGH_LOAD = 7` enum added to firmware; Unity test
   confirms win3/win18 analog inputs → invalid, win14 → valid.
8. pio test -e native_test: all existing 84 tests pass + ≥4 new load-gate tests.

</spec_lock>
