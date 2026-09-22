# Онбординг разработчика BiBa

Этот документ — короткая карта репозитория и текущих правил работы. Отдельного
`CONTRIBUTING.md`, `.editorconfig` или общей конфигурации форматтера в проекте
сейчас нет, поэтому ниже явно разделены проверяемые правила из CI и соглашения,
которые только следуют из структуры и истории Git.

## Где что лежит

- `biba-controller/` — Python-runtime для Raspberry Pi: CRSF, управление
  моторами, BMS, телеметрия, settings UI и звук.
- `firmware/` — единый PlatformIO-проект для RP2040 (STM32F103-таргеты удалены).
- `firmware/targets/` — распиновка, возможности и калибровки конкретных плат.
- `firmware/test/` — host-side Unity-тесты переносимого C-кода.
- `tests/` — pytest-тесты Python-runtime, скриптов, протокола и ROS2-файлов.
- `ros2_ws/` — ROS2-пакеты будущей композиции Pi + MCU.
- `docker/legacy-pi/` — текущий production compose для Pi-only; `docker/ros2/`
  и `docker/base/` — развиваемый ROS2-стек и его базовые образы.
- `scripts/` — bringup, диагностика, обновление робота и инженерные захваты.
- `docs/` — архитектура, wiring, deployment, field validation и design-планы.
- `.planning/` — roadmap и рабочие требования RP2040-порта.
- `.github/workflows/` — реальные автоматические quality gates.

Общий обзор начинайте с `README.md`, embedded-часть — с
`firmware/platformio.ini`, `firmware/README.md` и `firmware/targets/README.md`.
Для общей картины системных композиций смотрите `docs/system_architecture.md`.

## Архитектура прошивки

Поток управления выглядит так:

```text
main.c / main_rp2040.cpp
        -> modes/mode_dispatcher.c
        -> modes/mode_standalone.c | mode_companion.c
        -> app/ -> drivers/ -> hal/
                     |          |
                  proto/     targets/<TARGET>/
```

- `modes/` компонует runtime. `standalone` сам читает CRSF, держит failsafe,
  рассчитывает команды и управляет приводом. `companion` получает setpoint от
  SBC и возвращает телеметрию; текущая реализация этого режима SPI-центрична.
  `combined` выбирает один из режимов по `MODE_SEL` при старте.
- `app/` содержит переиспользуемые алгоритмы: mixer/PID/лимитирование,
  failsafe, ramp, RPM PI, спектральную и zero-crossing оценку RPM, телеметрию.
- `drivers/` содержит CRSF, BTS7960, current/voltage sense, IMU, ADS1115 и
  AHT30. Драйвер обращается к железу через фасад `hal/biba_hal.h`.
- `hal/` реализует этот фасад для RP2040; код приложения не должен напрямую
  включать Pico SDK.
- `proto/` задаёт фиксированный 64-байтный SBC/MCU wire format. Его версия и
  раскладка должны оставаться согласованы с
  `biba-controller/stm32_link/protocol.py`.
- `include/biba_board.h` и `include/biba_config.h` — единственные штатные
  входы к target-specific распиновке и настройкам. `target_config.h` имеет
  приоритет над guarded defaults из `biba_config.h`.

Важно: текущая target-модель выбирает плату, пины и калибровки, но не является
полной абстракцией типа привода. `mode_*` и dispatcher прямо используют
`bts7960`, а HAL экспортирует PWM API для коллекторного привода. Новый BLDC/CAN
вариант потребует отдельной границы motor backend (и выбора исходников при
сборке), а не только нового `target.h`.

## Существующие targets и env

Фактический источник истины — `firmware/platformio.ini` вместе с
`firmware/targets/*/target.h`:

| Target | Назначение и отличия | Env |
| --- | --- | --- |
| `RP2040_DC_BTS7960_PWM` | Текущий default: Arduino-Pico, CRSF UART0, SBC UART1, BTS7960, I2C и четыре ADC-канала; current/power limits временно выключены до аппаратной доработки | `rp2040_dc_bts7960_pwm_standalone`, `rp2040_dc_bts7960_pwm_companion`, `rp2040_dc_bts7960_pwm_is_poc` |
| `RP2040_BLDC_ODRIVE_CAN` | Пара BLDC через ODrive по CAN (MCP2515 на SPI0 GP16–19, INT=GP15), 250 кбит/с, CANSimple 11-bit; BTS7960 и native ADC отключены. Архитектура — `docs/adr/0001-pico-bldc-target.md`. | `rp2040_bldc_odrive_can_{standalone,companion,combined}` |
| `RP2040_BLDC_ODRIVE_UART` | Те же ODrive, но по ASCII-протоколу на UART1 (GP4/GP5). Без MCP2515. Сейчас предпочтительный production-линк: CANSimple в прошивке ODrive 0.5.6 залипает на холостом ходу. | `rp2040_bldc_odrive_uart_{standalone,companion,combined}` |
| `RP2040_BLDC_VESC_CAN` | Пара BLDC через Flipsky dual FSESC (спаренный VESC) по CAN на том же MCP2515-мосту: 500 кбит/с, 29-bit extended ID, big-endian. Требует настройки VESC Tool (VESC ID 0/1, CAN status messages). Детали — `docs/adr/0002-target-naming-and-vesc.md`. | `rp2040_bldc_vesc_can_{standalone,companion,combined}` |
| без target | Переносимые host-тесты | `native_test` |

