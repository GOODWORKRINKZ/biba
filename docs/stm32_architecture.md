# STM32F103 firmware architecture

Этот документ описывает firmware-проект `firmware/` для STM32F103C8T6
("Blue Pill") — опционального добавочного микроконтроллера к BiBa,
который умеет работать либо самостоятельно, либо как SPI-slave к основному
одноплатному компьютеру (Pi Zero 2W / Pi 5 / аналог).

## Зачем это нужно

1. Забрать у Pi hard-realtime задачи: CRSF на 420 000 бод с DMA, PWM для
   двух BTS7960 с dead-time, быстрый current-sense через штатный ADC.
2. Сохранить весь «умный» runtime на Linux: voice, web, телеметрия в
   сторону оператора, autonomy.
3. Дать возможность построить «urto-minimal» биобота без SBC — только
   STM32 + приёмник + два BTS7960.

## Два режима работы

### Standalone

Весь низкоуровневый стек живёт на STM32:

```
CRSF UART ──▶ парсер ──▶ mixer ──▶ heading-hold PID ──▶ limiter ──▶ PWM → BTS7960
                                                             ▲
                                      ADC1 circular DMA ─────┘
```

Pi (если вообще есть) подключается по желанию через SPI для сбора
телеметрии или как источник high-level команд.

### Companion

SBC — владелец setpoint-а; STM32 — "умный драйвер", который:

- принимает команды по SPI-slave,
- следит за current / power лимитами своим ADC,
- возвращает полную телеметрию на MISO,
- уходит в фейлсейф, если SPI молчит дольше `SPI_LINK_TIMEOUT_MS`.

CRSF опционально активен как локальный override / независимый
фейлсейф-канал.

### Combined

Единая прошивка, режим выбирается при старте по пину `MODE_SEL` (PB9,
pull-up; замыкание на GND = companion). Это позволяет одной прошивкой
закрывать обе сборки робота.

## Targets (Betaflight/ELRS-style)

Конкретная привязка пинов и per-board калибровка отделены от портируемой
логики — ровно как в Betaflight и ExpressLRS. Каждая аппаратная
конфигурация живёт в `firmware/targets/<TARGET>/`:

```
targets/<TARGET>/
├── target.h            # pin map + BIBA_TARGET_HAS_* feature flags
├── target_config.h     # per-board калибровка / лимиты
└── target.md           # документация борды
```

Портируемый код включает только `biba_board.h` и `biba_config.h` —
это тонкие shim'ы, которые через путь `-Itargets/<TARGET>` (инжектится
PlatformIO per-env) подтягивают `target.h` и `target_config.h` выбранной
борды. Никаких `#ifdef TARGET == …` в `src/`.

Каждая hardware-конфигурация собирается в комбинации с каждым режимом
(`<target>_<mode>`), давая матрицу сборки `T × M`. Сейчас
поставляются:

| Target            | Плата                                      |
| ----------------- | ------------------------------------------ |
| `BLUEPILL_F103C8` | Стоковая "Blue Pill" (reference)           |
| `BIBA_F103_REV_A` | Пример кастомного PCB (прототип Rev A)     |

Добавление нового target'а = одна новая директория + один `[target_*]`
блок в `platformio.ini`, без правок портируемого кода. Подробнее — в
[`firmware/targets/README.md`](../firmware/targets/README.md).

## Слои прошивки

```
┌──────────────────────────────────────────────────────────┐
│ modes/        mode_dispatcher.c, mode_{standalone,companion}.c │
├──────────────────────────────────────────────────────────┤
│ app/          control_loop (mixer, PID, limiter),        │
│               failsafe, telemetry                        │
├──────────────────────────────────────────────────────────┤
│ drivers/      bts7960, current_sense, voltage_sense,     │
│               crsf, imu, buzzer_motor                    │
├──────────────────────────────────────────────────────────┤
│ hal/          biba_hal: clock, GPIO, TIM1 PWM, ADC+DMA,  │
│               USART3+DMA, SPI2-slave+DMA, I2C1           │
├──────────────────────────────────────────────────────────┤
│ proto/        biba_proto.{h,c} — общий SPI wire format   │
└──────────────────────────────────────────────────────────┘
```

Слои `proto`, `app/control_loop`, `app/failsafe`, `drivers/crsf` — чистый
переносимый C. Они компилируются под хост в env `native_test` и имеют
Unity-тесты (`test/test_biba_proto/`, `test/test_control_loop/`,
`test/test_crsf/`), которые CI гоняет на каждый push.

Всё, что трогает регистры STM32, лежит в `hal/biba_hal.c` и исключается
из native-сборки через `build_src_filter` в `platformio.ini`.

## Распиновка

