# BiBa STM32F103 firmware

PlatformIO project for the STM32F103C8T6-class add-on that runs BiBa
either standalone or as an SPI slave to a Raspberry Pi.

The project uses a **Betaflight/ELRS-style target layout**: each
supported hardware configuration is one directory under
[`targets/`](targets), and the build matrix is `<target> × <mode>`. See
[`targets/README.md`](targets/README.md) for the full "how to add a new
target" guide.

## Build matrix

Envs are named `<target_lowercase>_<mode>`. There are three modes:

| Mode          | What it builds                                                   |
| ------------- | ---------------------------------------------------------------- |
| `standalone`  | STM32 owns CRSF + BTS7960 + limiter + heading-hold.              |
| `companion`   | STM32 acts as SPI slave; the SBC drives setpoints.               |
| `combined`    | Both modes in one binary, selected at boot via the MODE_SEL pin. |
| `native_test` | Host-side unit tests over the portable modules (no target).      |

Current targets:

| Target            | Board                                         |
| ----------------- | --------------------------------------------- |
| `BLUEPILL_F103C8` | Reference: stock STM32F103C8T6 "Blue Pill"    |
| `BIBA_F103_REV_A` | Example custom PCB (prototype revision A)     |

## Build & flash

```bash
cd firmware

# build (target × mode)
pio run -e bluepill_f103c8_standalone
pio run -e bluepill_f103c8_companion
pio run -e bluepill_f103c8_combined

# or the custom PCB
pio run -e biba_f103_rev_a_standalone

# flash through ST-Link
pio run -e bluepill_f103c8_standalone -t upload

# run host-side unit tests (target-independent)
pio test -e native_test
```

CI (`.github/workflows/G-Build-STM32F103.yml`) builds every
`(target, mode)` pair and attaches `firmware.bin` / `firmware.elf`
artefacts named `biba-stm32f103-<target>-<mode>`.

## Layout

```
firmware/
├── platformio.ini             # target × mode env matrix
├── include/                   # thin shims -> targets/<TARGET>/target*.h
├── src/
│   ├── main.c                 # tiny entrypoint, calls the mode dispatcher
│   ├── app/                   # portable control-loop code (PID, limiter, telemetry)
│   ├── drivers/               # BTS7960, ADC-based current/voltage sense, CRSF, IMU, buzzer
│   ├── hal/                   # STM32Cube wrapper (clocks, DMA, peripherals)
│   ├── modes/                 # standalone / companion / dispatcher
│   └── proto/                 # shared SPI wire format with the SBC
├── targets/
│   ├── README.md              # how to add a new target
│   ├── BLUEPILL_F103C8/       # {target.h, target_config.h, target.md}
│   └── BIBA_F103_REV_A/       # example custom PCB
└── test/                      # Unity-based host tests for the portable modules
```

## Portable vs. STM32 code split

Everything under `src/app/` (minus `telemetry.c`), `src/drivers/crsf.*`,
and `src/proto/` is strict portable C with no HAL includes and no
dependency on `target.h`. Those modules are unit-tested on the host
under `pio test -e native_test`. The rest (anything that pokes hardware
or `stm32f1xx_hal.h`) is excluded from the native env via
`build_src_filter` in `platformio.ini`.

Hardware-facing code includes `biba_board.h` (pin shim) and
`biba_config.h` (policy + target overrides); both headers resolve the
per-target `target.h` / `target_config.h` via the `-I targets/<TARGET>`
path PlatformIO injects per env.

## SPI wire protocol

Documented in [`docs/stm32_architecture.md`](../../docs/stm32_architecture.md).
The same format is implemented on the SBC side in
`biba-controller/stm32_link/protocol.py`; the version constant in
`include/biba_version.h` must match `PROTOCOL_VERSION` there.
