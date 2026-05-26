# Plan 11-03 SUMMARY — VBAT/IBAT in SWEEPRAW Protocol

**Date:** 2026-05-26
**Status:** COMPLETE

## Changes

### Firmware: `firmware/src/poc/is_rpm_poc_main.cpp`
- Added VBAT/IBAT ADC sampling in `cmd_sweepraw_both()` per-window loop
- `biba_hal_adc_sample(BIBA_ADC_CHAN_VBAT)` and `BIBA_ADC_CHAN_IBAT` sampled after duty set, before IS captures
- L header extended to 7 tokens: `SWEEPRAW2_WIN <idx> <t> <duty> L <vbat> <ibat>`
- R header unchanged (5 tokens)
- `pio run -e rpico_rp2040_is_poc` → SUCCESS

### Python Parser: `scripts/is_poc_sweepraw.py`
- `_parse_both_windows()`: extracts vbat_raw/ibat_raw from L headers when `len(parts) >= 7`
- R windows and old firmware: `NaN` backfill (D-B4)
- `_write_csv()`: extended header row + data row with `vbat_raw`, `ibat_raw` columns

## Acceptance Criteria — ALL PASS
- [x] `grep -c "vbat_raw" firmware/src/poc/is_rpm_poc_main.cpp` → 2 (>= 2)
- [x] L header printf has `%u %u` format
- [x] R header printf unchanged
- [x] `pio run` SUCCESS, no compile errors
- [x] Python parser: vbat_raw appears in parse, header, and data row
- [x] `len(parts) >= 7` guard present

## Note
With APM power module now connected, future captures will have real VBAT/IBAT data instead of floating-pin noise.
