---
doc: ARCHITECTURE-RESEARCH
last_mapped: 2026-05-14
---

# Architecture Research: Multi-Target Robot Platform

**Confidence:** HIGH — based on existing codebase + verified patterns against well-known
PlatformIO, protobuf, and embedded cross-platform literature.

---

## Multi-Target Embedded Patterns

### Pattern: Hub-and-Spoke (SBC as coordinator)

The dominant pattern for Linux+MCU systems. SBC owns high-level logic (mode arbitration, AI,
BMS, voice, telemetry publishing). MCUs own deterministic real-time work (PWM, ADC, CRSF
timing). Communication is explicit and boundary-crossing is intentional.

BiBa already implements this cleanly:

- **Composition A**: Pi standalone (hub + spoke collapsed into one host)
- **Composition C**: Pi as ROS2 hub, STM32 as SPI-slave spoke
- **Composition B**: STM32 standalone (no hub, spoke runs self-contained)

The key discipline that makes this work: **spoke must be safe without hub**. STM32 firmware
has independent CRSF watchdog and SPI watchdog — if Pi dies, motors stop. Hub failure is
always safe. This is the correct pattern for field robots.

### Pattern: Capability Flags as Target Contract

`target.h` per board defines `BIBA_TARGET_HAS_*` flags (e.g., `BIBA_TARGET_HAS_SPI_SLAVE`,
`BIBA_TARGET_HAS_IMU`). Shared source uses `#if BIBA_TARGET_HAS_X` gates. This is the
Betaflight/ELRS-style approach — one source tree, many boards, compile-time specialization.

Correct approach for this project. Avoids runtime dispatch overhead on constrained MCUs.

### Pattern: HAL Shim per Target

`firmware/src/hal/` contains `biba_hal_motor.c` (STM32F103 TIM-based PWM) and
`biba_hal_motor_rp2040.c` (RP2040 PWM slice API). Identical function signatures, different
implementations. PlatformIO `build_src_filter` in each env selects the right HAL file.

This is the clean pattern. Extend it: when adding RP2040 SPI slave or I2C IMU, add
`biba_hal_spi_rp2040.c` / `biba_hal_imu_rp2040.c` rather than #ifdef-ing inside shared files.

### Pattern: Mode Dispatch via Compile Flag

`BIBA_MODE_STANDALONE` / `BIBA_MODE_COMPANION` / `BIBA_MODE_COMBINED` select which top-level
behavior is compiled in. The `modes/mode_dispatcher.c` routes to the correct mode.

Important: modes are orthogonal to targets. Any target can run any mode (if hardware permits).
The `platformio.ini` env naming convention `<target>_<mode>` makes all combinations explicit.

---

## Python ↔ C/C++ Protocol Sharing

### Current approach: manual mirroring + CI drift test (HIGH confidence, correct)

`firmware/src/proto/biba_proto.h` and `biba-controller/stm32_link/protocol.py` are manually
kept identical. `tests/test_biba_proto_drift.py` fails CI if they diverge. This is intentional
and appropriate for a 64-byte fixed-frame protocol — the overhead of a codegen pipeline
(protobuf, flatbuffers) exceeds the protocol's actual complexity.

**Recommendation: keep the manual mirror pattern** for `biba_proto`. The drift test is the
right enforcement mechanism. Add CRC vector tests for every new command/telemetry type added.

### Alternative: protobuf/nanopb (use only if protocol grows complex)

If the protocol needs nested structs, variable-length arrays, optional fields, or versioned
forward compatibility, **nanopb** (C library, ~1–2 KB flash) + standard protobuf Python is the
correct upgrade path:

- Define in `.proto` file → generate `*.pb.h` / `*.pb.c` for MCU, Python code for Pi
- Single source of truth eliminates drift entirely
- Nanopb is used in production on RP2040 and STM32 (Zephyr, ArduPilot, etc.)
- Adds codegen step to build pipeline; adds `.proto` as a new required artifact

**Trigger for upgrade:** If `biba_proto` payload count exceeds ~6 command types, or if Pi-side
consumers (ROS2 bridge, web telemetry) diverge from a single Python codec.

### Alternative: msgpack (avoid for this project)

MessagePack is compact and language-agnostic but requires dynamic allocation and length-prefix
framing that fights against fixed 64-byte SPI frames. Not recommended here.

### Alternative: shared C header parsed by Python ctypes (avoid)

Some projects parse `biba_proto.h` with Python `ctypes.Structure`. Brittle — sensitive to
preprocessor macros, alignment, padding. The manual mirror + drift test is simpler and safer.

### Config/PID values: env var → struct on Python, `#define` → struct on MCU

These don't need wire-format sharing at runtime. They are set at deployment time. See
Config/Calibration Portability section below.

---

## PlatformIO Multi-Board Structure

### Existing structure (correct, follow it)

