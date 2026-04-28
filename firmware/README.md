# Прошивка BiBa для STM32F103

Проект PlatformIO для платы класса STM32F103C8T6, на которой работает
BiBa либо в standalone-режиме, либо в роли SPI-slave при Raspberry Pi.

Проект использует **раскладку таргетов в стиле Betaflight/ELRS**: каждая
поддерживаемая аппаратная конфигурация — это отдельная директория в
[`targets/`](targets), а матрица сборки строится как `<target> × <режим>`.
Полное руководство «как добавить новый target» см. в
[`targets/README.md`](targets/README.md).

## Матрица сборки

Имя env собирается как `<target_lowercase>_<mode>`. Поддерживается четыре режима:

| Режим         | Что собирается                                                       |
| ------------- | -------------------------------------------------------------------- |
| `standalone`  | STM32 сам управляет CRSF + BTS7960 + лимитером + heading-hold.       |
| `companion`   | STM32 работает как SPI-slave, уставки приходят с SBC.                |
| `combined`    | Оба режима в одном бинарнике, выбор при старте по пину MODE_SEL.     |
| `native_test` | Хостовые юнит-тесты переносимых модулей (без таргета).               |

Текущие таргеты:

| Target                  | Плата                                                       |
| ----------------------- | ----------------------------------------------------------- |
| `BLUEPILL_F103C8`       | Эталон: серийный STM32F103C8T6 «Blue Pill» (20 КБ ОЗУ)      |
| `BLUEPILL_F103C8_CLONE` | Тот же распиновка, но клон-чип с реальными 8 КБ ОЗУ         |
| `BIBA_F103_REV_A`       | Пример кастомной платы (прототип ревизии A)                 |

Вариант `_CLONE` — это **не** отдельная директория в `targets/`. Он
переиспользует распиновку обычного Blue Pill и отличается только
скриптом линкера и лимитом RAM в PlatformIO, чтобы бинарник помещался в
урезанный кристалл. Сейчас на стенде стоит именно клон, поэтому
`bluepill_f103c8_clone_standalone` — это `default_envs` проекта.

## Сборка и прошивка

```bash
cd firmware

# дефолтный стендовый env (клон-чип, линкер на 8 КБ ОЗУ)
pio run

# явный target × режим
pio run -e bluepill_f103c8_standalone
pio run -e bluepill_f103c8_companion
pio run -e bluepill_f103c8_combined

# варианты для клон-чипа (8 КБ ОЗУ)
pio run -e bluepill_f103c8_clone_standalone
pio run -e bluepill_f103c8_clone_companion
pio run -e bluepill_f103c8_clone_combined

# кастомная плата
pio run -e biba_f103_rev_a_standalone

# прошивка через ST-Link
pio run -e bluepill_f103c8_clone_standalone -t upload

# хостовые юнит-тесты (не зависят от таргета)
pio test -e native_test
```

CI (`.github/workflows/G-Build-STM32F103.yml`) собирает каждую пару
`(target, mode)` и публикует артефакты `firmware.bin` / `firmware.elf`
с именем `biba-stm32f103-<target>-<mode>`.

## Раскладка проекта

```
firmware/
├── platformio.ini             # матрица env'ов target × режим
├── ldscripts/                 # кастомные линкер-скрипты (например, 8 КБ ОЗУ для клона)
├── include/                   # тонкие шимы -> targets/<TARGET>/target*.h
├── src/
│   ├── main.c                 # минимальная точка входа, вызывает диспетчер режимов
│   ├── app/                   # переносимая логика контроля (PID, лимитер, телеметрия)
│   ├── drivers/               # BTS7960, токовый/вольтовый ADC, CRSF, IMU
│   ├── hal/                   # обёртка над STM32Cube (тактирование, DMA, периферия)
│   ├── modes/                 # standalone / companion / диспетчер
│   └── proto/                 # общий с SBC формат SPI-кадров
├── targets/
│   ├── README.md              # как добавить новый таргет
│   ├── BLUEPILL_F103C8/       # {target.h, target_config.h, target.md}
│   └── BIBA_F103_REV_A/       # пример кастомной платы
└── test/                      # хостовые тесты на Unity для переносимых модулей
```

## Разделение переносимого и STM32-кода

Всё в `src/app/` (кроме `telemetry.c`), `src/drivers/crsf.*` и
`src/proto/` — это строго переносимый C без include'ов HAL и без
зависимости от `target.h`. Эти модули покрыты юнит-тестами на хосте
через `pio test -e native_test`. Остальное (всё, что лезет в железо
или включает `stm32f1xx_hal.h`) исключается из native env через
`build_src_filter` в `platformio.ini`.

Аппаратный код подключает `biba_board.h` (шим распиновки) и
`biba_config.h` (политика + переопределения таргета); оба заголовка
резолвят `target.h` / `target_config.h` через путь `-I targets/<TARGET>`,
который PlatformIO добавляет в каждом env.

## Протокол SPI

Описан в [`docs/stm32_architecture.md`](../../docs/stm32_architecture.md).
Тот же формат реализован на стороне SBC в
`biba-controller/stm32_link/protocol.py`; константа версии в
`include/biba_version.h` обязана совпадать с `PROTOCOL_VERSION` там.
