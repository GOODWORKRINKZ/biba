# Прошивка BiBa для RP2040

Проект PlatformIO для плат класса RP2040 (Raspberry Pi Pico-class), на
которых работает BiBa либо в standalone-режиме, либо в роли companion
при Raspberry Pi.

Проект использует **раскладку таргетов в стиле Betaflight/ELRS**: каждая
поддерживаемая аппаратная конфигурация — это отдельная директория в
[`targets/`](targets), а матрица сборки строится как `<target> × <режим>`.
Полное руководство «как добавить новый target» см. в
[`targets/README.md`](targets/README.md).

STM32-таргеты (Blue Pill / BIBA_F103_REV_A) удалены из проекта — они
больше не собираются и не поддерживаются.

## Матрица сборки

Имя env собирается как `<target_lowercase>_<mode>`. Поддерживается четыре режима:

| Режим         | Что собирается                                                       |
| ------------- | -------------------------------------------------------------------- |
| `standalone`  | RP2040 сам управляет CRSF + мотор-драйвером + лимитером + heading-hold. |
| `companion`   | RP2040 работает как slave, уставки приходят с SBC.                   |
| `combined`    | Оба режима в одном бинарнике, выбор при старте по пину MODE_SEL.     |
| `native_test` | Хостовые юнит-тесты переносимых модулей (без таргета).               |

Текущие таргеты — см. таблицу в [`targets/README.md`](targets/README.md#поддерживаемые-таргеты).

## Сборка и прошивка

```bash
cd firmware

# дефолтный env (RP2040_DC_BTS7960_PWM standalone)
pio run

# явный target × режим
pio run -e rp2040_dc_bts7960_pwm_standalone
pio run -e rp2040_dc_bts7960_pwm_companion

# BLDC/CAN вариант
pio run -e rp2040_bldc_odrive_can_standalone
pio run -e rp2040_bldc_odrive_can_companion
pio run -e rp2040_bldc_odrive_can_combined

# BLDC на ODrive по UART (ASCII)
pio run -e rp2040_bldc_odrive_uart_standalone
pio run -e rp2040_bldc_odrive_uart_companion
pio run -e rp2040_bldc_odrive_uart_combined

# BLDC на VESC (Flipsky dual FSESC) по CAN
pio run -e rp2040_bldc_vesc_can_standalone
pio run -e rp2040_bldc_vesc_can_companion
pio run -e rp2040_bldc_vesc_can_combined

# мост HotRC PWM → CRSF (отдельная Pico вместо ELRS-приёмника)
pio run -e rp2040_bridge_pwm2crsf

# прошивка через picotool
pio run -e rp2040_dc_bts7960_pwm_standalone -t upload

# хостовые юнит-тесты (не зависят от таргета)
pio test -e native_test
```

CI (`.github/workflows/G-Build-Firmware-Native-Tests.yml`) прогоняет
только `pio test -e native_test`; сборка под конкретный таргет в CI не
производится и делается локально.

## Раскладка проекта

```
firmware/
├── platformio.ini             # матрица env'ов target × режим
├── include/                   # тонкие шимы -> targets/<TARGET>/target*.h
├── src/
│   ├── main_rp2040.cpp        # точка входа Arduino (setup/loop), вызывает диспетчер режимов
│   ├── app/                   # переносимая логика контроля (PID, лимитер, телеметрия)
│   ├── drivers/               # мотор-драйверы, ADC, CRSF, IMU, MCP2515/CAN, ODrive
│   ├── hal/                   # обёртка над RP2040/Pico SDK (тактирование, DMA, периферия)
│   ├── modes/                 # standalone / companion / диспетчер
│   └── proto/                 # общий с SBC формат кадров
├── targets/
│   ├── README.md              # как добавить новый таргет
│   ├── RP2040_DC_BTS7960_PWM/    # {target.h, target_config.h, target.md}
│   ├── RP2040_BLDC_ODRIVE_CAN/   # BLDC: ODrive по CAN (MCP2515)
│   ├── RP2040_BLDC_ODRIVE_UART/  # BLDC: ODrive по UART1 ASCII
│   ├── RP2040_BLDC_VESC_CAN/     # BLDC: Flipsky dual FSESC по CAN
│   └── RP2040_BRIDGE_PWM2CRSF/   # мост HotRC 6×PWM → CRSF (src/pwm2crsf/)
└── test/                      # хостовые тесты на Unity для переносимых модулей
```

## Разделение переносимого и таргет-специфичного кода

Всё в `src/app/` (кроме `telemetry.c`), `src/drivers/crsf.*` и
`src/proto/` — это строго переносимый C без include'ов HAL и без
зависимости от `target.h`. Эти модули покрыты юнит-тестами на хосте
через `pio test -e native_test`. Остальное (всё, что лезет в железо
или включает Pico SDK / Arduino-заголовки) исключается из native env
через `build_src_filter` в `platformio.ini`.

Аппаратный код подключает `biba_board.h` (шим распиновки) и
`biba_config.h` (политика + переопределения таргета); оба заголовка
резолвят `target.h` / `target_config.h` через путь `-I targets/<TARGET>`,
который PlatformIO добавляет в каждом env.

## Протокол SPI

Описан в [`docs/stm32_architecture.md`](../docs/stm32_architecture.md).
Тот же формат реализован на стороне SBC в
`biba-controller/stm32_link/protocol.py`; константа версии в
`include/biba_version.h` обязана совпадать с `PROTOCOL_VERSION` там.