```
firmware/
├── platformio.ini           # ALL envs defined here; inherits via extends =
├── targets/
│   ├── BLUEPILL_F103C8/
│   │   ├── target.h         # pin defines + capability flags
│   │   └── target_config.h  # board-specific calibration constants
│   ├── BLUEPILL_F103C8_CLONE/
│   ├── BIBA_F103_REV_A/
│   └── RPICO_RP2040/
│       ├── target.h
│       └── target_config.h
├── src/
│   ├── app/                 # mode-independent application logic
│   ├── drivers/             # peripheral drivers (crsf, imu, bts7960, adc)
│   ├── hal/                 # per-target HAL implementations
│   ├── modes/               # standalone / companion / combined entry logic
│   └── proto/               # biba_proto (shared with Python)
├── include/
│   └── biba_config.h        # global defaults (overridden by target_config.h)
└── test/                    # native PlatformIO unit tests (host runner)
```

### Key rules to preserve

1. **`target.h` = pin map + capability flags only.** No business logic. No magic numbers.
2. **`target_config.h` = calibration overrides.** Current-sense zero offset, ADC ratio, VBAT divider.
   RP2040 version should add its own calibration values measured from real hardware.
3. **`biba_config.h` = global policy defaults.** Timeouts, protocol version, loop rate, PWM
   frequency. Any target that doesn't override gets these. Put safe defaults here.
4. **`env:<target>_<mode>` naming in platformio.ini.** Do not deviate; it's the matrix convention.
5. **`build_src_filter` selects HAL file per env.** Prefer filter over #ifdef inside HAL.

### Adding RP2040 modes (RP2040-PORT phases)

Each new RP2040 capability needs:

```ini
[env:rpico_rp2040_companion]
extends = env_rp2040, fw_common
build_flags =
    ${fw_common.build_flags}
    -I${target_rpico_rp2040.target_include}
    ${target_rpico_rp2040.build_flags}
    ${mode_companion.build_flags}
```

Where `env_rp2040` is a new base stanza replacing `env` (which defaults to `platform = ststm32`).
RP2040 needs `platform = raspberrypi`, `framework = arduino` or `framework = pico-sdk`.

### PlatformIO native test (host runner)

`pio test -e native` runs `test/` on the host without hardware. Use this for protocol codec
tests, PID math, and any pure logic. Already used for `test/test_biba_proto/`. Extend for RP2040
new logic before flashing.

---

## Config/Calibration Portability

### Python side: env vars → `config.py` constants (HIGH confidence, correct)

All configuration is read from environment variables at import time in `config.py`. The Docker
Compose file injects values. No runtime mutation. Tests patch via `monkeypatch.setattr`.

Calibration values that are hardware-specific (motor trim, PID gains) are persisted separately:

- `settings_store.py` — motor trim (JSON, atomic write)
- `pid_tuning.py` — PID params (JSON file store)

This is the correct pattern for a Linux runtime. JSON persistence is version-control friendly.

### Firmware side: `target_config.h` overrides + runtime EEPROM (current + recommended)

**Compile-time calibration** (current): `target_config.h` defines `BIBA_IS_ZERO_OFFSET_V`,
`BIBA_IS_AMPS_PER_VOLT`, `BIBA_VBAT_DIVIDER_RATIO`. Good for values that are fixed per board
revision. Requires reflash to change.

**Runtime calibration persistence** (not yet implemented, needed for RP2040-PORT-04/05):

- STM32F103: Flash last-page storage (HAL FLASH_Program). 1 KB is sufficient for PID + trim.
- RP2040: LittleFS on onboard flash (standard pattern, library available in PlatformIO).
  Simpler than raw flash writes; wear-levelled; survives power loss.

**Recommendation:** For RP2040 port, add a `calibration.c/h` module that reads/writes a small
struct (PID gains, trim values, current-sense offsets) to LittleFS on startup.
Default to `target_config.h` defines if no persisted data found.

### Cross-target config sharing

Do not attempt to share config values between Python and C via generated code. The two runtimes
have different deployment lifecycle:

- Pi config changes: update `.env` file, restart Docker — 10 seconds
- MCU config changes: reflash — 30 seconds (or use persisted EEPROM)

**Sharing protocol**: If Pi needs to push calibration to MCU, use `SET_CONFIG` command already
defined in `biba_proto` (`Command.SET_CONFIG = 0x30`). Pi serializes calibration into proto
payload, MCU deserializes and stores in flash/LittleFS. This is already scaffolded — implement
the payload struct and storage on each side.

---

## Suggested Build Order

Based on dependency graph:

