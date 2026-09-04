# Онбординг разработчика BiBa

Этот документ — короткая карта репозитория и текущих правил работы. Отдельного
`CONTRIBUTING.md`, `.editorconfig` или общей конфигурации форматтера в проекте
сейчас нет, поэтому ниже явно разделены проверяемые правила из CI и соглашения,
которые только следуют из структуры и истории Git.

## Где что лежит

- `biba-controller/` — Python-runtime для Raspberry Pi: CRSF, управление
  моторами, BMS, телеметрия, settings UI и звук.
- `firmware/` — единый PlatformIO-проект для STM32F103 и RP2040.
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
- `hal/` реализует этот фасад отдельно для STM32 и RP2040; код приложения не
  должен напрямую включать STM32Cube или Pico SDK.
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
| `BLUEPILL_F103C8` | Настоящий STM32F103C8, CRSF через USART3, SPI2 companion, четыре PWM на общем TIM1; независимый motor-audio недоступен | `bluepill_f103c8_{standalone,companion,combined}` |
| `BLUEPILL_F103C8_CLONE` | Клон с 8 КБ RAM и отдельным linker script; CRSF перенесён на USART2 из-за отсутствующего USART3, поэтому правые current-sense каналы недоступны и алиасованы на левые | `bluepill_f103c8_clone_{standalone,companion,combined}` |
| `BIBA_F103_REV_A` | Нераспаянный прототип custom PCB; четыре независимых PWM-таймера, другие калибровки тока/VBAT, поддержка motor-audio | `biba_f103_rev_a_{standalone,companion,combined}` |
| `RPICO_RP2040` | Текущий default: Arduino-Pico, CRSF UART0, SBC UART1, BTS7960, I2C и четыре ADC-канала; current/power limits временно выключены до аппаратной доработки | `rpico_rp2040_standalone`, `rpico_rp2040_companion`, `rpico_rp2040_is_poc` |
| `RPICO_RP2040_BLDC` | Альтернативный RP2040-таргет: пара BLDC через ODrive по CAN (MCP2515 на SPI0 GP16–19, INT=GP15); BTS7960 и native ADC-сheck отключены. Архитектура и обоснование — `docs/adr/0001-pico-bldc-target.md`. | `rpico_rp2040_bldc_{standalone,companion,combined}` |
| без target | Переносимые host-тесты | `native_test` |

`rpico_rp2040_standalone` указан как `default_envs`. RP2040 platform сейчас
задан локальным URI `file:///home/ros2/.platformio/platforms/rp2040`, поэтому
чистая машина без этого каталога не воспроизведёт сборку без предварительной
настройки platform package.

В документации есть drift, который нельзя принимать за контракт: несколько
старых разделов утверждают, что clone не имеет своей target-директории и
полностью повторяет Blue Pill; это уже не так. `RPICO_RP2040/target.md` также
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
pio run -e bluepill_f103c8_standalone
pio run -e biba_f103_rev_a_standalone
pio run -e rpico_rp2040_standalone
pio run -e rpico_rp2040_bldc_standalone    # BLDC/CAN variant
```

STM32 загружается через ST-Link (`pio run -e <env> -t upload`), RP2040 — через
`picotool`/BOOTSEL. Не прошивайте и не запускайте моторный тест без отдельного
hardware safety check; unit/build success не заменяет field validation.

CI делает следующее:

- `G-Build-Controller-Image.yml`: Ruff, ShellCheck, pytest и arm64 Docker build;
- `G-Build-STM32F103.yml`: `native_test` и матрица
  `{bluepill_f103c8,biba_f103_rev_a} x {standalone,companion,combined}`;
- `G-Build-All.yml`: на `main` сводит controller, STM32 и ROS2 image builds.

Clone и RP2040 env сейчас не входят в firmware CI-матрицу, поэтому их нужно
собирать явно перед PR. Для embedded-изменения минимальный набор —
`native_test` плюс каждый затронутый hardware env; для изменения wire protocol
добавляются соответствующие C и Python тесты.

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
  который заводит `RPICO_RP2040_BLDC` без переписывания существующего
  `RPICO_RP2040`.
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
