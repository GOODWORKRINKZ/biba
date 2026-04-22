# BiBa STM32F103 firmware

PlatformIO project for the STM32F103C8T6 ("Blue Pill") add-on that can run
BiBa either standalone or as an SPI slave to a Raspberry Pi.

## Build envs

| Env           | What it builds                                                     |
|---------------|--------------------------------------------------------------------|
| `standalone`  | STM32 owns CRSF + BTS7960 + limiter + heading-hold.                |
| `companion`   | STM32 acts as SPI slave; the SBC drives setpoints.                 |
| `combined`    | Both modes in one binary, selected at boot via the MODE_SEL pin.   |
| `native_test` | Host-side unit tests over the portable modules (no hardware).     |

Single source tree; the differences live in `#ifdef BIBA_MODE_*` guards
inside `src/modes/mode_dispatcher.c`.

## Build & flash

```bash
cd firmware/stm32f103

# build (pick one)
pio run -e standalone
pio run -e companion
pio run -e combined

# flash through ST-Link
pio run -e standalone -t upload

# run host-side unit tests
pio test -e native_test
```

CI builds all four envs on every push; the `.bin` artefacts are attached
to the workflow run — see `.github/workflows/G-Build-STM32F103.yml`.

## Layout

```
firmware/stm32f103/
├── platformio.ini
├── include/                # public headers (pins, config, version)
├── src/
│   ├── main.c              # tiny entrypoint, calls the mode dispatcher
│   ├── app/                # portable control-loop code (PID, limiter, telemetry)
│   ├── drivers/            # BTS7960, ADC-based current/voltage sense, CRSF, IMU, buzzer
│   ├── hal/                # STM32Cube wrapper (clocks, DMA, peripherals)
│   ├── modes/              # standalone / companion / dispatcher
│   └── proto/              # shared SPI wire format with the SBC
└── test/                   # Unity-based host tests for the portable modules
```

## Portable vs. STM32 code split

Everything under `src/app/` (minus `telemetry.c`), `src/drivers/crsf.*`,
and `src/proto/` is strict portable C with no HAL includes. Those modules
are unit-tested on the host under `pio test -e native_test`. The rest
(anything that pokes hardware or `stm32f1xx_hal.h`) is excluded from the
native env via `build_src_filter` in `platformio.ini`.

## SPI wire protocol

Documented in `docs/stm32_architecture.md`. The same format is implemented
on the SBC side in `biba-controller/stm32_link/protocol.py`; the version
constant in `include/biba_version.h` must match `PROTOCOL_VERSION` there.