STM32F103-таргеты (`BLUEPILL_F103C8`, `BLUEPILL_F103C8_CLONE`,
`BIBA_F103_REV_A`) удалены из проекта — прошивка под STM32 больше не
собирается и не поддерживается.

`rp2040_dc_bts7960_pwm_standalone` указан как `default_envs`. RP2040 platform сейчас
задан локальным URI `file:///home/ros2/.platformio/platforms/rp2040`, поэтому
чистая машина без этого каталога не воспроизведёт сборку без предварительной
настройки platform package.

В документации есть drift, который нельзя принимать за контракт: несколько
старых разделов утверждают, что clone не имеет своей target-директории и
полностью повторяет Blue Pill; это уже не так. `RP2040_DC_BTS7960_PWM/target.md` также
называет board id `rpipico`, тогда как текущий env использует
`vccgnd_yd_rp2040`. Перед проектированием нового target сверяйтесь с INI и
заголовками, затем обновляйте документацию вместе с кодом.

## Сборка и проверки

Базовые локальные команды:

```bash
pip install -r requirements-dev.txt
ruff check biba-controller/ tests/
pytest
shellcheck scripts/*.sh scripts/setup/*.sh

cd firmware
pio test -e native_test
pio run -e rp2040_dc_bts7960_pwm_standalone
pio run -e rp2040_bldc_odrive_can_standalone    # BLDC: ODrive по CAN
pio run -e rp2040_bldc_odrive_uart_standalone   # BLDC: ODrive по UART
pio run -e rp2040_bldc_vesc_can_standalone      # BLDC: VESC по CAN
```

RP2040 прошивается через `picotool`/BOOTSEL (`pio run -e <env> -t upload`). Не
прошивайте и не запускайте моторный тест без отдельного hardware safety
check; unit/build success не заменяет field validation.

CI делает следующее:

- `G-Build-Controller-Image.yml`: Ruff, ShellCheck, pytest и arm64 Docker build;
- `G-Build-Firmware-Native-Tests.yml`: только `native_test` (портируемый код,
  без сборки под конкретный таргет);
- `G-Build-All.yml`: на `main` сводит controller, firmware native tests и
  ROS2 image builds.

RP2040 env'ы сейчас не входят в firmware CI-матрицу (сборка под конкретный
таргет в CI не производится), поэтому их нужно собирать явно перед PR. Для
embedded-изменения минимальный набор — `native_test` плюс каждый затронутый
hardware env; для изменения wire protocol добавляются соответствующие C и
Python тесты.

## Конвенции кода и targets

- C: GNU11, `-Wall -Wextra` (portable env также `-Wpedantic`), 4 пробела,
  opening brace на следующей строке, `snake_case`, публичный префикс `biba_`,
  include guards `BIBA_*_H`, константы/target ABI в `BIBA_*`.
- Hardware-specific код остаётся в `hal/` и `targets/`; переносимые алгоритмы
  не включают `target.h` напрямую и получают Unity-тест в `firmware/test/`.
- Новый target именуется `SCREAMING_SNAKE` и обычно содержит `target.h`,
  `target_config.h`, `target.md`. Регистрация env делается в
  `platformio.ini`; CI-матрица и таблицы targets обновляются в том же PR.
  Пример добавления полностью нового target с собственным motor backend
  (MCP2515, ODrive) — коммит ADR-0001 (`docs/adr/0001-pico-bldc-target.md`),
  который заводит `RP2040_BLDC_ODRIVE_CAN` без переписывания существующего
  `RP2040_DC_BTS7960_PWM`.
- Не добавляйте target-ветвления лесенкой в portable `src/`: возможности
  описываются `BIBA_TARGET_HAS_*`, пины — target ABI, политика/калибровки —
  `target_config.h` с fallback в `biba_config.h`.
- Python проверяется Ruff и pytest; тесты именуются `tests/test_*.py`.
- Документация в основном русскоязычная. Изменение wiring, env, протокола или
  field status считается незавершённым без синхронного обновления docs.

## Ветки, коммиты и Pull Request

Формальной policy нет. Наблюдаемая схема последних изменений: тематические
ветки (`feature/...`, иногда `feat/...` или milestone-имя) интегрируются в
`develop`, затем `develop` вливается PR-ом в `main`. Перед началом уточните
base у владельца; для новой BLDC-работы ожидается отдельная feature-ветка, а
не прямое изменение `main`.

Рекомендуемый цикл:

1. Обновить выбранную base-ветку и создать `feature/<short-topic>`.
2. Делать небольшие тематические коммиты. В истории преобладает Conventional
   Commits: `feat(scope): ...`, `fix(scope): ...`, `docs(scope): ...`,
   `test(scope): ...`, `refactor(scope): ...`.
3. Перед push выполнить локальные проверки для всех затронутых слоёв/env.
4. Открыть PR в `develop` (если владелец не указал другую base), описать
   hardware assumptions, затронутые targets, test plan и результаты.
5. Не считать embedded-функцию готовой только по CI: явно вынести в PR
   необходимые bench/field проверки, распиновку и безопасное состояние при
   boot/failsafe.

Production-робот обновляется из репозитория штатным `bbupdate`; локальные
правки на роботе в обход Git/PR делают развёртывание невоспроизводимым.