```
Phase 1 — Hardware foundation (no dependencies)
  RP2040-PORT-01: CRSF receive + decode
  RP2040-PORT-02: BTS7960 PWM output
  THERMAL-01:     Physical thermal fix (hardware, no software dep)

Phase 2 — Sensing (depends on Phase 1 motor control being stable)
  RP2040-PORT-03: IMU heading-hold (depends on Phase 1 motor control)
  RP2040-PORT-04: Current measurement (needs motors running to validate)

Phase 3 — Calibration + safety (depends on Phase 2 sensors)
  RP2040-PORT-05: Channel trim (needs CRSF + motors working)
  RP2040-PORT-06: Failsafe (needs all of the above to be real to test)
  THERMAL-02:     Software thermal protection (needs current sensing from P2)

Phase 4 — Documentation + variant matrix (no code dep, do last)
  VARIANT-01/02:  Variant matrix docs (write when code is stable)
```

**Critical path**: CRSF → motor PWM → IMU → current → trim → failsafe.
Do not start failsafe testing before all nominal paths are validated.

---

## Integration Points

### Pi Zero 2W ↔ STM32F103 (implemented, production)

| Interface | Physical | Protocol | Direction | Notes |
|-----------|----------|----------|-----------|-------|
| SPI | 4-wire (SCK, MOSI, MISO, CS) + DATA_READY GPIO | `biba_proto` 64-byte frames | Pi master → STM32 slave | 50 Hz setpoint, 20 Hz telemetry |
| Power | Shared supply | — | — | 5V from BEC |

### Pi Zero 2W ↔ RP2040 (not yet implemented, same pattern as STM32)

RP2040 `target.h` already defines SPI slave pins (GP10–GP14) and `BIBA_TARGET_HAS_SPI_SLAVE=1`.
The integration point exists at the hardware level. Software path is:

1. Enable `mode_companion` build for `rpico_rp2040`
2. Implement RP2040 SPI slave handler (reuse STM32 companion mode as reference)
3. `biba-controller/stm32_link/` works unchanged on Pi side — same protocol, same Python codec

### RP2040 ↔ CRSF Receiver (Phase 1 target)

| Interface | Physical | Protocol | Direction |
|-----------|----------|----------|-----------|
| UART0 | GP0 (TX), GP1 (RX) | CRSF 420000 baud | Receiver → RP2040 |

Firmware CRSF driver (`drivers/crsf.c`) is written in C and target-agnostic via HAL.
RP2040 UART HAL needed: `biba_hal_uart_rp2040.c` implementing `biba_hal_uart_init()` /
`biba_hal_uart_read_byte()` — same signatures as STM32 HAL.

### RP2040 ↔ IMU (BMI160 / LSM6DS3)

| Interface | Physical | Protocol | Direction |
|-----------|----------|----------|-----------|
| I2C0 | GP20 (SDA), GP21 (SCL) | I2C 400 kHz | MCU master → IMU slave |

IMU driver (`drivers/imu.c`) currently STM32-HAL-backed. RP2040 needs `biba_hal_i2c_rp2040.c`.
Factory auto-detect pattern (WHO_AM_I probe) already exists — keep it.

### RP2040 ↔ BTS7960 (Phase 1 target)

| Interface | Physical | Notes |
|-----------|----------|-------|
| PWM | GP2/3 (Left), GP6/7 (Right) | RP2040 PWM slices 1+3; same slice → same carrier for both channels per side |

Key constraint from `target.h`: `BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM = 0`. L_RPWM and L_LPWM
share one PWM slice, so carrier frequency is identical. This matches BTS7960 requirements.
Different from STM32F103 which can run independent TIM channels.

### STM32F103 ↔ CRSF Receiver (implemented, standalone mode)

In standalone mode, STM32 reads CRSF directly on USART1. In companion mode, CRSF is owned by
the SBC. The `modes/mode_dispatcher.c` selects which UART owns CRSF at compile time via
`BIBA_MODE_STANDALONE` / `BIBA_MODE_COMPANION`.

---

## Gaps and Flags for Future Phases

| Gap | Impact | Recommended Action |
|-----|--------|-------------------|
| RP2040 `env_rp2040` base stanza not in `platformio.ini` | Blocks all RP2040 builds | Add `platform = raspberrypi` + pico-sdk stanza before RP2040-PORT work |
| No `biba_hal_uart_rp2040.c` | CRSF driver won't compile for RP2040 | Implement in HAL, same signature as STM32 HAL |
| No `biba_hal_i2c_rp2040.c` | IMU driver won't compile for RP2040 | Implement in HAL |
| `target_config.h` for RP2040 has no calibration values | IS pin ratio, VBAT divider untested | Measure from hardware, fill in before RP2040-PORT-04 |
| `SET_CONFIG` command stub in protocol, no payload struct | Calibration push from Pi to MCU not implemented | Define struct when RP2040 LittleFS persistence is added |
| No LittleFS / flash persistence on RP2040 | PID + trim lost on power cycle | Add in Phase 3 (before RP2040-PORT-05) |
