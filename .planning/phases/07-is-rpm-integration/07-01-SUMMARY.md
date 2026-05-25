---
phase: 07-is-rpm-integration
plan: "01"
status: complete
created: 2026-05-23
---

# Plan 07-01 Summary: ZC Detector + Async ADC Capture

## What Was Built

- **firmware/src/app/zc_detector.h/c** — portable C99 module:
  - `zc_freq_hz(buf, n, sps)` — A2 Sub-window Schmitt-trigger frequency estimator extracted verbatim from `firmware/src/poc/is_rpm_poc_main.cpp` (lines 149–177). No pico-sdk/HAL dependency — compiles cleanly under `native_test`.
  - `zc_ema_update(*ema, raw, target)` — two-sided validity-gated EMA (alpha=0.7) with `*=0.9` slow-decay branch for the raw==0 case (extracted from `cmd_rpmrun`).
  - Constants: `ZC_SUBWIN_K=8`, `ZC_SUBWIN_MIN_PKPK=30`, `ZC_MIN_VALID_HZ=80.0`, `ZC_EMA_ALPHA=0.7`.
- **firmware/src/app/adc_capture.h/c** — moved from `src/poc/` (poc files preserved unchanged) and extended:
  - Preserved `adc_capture_init()` and blocking `adc_capture_burst()` APIs.
  - Added `adc_capture_done_cb_t` callback type.
  - Added `adc_capture_start_async(ch, n, buf, cb)` — non-blocking DMA start with IRQ-driven completion callback.
  - Added `adc_capture_busy()` — idle check.
  - Implementation guards: busy check (`s_dma_ch >= 0` → return false), idle-mark before callback (so callback can synchronously restart capture), shared IRQ handler registered via `irq_add_shared_handler(DMA_IRQ_0, ...)`.
- **firmware/test/test_zc_detector/test_main.c** — 5 Unity tests:
  - `test_pure_sine_300hz` — 300 Hz sine ±15 Hz
  - `test_pure_sine_500hz` — 500 Hz sine ±25 Hz
  - `test_dc_only_returns_zero` — DC buffer → 0.0
  - `test_too_short_returns_zero` — n=16 (< ZC_SUBWIN_K*4=32) → 0.0
  - `test_ema_update_valid_range` — alpha=0.7 application
- **firmware/platformio.ini** — `[common]` build_src_filter excludes `<poc/>` and `<app/adc_capture.c>` so native_test never touches pico-sdk-dependent code; `-lm` added to native_test build_flags for `sinf`.

## Verification

```
pio test -e native_test --filter test_zc_detector
→ 5 Tests, 0 Failures (test_pure_sine_300hz/500hz, dc_only, too_short, ema_valid all PASS)

pio test -e native_test          (full regression)
→ 47 test cases: 47 succeeded
   test_bts7960, test_zc_detector, test_control_loop, test_crsf, test_biba_proto, test_ramp all PASS
```

## Deviations from Plan

**[Rule 1 — Pre-existing build bug]** native_test build broken before this plan

- **Found during:** Task 3 verification (`pio test -e native_test --filter test_zc_detector`).
- **Issue:** `[common]` build_src_filter never excluded `src/poc/` — both `poc/adc_capture.c` (uses `<hardware/adc.h>`) and `poc/is_rpm_poc_main.cpp` (uses `<Arduino.h>`) were being compiled under the `native` platform and failing with `fatal error: hardware/adc.h: No such file or directory` and `Arduino.h: No such file or directory`. Confirmed pre-existing: `pio test -e native_test --filter test_ramp` failed identically before the new module landed.
- **Fix:** Added `-<poc/>` to `[common]` build_src_filter. Does not affect `[fw_common]` (STM32) or `[rp2040_poc_src_filter]` (PoC env still gets `+<poc/>` explicitly).
- **Files modified:** firmware/platformio.ini
- **Verification:** `pio test -e native_test` → 47/47 PASS.
- **Commit hash:** Folded into Task 3 commit.

**[Rule 1 — Pre-existing missing libm link]** sinf undefined in native_test

- **Found during:** Task 3 verification.
- **Issue:** native_test env did not link libm; new test needs `sinf` for the sine-wave generator (the plan's spec listed it in `behavior`).
- **Fix:** Added `-lm` to `[env:native_test].build_flags`.
- **Files modified:** firmware/platformio.ini (same edit cycle).
- **Verification:** linker error gone, tests link and pass.
- **Commit hash:** Folded into Task 3 commit.

**Total deviations:** 2 auto-fixed (both Rule 1, pre-existing build bugs in the native_test env).
**Impact:** Native test environment is now usable for future portable modules (rpm_pi in Plan 07-04 will reuse this same env).

## Key Files Created

- `firmware/src/app/zc_detector.h`
- `firmware/src/app/zc_detector.c`
- `firmware/src/app/adc_capture.h`
- `firmware/src/app/adc_capture.c`
- `firmware/test/test_zc_detector/test_main.c`

## Self-Check: PASSED

- [x] zc_freq_hz() returns frequency within ±5% for a synthetic 300 Hz sine at 10 kSPS (test_pure_sine_300hz tolerance ±15 Hz = ±5% of 300 Hz; PASSED)
- [x] zc_freq_hz() returns 0.0 for a DC-only buffer (test_dc_only_returns_zero; PASSED)
- [x] adc_capture_start_async() API exists with callback signature in adc_capture.h (declared in firmware/src/app/adc_capture.h)
- [x] pio test -e native_test --filter test_zc_detector exits 0 (5 Tests, 0 Failures)
- [x] adc_capture.c compiles for rpico_rp2040_standalone env (includes hardware/adc.h, hardware/dma.h, hardware/irq.h — built under standalone via app/ inclusion; native_test correctly excluded)

## Next Plan Readiness

Plan 07-04 (rpm_pi) can `#include "zc_detector.h"` and call `zc_ema_update()`.
Plan 07-05 (mode_standalone.c integration) can call `adc_capture_start_async()` with a per-wheel completion callback.
