# Plan 07-02 Summary — biba_proto wheel_rpm telemetry + Python decode

**Phase**: 07-is-rpm-integration
**Plan**: 07-02
**Status**: Complete
**Branch**: develop
**Commits**: `2936901`, `b30853d`, `463ca42`

---

## Objective Delivered

Extended `biba_proto_telemetry_t` with two `uint16_t` wheel_rpm fields carved
from the existing `reserved[11]` region. Atomically updated the Python
decoder, added env-driven speed constants, and exposed a `wheel_rpm_to_mps()`
helper. Struct size unchanged at 48 bytes — no wire-level break,
`BIBA_PROTO_VERSION` untouched.

This delivers the RP2040 → Pi telemetry pipeline for IS-RPM (requirement
RPM-INT-03). Plan is fully independent of Plan 07-01's `zc_detector.h`.

---

## Changes

### C firmware (commit `2936901`)
- `firmware/src/proto/biba_proto.h`:
  - Replaced `uint8_t reserved[11]` with `uint16_t wheel_rpm_left_hz10`
    + `uint16_t wheel_rpm_right_hz10` + `uint8_t reserved[7]`.
  - Fields are ZC frequency scaled ×10 (0.1 Hz resolution); 0 = invalid /
    stopped sentinel.
- `firmware/src/app/telemetry.h`:
  - `biba_telemetry_input_t` gains `float wheel_rpm_left_hz` and
    `float wheel_rpm_right_hz`.
- `firmware/src/app/telemetry.c`:
  - `biba_telemetry_collect()` clamps negatives to 0, scales ×10 with round,
    saturates at 0xFFFF before storing. Block guards inside braces to avoid
    polluting outer scope.

### Python controller (commit `b30853d`)
- `biba-controller/stm32_link/protocol.py`:
  - `TELEMETRY_STRUCT`: `"...BHH7s"` (was `"...B11s"`).
  - `Telemetry` dataclass: `wheel_rpm_left_hz`, `wheel_rpm_right_hz` floats.
  - `from_bytes`: decodes `fields[20] / 10.0`, `fields[21] / 10.0`.
  - `to_bytes`: encodes via `int(round(hz * 10))` clamped to `[0, 0xFFFF]`,
    pads with `b"\x00" * 7`.
- `biba-controller/config.py`:
  - `WHEEL_RADIUS_M` (env `WHEEL_RADIUS_M`, default `0.100` m).
  - `GEAR_RATIO` (env `GEAR_RATIO`, default `1.0`).
- `biba-controller/main.py`:
  - `import math` added.
  - `wheel_rpm_to_mps(rpm_hz)` → `(2·π·hz·R) / G`. Returns 0.0 for
    `rpm_hz <= 0` or `GEAR_RATIO == 0` (T-07-02-02 mitigation).

### Tests (commit `463ca42`)
- `tests/test_stm32_link_protocol.py` — appended 5 new tests:
  - `test_telemetry_size_still_48` — invariant on struct size.
  - `test_wheel_rpm_decode_300hz` — 300/150 Hz roundtrip via to_bytes/from_bytes.
  - `test_wheel_rpm_decode_zero` — zero sentinel decodes to 0.0.
  - `test_wheel_rpm_encode_roundtrip` — 432.7 / 428.1 Hz survive within 0.1 Hz.
  - `test_wheel_rpm_zero_invalid_encodes_zero_bytes` — verifies bytes at
    payload offset 37/39 (absolute 43/45) are 0x0000 when Telemetry default.

---

## Verification (all gates green)

| Gate | Result |
|------|--------|
| `pio test -e native_test -f test_biba_proto` (sizeof check) | 9/9 PASS |
| `pio test -e native_test` (full native regression) | 47/47 PASS |
| `pytest tests/test_stm32_link_protocol.py -v` | 30/30 PASS (25 prior + 5 new) |
| `grep wheel_rpm_left_hz10 firmware/src/proto/biba_proto.h` | hit |
| `grep "reserved\[7\]" firmware/src/proto/biba_proto.h` | hit |
| `grep "reserved\[11\]" firmware/src/proto/biba_proto.h` | 0 hits |
| `grep HH7s biba-controller/stm32_link/protocol.py` | hit |
| `grep WHEEL_RADIUS_M\|GEAR_RATIO biba-controller/config.py` | both hit |
| `grep wheel_rpm_to_mps biba-controller/main.py` | hit |

## Self-Check: PASSED

- Struct size invariant (48 B) verified by both `test_biba_proto` (C) and
  `test_telemetry_size_still_48` (Python).
- `BIBA_PROTO_VERSION` untouched — no breaking-change signaling.
- Threat T-07-02-02 (GEAR_RATIO=0 div-by-zero) mitigated by explicit
  `if config.GEAR_RATIO == 0.0: return 0.0` guard, in addition to the
  `rpm_hz <= 0` early-return.
- No existing tests modified or broken; only appended new ones.

## Deviations

None. All three tasks executed exactly per `<action>` blocks.

## Notes for downstream plans

- Plan 07-05 will populate `inputs->wheel_rpm_left_hz` /
  `inputs->wheel_rpm_right_hz` from the ZC detector EMA outputs in
  `mode_standalone.c` and pass them through `biba_telemetry_collect`.
- Pre-existing environment issue: `tests/test_main*.py`,
  `tests/test_imu_factory.py`, and several others fail at collection because
  `smbus2` is not installed in the current dev venv. This affects ~94 tests
  but is **not** introduced by Plan 07-02 (root cause:
  `biba-controller/imu/factory.py:5: from smbus2 import SMBus`). Plan-relevant
  tests all pass.