См. таблицу в [docs/wiring.md](wiring.md#подключение-stm32f103). Короткая
сводка привязок:

- **TIM1** — все 4 PWM-канала BTS7960 (PA8..PA11), один таймер ⇒ фазы
  синхронны, легко добавить dead-time.
- **ADC1** — circular DMA-скан PA0..PA6 (4 current + 2 voltage + 1
  резерв), 12 бит, 55.5 циклов sample time.
- **USART3** — CRSF на PB10/PB11, 420 000 бод, DMA1 Channel 3.
- **SPI2** — slave-линия к SBC на PB12..PB15, NSS hardware, DMA1 Ch4/Ch5.
- **I2C1** — IMU на PB6/PB7, 400 кГц.
- **SWJ** — JTAG отключается в `biba_hal_init()`, остаётся SW-DP;
  PB3/PB4/PA15 освобождаются под GPIO / enable-пины BTS7960.

USART1 намеренно не используется: его AF-пины PA9/PA10 занимают TIM1_CH2
и TIM1_CH3 для PWM.

## SPI wire protocol

Full-duplex обмен, каждая SPI-транзакция передаёт один 64-байтный кадр в
каждую сторону. STM32 всегда держит на MISO свежий telemetry snapshot,
поэтому у SBC нет необходимости делать отдельный "запрос телеметрии".

Раскладка кадра (64 байта):

| offset | size | field          | комментарий                      |
|-------:|-----:|----------------|----------------------------------|
|      0 |    2 | sync           | `0xBA 0xBB`                      |
|      2 |    1 | version        | `0x01` (константа `BIBA_PROTO_VERSION`) |
|      3 |    1 | cmd            | `biba_proto_cmd_t` / `biba_proto_tlm_t` |
|      4 |    1 | seq            | монотонный счётчик отправителя   |
|      5 |    1 | flags          | `BIBA_PROTO_FLAG_*`              |
|      6 |    1 | payload_len    | 0..54                            |
|      7 |    1 | reserved       | должен быть 0                    |
|   8–61 |   54 | payload        | команд-специфично                |
|     62 |    2 | crc16          | CRC-16/CCITT-FALSE по байтам 0..61 |

CRC — `CRC-16/CCITT-FALSE` (poly 0x1021, init 0xFFFF, no reflect, xorout 0).
Та же реализация живёт в Python в
[`biba-controller/stm32_link/protocol.py`](../biba-controller/stm32_link/protocol.py)
и оба имплементатора покрыты тестами с одинаковыми vector-ами.

### Основные команды (SBC → STM32)

| cmd  | имя              | payload                              |
|:----:|------------------|--------------------------------------|
| 0x01 | `PING`           | пустой                               |
| 0x10 | `SET_SETPOINT`   | `int16 left_q15, int16 right_q15`    |
| 0x11 | `GET_TELEMETRY`  | пустой                               |
| 0x20 | `ARM`            | пустой                               |
| 0x21 | `DISARM`         | пустой                               |
| 0x30 | `SET_CONFIG`     | TLV (резерв)                         |
| 0x40 | `PLAY_TONE`      | `uint16 freq_hz, uint16 duration_ms` |

### Телеметрия (STM32 → SBC)

`cmd = 0x82` (SNAPSHOT). Payload — упакованная структура
`biba_proto_telemetry_t` (48 байт): setpoint echo, измеренные токи в мА,
VBAT, 12V rail, gyro/accel в centi-deg/s и milli-g, CRSF RSSI/LQ/SNR,
флаги и uptime в миллисекундах.

### DATA_READY (PA12)

STM32 поднимает PA12 коротким импульсом после каждого нового ADC-скана.
SBC может навесить на этот пин GPIO-interrupt и опрашивать телеметрию
реактивно, без фиксированного 1 кГц polling.

### Failsafe

- **Companion**: если SPI молчит дольше `BIBA_SPI_LINK_TIMEOUT_MS`,
  PWM обнуляется, BTS7960 дизабл, флаг `BIBA_PROTO_FLAG_FAILSAFE`
  выставляется в каждой телеметрии.
- **Standalone**: если CRSF молчит дольше `BIBA_CRSF_TIMEOUT_MS`, PWM
  обнуляется, PID-интегратор сбрасывается.

## Интеграция с Pi-runtime

Python-клиент живёт в [`biba-controller/stm32_link/`](../biba-controller/stm32_link/):

- `protocol.py` — энкодинг/декодинг фреймов (без `spidev`, 100% портируемо).
- `client.py` — `STM32Link` — SPI-мастер поверх `spidev`.
- По умолчанию отключён через `STM32_LINK_ENABLED=0` в `config.py`, так
  что существующий GPIO-путь не трогается.

## Дерево файлов

```
firmware/
├── platformio.ini           # matrix: <target>_<mode>, плюс native_test
├── include/                 # thin shims -> targets/<TARGET>/target*.h
├── src/
│   ├── main.c
│   ├── proto/biba_proto.*   # общий SPI wire format
│   ├── app/                 # control_loop, failsafe, telemetry
│   ├── drivers/             # bts7960, current/voltage_sense, crsf, imu, buzzer_motor
│   ├── hal/biba_hal.*       # STM32Cube wrapper
│   └── modes/               # диспетчер + standalone / companion
├── targets/
│   ├── README.md            # how to add a new target
│   ├── BLUEPILL_F103C8/     # reference Blue Pill pinout
│   └── BIBA_F103_REV_A/     # пример кастомной PCB
└── test/
    ├── test_biba_proto/     # CRC16 + frame round-trip
    ├── test_control_loop/   # PID, лимитер, mixer, failsafe
    ├── test_crsf/           # CRC8, парсер, канальная упаковка
    └── test_support/        # общий shim для native / Unity
```

## Валидация

- **Host-side**: `pio test -e native_test` — 31 тест на CRC, парсер CRSF,
  парсер SPI-кадров, лимитер по току/мощности, PID anti-windup.
- **Сборочные env**: `pio run -e <target>_<mode>` для каждой пары
  `target × mode`. Все пары собираются в CI
  (`.github/workflows/G-Build-STM32F103.yml`), артефакт
  `biba-stm32f103-<target>-<mode>` (`firmware.bin` + `.elf`) прикрепляется
  к workflow run.
- **На железе**: ST-Link + `pio run -e <target>_<mode> -t upload`, далее
  сверка с Pi-реф behaviour (CRSF RSSI, PWM на осциллографе, current-sense
  против ADS1115).
