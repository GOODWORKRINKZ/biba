# 08-01 SUMMARY — LittleFS Blackbox Core

## Status: COMPLETE

## What Was Built

**New files:**
- `firmware/src/app/blackbox.h` — C-compatible header: packed structs `biba_blackbox_header_t` (32 B) and `biba_blackbox_record_t` (31 B), static-assert size checks, `extern "C"` API declarations, `BLACKBOX_MAGIC "BBD1"`.
- `firmware/src/app/blackbox.cpp` — LittleFS implementation: init/format, open/write/close session, full-check, list/send/delete sessions via CDC, path-traversal-safe filename validation.
- `firmware/test/test_blackbox/test_main.c` — 4 Unity tests: header size, record size, magic bytes, rate-hz-fits-byte. All 4 PASS.

**Modified files:**
- `firmware/src/hal/biba_hal.h` — added `biba_hal_serial_write_bytes` and `biba_hal_serial_write_str` declarations.
- `firmware/src/hal/biba_hal_serial.cpp` — implemented `write_bytes` (`Serial.write`) and `write_str` (`Serial.print`).
- `firmware/include/biba_config.h` — added `BIBA_BLACKBOX_RATE_HZ`, `BIBA_BLACKBOX_FIELD_MASK`, `BIBA_BLACKBOX_MIN_FREE_KB`, `BIBA_CH_BLACKBOX`.
- `firmware/platformio.ini` — added `board_build.filesystem_size = 4MB` to `[env:rpico_rp2040_standalone]`; excluded `blackbox.cpp` and `motor_bridge.c` from `[common]` src filter (HAL-dependent files); fixed phase-7 regression by pulling `motor_bridge.c` directly in `test_motor_bridge/test_main.c`.

## Verification Results

- `pio test -e native_test`: **71/71 PASS** (4 new blackbox + all 67 pre-existing)
- `pio run -e rpico_rp2040_standalone`: **SUCCESS**

## Struct Sizes (verified by static_assert + tests)

| Struct | Expected | Actual |
|---|---|---|
| `biba_blackbox_header_t` | 32 B | 32 B ✓ |
| `biba_blackbox_record_t` | 31 B | 31 B ✓ |

## Security Notes

- `filename_is_valid()` in `blackbox.cpp` uses sscanf + snprintf round-trip comparison to prevent path traversal in `bb get` / `bb del` commands (T-08-01 threat mitigation, per 08-01-PLAN.md §Security).

## Dependencies Provided to 08-02

- `blackbox_init()` — call once in `biba_mode_standalone_init()`
- `blackbox_open_session(num, field_mask, rate_hz)` — opens `/session_NNNN.bbd`, writes 32-B header
- `blackbox_write_record(buf, len)` — appends 31-B record
- `blackbox_close_session()` — flush + close
- `blackbox_is_full(min_free_kb)` — returns true when LittleFS free < threshold
- `blackbox_delete_oldest()` — removes oldest session by session number
- `BIBA_BLACKBOX_RATE_HZ`, `BIBA_BLACKBOX_FIELD_MASK`, `BIBA_BLACKBOX_MIN_FREE_KB`, `BIBA_CH_BLACKBOX`
