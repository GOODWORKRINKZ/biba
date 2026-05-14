# BiBa

[![Build All](https://github.com/GOODWORKRINKZ/biba/actions/workflows/G-Build-All.yml/badge.svg?branch=main)](https://github.com/GOODWORKRINKZ/biba/actions/workflows/G-Build-All.yml)
[![Build Controller Image](https://github.com/GOODWORKRINKZ/biba/actions/workflows/G-Build-Controller-Image.yml/badge.svg?branch=main)](https://github.com/GOODWORKRINKZ/biba/actions/workflows/G-Build-Controller-Image.yml)

<p align="center">
   <img src="docs/biba-logo-gradient.svg" alt="BiBa gradient ASCII logo" width="760">
</p>

BiBa — это колесная робот-платформа с управлением по ExpressLRS/CRSF, телеметрией от Daly 6S BMS по BLE или USB-UART, двухканальными драйверами BTS7960 и звуковой индикацией через моторы. Платформа поддерживает три композиции железа — от чисто-Pi-варианта до связки одноплатник + STM32F103, поэтому репозиторий организован как hub: общие компоненты живут рядом, а сборки разводятся по подкаталогам.

## Архитектура

BiBa поддерживает три композиции железа. Где есть STM32 — именно он принимает CRSF и держит failsafe; одноплатник, если присутствует, работает как high-level brain поверх SPI-канала к STM32.

| Композиция | SBC (Raspberry Pi) | MCU add-on | Кто слушает CRSF | Compose / прошивка |
| --- | --- | --- | --- | --- |
| **A. Pi-only** (текущий продакшен) | да | нет | Pi (`/dev/ttyS0`) | [`docker/legacy-pi/docker-compose.yml`](docker/legacy-pi/docker-compose.yml) |
| **B. STM32-only** | нет | STM32F103 | STM32 | env `standalone` в [`firmware/`](firmware/) |
| **C. Pi + STM32** | да | STM32F103 | STM32 (Pi видит каналы через SPI-телеметрию) | env `companion` в [`firmware/`](firmware/) + ROS2-стек в `docker/ros2/` (в разработке) |
| **D. RP2040-only** (в разработке, ветка `rp2040-port`) | нет | RP2040 | RP2040 | env `rpico_rp2040_standalone` в [`firmware/`](firmware/) |

Канонический разбор композиций, их обязанности и failsafe-уровни — в [docs/system_architecture.md](docs/system_architecture.md). STM32-сторона детально описана в [docs/stm32_architecture.md](docs/stm32_architecture.md), будущий ROS2-стек композиции C — в [docs/ros2_stack.md](docs/ros2_stack.md). Общий design-doc и план редизайна — [docs/plans/2026-04-28-sbc-architecture-redesign-design.md](docs/plans/2026-04-28-sbc-architecture-redesign-design.md).

## Состав железа

- Raspberry Pi Zero 2W
- ELRS-приемник с подключением по UART/CRSF
- Daly BMS по BLE или с USB-UART адаптером
- 6S аккумулятор с телеметрией BMS
- Два драйвера BTS7960 для левого и правого моторов
- ADS1115 для current sense и телеметрии токов колёс (опционально)

## Распиновка

| Назначение | BCM | Физический пин |
| --- | --- | --- |
| ELRS TX | 14 | 8 |
| ELRS RX | 15 | 10 |
| I2C SDA (ADS1115, опционально) | 2 | 3 |
| I2C SCL (ADS1115, опционально) | 3 | 5 |
| Left BTS7960 RPWM | 12 | 32 |
| Left BTS7960 LPWM | 18 | 12 |
| Left BTS7960 REN | 23 | 16 |
| Left BTS7960 LEN | 24 | 18 |
| Right BTS7960 RPWM | 19 | 35 |
| Right BTS7960 LPWM | 13 | 33 |
| Right BTS7960 REN | 20 | 38 |
| Right BTS7960 LEN | 21 | 40 |
| GND драйвера | - | 14 |

Распиновка и таблица выше актуальны для композиции A (Pi-only). Для композиций B/C wiring между Pi, STM32 и силовой частью описан в [docs/wiring.md](docs/wiring.md) и [docs/stm32_architecture.md](docs/stm32_architecture.md).

Подробное описание подключения находится в [docs/wiring.md](docs/wiring.md).

Опциональная прошивка для STM32F103 ("Blue Pill") add-on, который умеет работать либо самостоятельно, либо SPI-slave-ом к Pi, живёт в [`firmware/`](firmware/). Архитектура описана в [docs/stm32_architecture.md](docs/stm32_architecture.md).

Текущий двухмоторный runtime на Pi Zero 2W должен быть запущен с `BTS7960_PWM_MODE=SOFTWARE`, потому что распиновка `12/18` и `19/13` делит общие hardware-PWM каналы. Это уже совпадает и с кодовым default в `config.py`, и с compose-default для развёрнутого робота.

## Структура репозитория

- `biba-controller/` — Python-контроллер для CRSF, моторов, моторного audio/voice runtime и телеметрии BMS (композиции A и C)
- `biba-controller/stm32_link/` — опциональный SPI-клиент к STM32F103 add-on (`STM32_LINK_ENABLED=1`, композиция C)
- `firmware/` — PlatformIO-проект прошивки (STM32F103C8T6 и RP2040): env'ы `standalone` для композиции B, `companion` для композиции C, `rpico_rp2040_standalone` для композиции D (ветка `rp2040-port`), `native_test` для host-side Unity-тестов
- `docker/` — каталог compose-стеков, разнесённых по композициям:
  - `docker/legacy-pi/` — текущий продакшен-стек композиции A
  - `docker/ros2/` — будущий ROS2-стек композиции C (в разработке)
  - `docker/base/` — общие базовые образы (в разработке)
- `lua/SCRIPTS/TELEMETRY/biba.lua` — экран телеметрии EdgeTX для оператора
- `.github/workflows/` — global builder workflows для Ruff, pytest, shellcheck и сборки arm64 Docker-образа в GHCR
- `scripts/setup/` — bringup-скрипты для Raspberry Pi (Docker, Compose, systemd-автозапуск)
- `scripts/biba_aliases.sh` — robot-side operational aliases, включая `bbupdate` для штатного обновления
- `scripts/diagnostics.sh` — диагностика хоста и контейнера
- `scripts/voice_prep.py` — офлайн-подготовка русскоязычных voice assets и явный promote в production voice каталог
- `voice-src/phrases.yml` — канонический набор русских фраз по событиям
- `voice-work/` — staging-каталог для сгенерированных кандидатов перед promote в production voice каталог
- `docs/deployment.md` — руководство по развёртыванию по композициям
- `docs/system_architecture.md` — канонический обзор всех трёх композиций
- `.agents/skills/` — вендорный каталог skills

## Quick-start по композициям

- **Композиция A (Pi-only).** Сегодняшний bringup-скрипт и compose-стек. Полный гайд: [docs/deployment.md](docs/deployment.md#композиция-a-pi-only).
- **Композиция B (STM32-only).** Без одноплатника. Сборка и заливка прошивки описаны в [firmware/README.md](firmware/README.md) и [docs/stm32_architecture.md](docs/stm32_architecture.md).
- **Композиция C (Pi + STM32).** В разработке. Проектная картина — в [design-doc](docs/plans/2026-04-28-sbc-architecture-redesign-design.md) и [docs/ros2_stack.md](docs/ros2_stack.md).

Дальше по тексту разделы про подготовку Pi, env-переменные, settings UI и motor trim относятся к композиции A.

## Подготовка Raspberry Pi (композиция A)

1. Включите UART на Raspberry Pi.
2. Освободите основной UART от Bluetooth, добавив в конфигурацию:

   ```ini
   enable_uart=1
   dtoverlay=disable-bt
   ```

3. Перезагрузите Raspberry Pi.
4. Настройте Daly BMS по BLE или подключите USB-UART адаптер, если используете UART-вариант.
5. Если используете ADS1115 для current sense, включите I2C и проверьте наличие `/dev/i2c-1`.

Вместо ручной установки Docker/Compose можно использовать bringup-скрипт:

```bash
curl -fsSL https://raw.githubusercontent.com/GOODWORKRINKZ/biba/main/scripts/setup/setup_node.sh | bash
```

Скрипт:

- ставит Docker и Docker Compose plugin
- ставит базовые системные утилиты
- клонирует или обновляет репозиторий в `~/biba`
- настраивает алиасы для управления стеком
- создает `systemd` unit для автозапуска `docker compose`

## Запуск (композиция A)

Компоновка стека лежит в [`docker/legacy-pi/docker-compose.yml`](docker/legacy-pi/docker-compose.yml). На роботе все стандартные действия выполняются через `bb*`-aliases из [`scripts/biba_aliases.sh`](scripts/biba_aliases.sh) (`bbupdate`, `bbstart`, `bbstop`, `bblogs`, `bbpull`).

Если удобно работать без алиасов — указывайте compose-файл явно:

```bash
docker compose -f docker/legacy-pi/docker-compose.yml pull
docker compose -f docker/legacy-pi/docker-compose.yml up -d
```

Локальная сборка:

```bash
docker compose -f docker/legacy-pi/docker-compose.yml build
docker compose -f docker/legacy-pi/docker-compose.yml up -d
```

Путь к compose-файлу можно переопределить переменной `BIBA_COMPOSE_FILE` для скриптов и алиасов.

Контейнер запускает `pigpiod`, слушает ELRS CRSF кадры на `/dev/ttyS0`, управляет моторами, опрашивает Daly BMS по BLE или на `/dev/ttyUSB0` и отправляет батарейную телеметрию обратно на передатчик.

Docker-образ собирается под `linux/arm64`, чтобы совпадать с Raspberry Pi Zero 2W. Для этого `pigpiod` собирается внутри образа из upstream `pigpio`, так как готовый пакет `pigpio` отсутствует в Debian bookworm arm64.

## Конфигурация и переменные окружения (композиция A)

Все env-переменные ниже применяются к compose-стеку композиции A в [`docker/legacy-pi/docker-compose.yml`](docker/legacy-pi/docker-compose.yml). Тип драйвера и распиновку можно переопределить через них:

- `MOTOR_DRIVER_TYPE=BTS7960|PWM_DIR`
- `BTS7960_PWM_MODE=HARDWARE|SOFTWARE` — для Pi Zero 2W с текущей двухмоторной проводкой нужен `SOFTWARE`
- `PWM_FREQUENCY_HZ=20000` — частота software PWM; актуально только при `BTS7960_PWM_MODE=SOFTWARE`
- `LEFT_MOTOR_RPWM=12`
- `LEFT_MOTOR_LPWM=18`
- `LEFT_MOTOR_REN=23`
- `LEFT_MOTOR_LEN=24`
- `LEFT_MOTOR_ENABLED=1` — отключить левый мотор целиком (для отладки)
- `RIGHT_MOTOR_RPWM=19`
- `RIGHT_MOTOR_LPWM=13`
- `RIGHT_MOTOR_REN=20`
- `RIGHT_MOTOR_LEN=21`
- `RIGHT_MOTOR_ENABLED=1` — отключить правый мотор целиком (для отладки)
- `MOTOR1_INVERTED=0|1`
- `MOTOR2_INVERTED=0|1`
- `CRSF_BAUD=420000` — скорость UART для CRSF-приёмника (менять не нужно для стандартного ELRS)
- `ARM_THRESHOLD=0.3` — нормализованный порог CH_ARM для арминга
- `THROTTLE_FILTER_MODE=NONE|KALMAN` — фильтрация газа до wheel-mix; `NONE` по умолчанию, `KALMAN` сглаживает выбросы канала
- `THROTTLE_KALMAN_PROCESS_NOISE=0.02` — насколько быстро фильтр принимает изменения реального setpoint
- `THROTTLE_KALMAN_MEASUREMENT_NOISE=0.5` — насколько сильно фильтр подавляет шум и ложные выбросы канала
- `CH_SPEED_MODE=5` — `CH6` на передатчике; трёхпозиционный селектор скоростного режима для controller-side scaling газа и руля
- `CH_DRIVE_MODE=6` — `CH7` на передатчике; селектор режимов движения: `manual` и `stabilized`
- `DRIVE_MODE_LOW_THRESHOLD=-0.3`, `DRIVE_MODE_HIGH_THRESHOLD=0.3` — пороги переключения drive mode аналогично speed mode
- `SPEED_MODE_LOW_THRESHOLD=-0.3` — нижний порог селектора в нормализованном диапазоне `-1..1`; ниже этого значения включается режим `1`
- `SPEED_MODE_HIGH_THRESHOLD=0.3` — верхний порог селектора в нормализованном диапазоне `-1..1`; выше этого значения включается режим `3`
- `SPEED_MODE_SLOW_SCALE=0.3333333333333333` — коэффициент для режима `1`
- `SPEED_MODE_MEDIUM_SCALE=0.6666666666666666` — коэффициент для режима `2`
- `SPEED_MODE_FAST_SCALE=1.0` — коэффициент для режима `3`
- `IMU_ENABLED=0|1` — включает autodetect IMU backend на I2C: BMI160/BMI166 или ST LSM6DS3-class
- `IMU_I2C_BUS=1`, `IMU_I2C_ADDRESS=104`, `IMU_EXPECTED_CHIP_ID=209` — параметры подключения IMU; на текущем роботе ST-модуль отвечает по `0x6A`, так что для него нужен `IMU_I2C_ADDRESS=106`
- `IMU_SAMPLE_RATE_HZ=100.0`, `IMU_STALE_TIMEOUT_S=0.2`, `IMU_GYRO_BIAS_CALIBRATION_S=1.0`, `IMU_GYRO_Z_SIGN=1.0` — частота чтения, timeout свежести, длительность bias-калибровки и знак yaw-оси
- `DRIVE_MODE_STEERING_DEADBAND=0.05`, `DRIVE_MODE_STEERING_LIMIT=1.0`, `DRIVE_MODE_YAW_RATE_MAX_DPS=90.0` — базовые ограничения assist-контура
- `DRIVE_MODE_YAW_RATE_KP/KI/KD` — tuning-параметры yaw-rate контура stabilized режима
- `DRIVE_MODE_YAW_RATE_DEADBAND_DPS`, `DRIVE_MODE_YAW_RATE_FILTER_HZ` — подавление мелкого gyro noise и сглаживание yaw-rate feedback
- `DRIVE_MODE_STABILIZATION_MIN_THROTTLE`, `DRIVE_MODE_NEUTRAL_STABILIZATION_STEERING_LIMIT`, `DRIVE_MODE_NEUTRAL_STABILIZATION_MAX_THROTTLE` — low-speed ограничения stabilized режима
- `PID_TUNING_SETTINGS_PATH=/data/pid-tuning.json` — persistent JSON с последними field-tuning значениями stabilized режима
- `LOW_CELL_VOLTAGE=3.5` — порог низкого напряжения ячейки для предупреждения `LOW` на Lua-экране
- `LOW_PACK_VOLTAGE=21.0` — порог низкого напряжения пакета (резервный, если ячейки не доступны)
- `BMS_BLE_ADDRESS=` — MAC-адрес BLE BMS (пустая строка = авто-поиск)
- `BMS_BLE_TIMEOUT_S=1.5` — таймаут BLE-операций
- `BMS_BLE_SERVICE_UUID`, `BMS_BLE_WRITE_UUID`, `BMS_BLE_NOTIFY_UUID` — UUID BLE-сервиса Daly (менять не нужно для стандартного Daly)
- `BMS_TELEMETRY_TRACE_ENABLED=0|1` — включает точные controller-side trace-логи на этапах consume/send для battery telemetry
- `BEACON_ENABLED=1` — включён по умолчанию; `0` отключает маяк совсем
- `BEACON_DELAY_S=300`
- `CH_BEACON=7` — `CH8` на передатчике; ручное включение маяка
- `CH_MUTE=9` — `CH10` на передатчике по умолчанию; канал мьюта обычных звуков, если нужен отдельный mute switch
- `CH_TRIM=8` — `CH9` на передатчике; в trim-mode используется как live-источник подстройки межколёсного баланса
- `MOTOR_TRIM_MAX_EFFECT=0.30` — максимальная коррекция, применяемая к одной стороне от полного хода `CH9`
- `MOTOR_TRIM_CONFIRM_HOLD_S=5.0` — сколько секунд держать trim-жест для входа и подтверждения
- `MOTOR_TRIM_SETTINGS_PATH=/data/motor-trim.json` — файл сохранённого trim на persistent Docker volume
- `ENABLE_RC_MELODIES=0|1` — включает выбор BLHeli-мелодий с передатчика
- `CH_MELODY=8` — канал выбора мелодии, если `ENABLE_RC_MELODIES=1`
- `STARTUP_MELODY=biba_signature` — стартовая BLHeli-мелодия при включённом melody-runtime
- `SOUND_MODE=SPECTRAL_VOICE|VOICE|SYNTH` — режим звуковой индикации: `SPECTRAL_VOICE` (по умолчанию) использует build-time spectral cache, `VOICE` — raw WAV, `SYNTH` — только BLHeli-мелодии без голоса
- `VOICE_SELECTION_MODE=ROUND_ROBIN|RANDOM` — порядок воспроизведения WAV при наличии нескольких вариантов на событие
- `MOTOR_TEST_API_ENABLED=1` — включён по умолчанию; `0` отключает встроенный HTTP settings UI контроллера
- `MOTOR_TEST_API_HOST=0.0.0.0` — bind host для settings UI
- `MOTOR_TEST_API_PORT=8765` — bind port для settings UI
- `RAMP_ACCEL_RATE=2.0` — скорость разгона мотора (единиц/сек, 0→100% за 0.5с)
- `RAMP_DECEL_RATE=2.0` — скорость отпускания/торможения (единиц/сек, 100%→0 за 0.5с)
- `RAMP_REVERSE_DECEL_RATE=0.5` — скорость подхода к нулю перед сменой направления; меньше значение = мягче переход в реверс
- `RAMP_ZERO_HOLD_S=0.15` — пауза на нуле (секунды) после торможения перед реверсом; даёт мотору физически остановиться и убирает «гавканье» BTS7960
- `MOTOR_DEADBAND=0.05` — мёртвая зона стика (меньше порога → мотор стоит)

Если нужно включить current sense через ADS1115, дополнительно задайте:

- `MOTOR_CURRENT_SENSE_ENABLED=1`
- `MOTOR_CURRENT_LIMITING_ENABLED=0|1` — включает software throttle back при превышении тока
- `MOTOR_CURRENT_SENSE_I2C_ADDRESS=72` (0x48 — стандартный адрес ADS1115)
- `MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ=32.0` — частота опроса ADS1115
- `MOTOR_CURRENT_SENSE_GAIN=1` — коэффициент усиления ADS1115 (1, 2, 4, 8, 16)
- `LEFT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL=2`, `LEFT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL=3`
- `RIGHT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL=0`, `RIGHT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL=1`
- `LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V=0.0`, `RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V=0.0` — нулевые смещения для калибровки
- `LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT=1.0`, `RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT=1.0` — коэффициент перевода напряжения в амперы
- `LEFT_MOTOR_MAX_CURRENT_A=18.0`, `RIGHT_MOTOR_MAX_CURRENT_A=18.0` — пороги ограничения тока
- `LEFT_MOTOR_MAX_POWER_W=180.0`, `RIGHT_MOTOR_MAX_POWER_W=180.0` — пороги ограничения мощности
- `MOTOR_LIMIT_FALLBACK_VOLTAGE=24.0` — напряжение пакета для расчёта мощности при отсутствии BMS данных

Для калибровочных заездов доступен отдельный trace-режим current sense:

- `MOTOR_CURRENT_TRACE_ENABLED=0|1` — включает JSONL-лог с motor activity, ADS1115 и BMS snapshot
- `MOTOR_CURRENT_TRACE_PATH=/data/current-trace.jsonl` — путь к trace-файлу на persistent volume
- `MOTOR_CURRENT_TRACE_POST_ROLL_S=2.0` — сколько секунд держать запись после окончания motor activity
- `MOTOR_CURRENT_TRACE_MIN_INTERVAL_S=0.0` — минимальный интервал между sample-записями; `0.0` означает без дополнительного rate limit

Этот trace нужен для офлайн-калибровки токов колёс против более медленного тока BMS и по умолчанию выключен.

Опциональные параметры STM32 SPI companion link (композиция C, выключен по умолчанию):

- `STM32_LINK_ENABLED=0|1` — включает SPI-клиент к STM32F103 add-on
- `STM32_LINK_SPI_BUS=0`, `STM32_LINK_SPI_DEVICE=0` — номер шины и устройства SPI
- `STM32_LINK_SPI_SPEED_HZ=8000000` — скорость SPI

Прочие:

- `LOG_LEVEL=INFO` — уровень логирования контроллера (`DEBUG`, `INFO`, `WARNING`, `ERROR`)

## Settings UI

Для инженерной проверки и полевого тюнинга на контроллере доступен встроенный HTTP settings UI:

- `http://<robot-ip>:8765/settings` — основной операторский экран
- `http://<robot-ip>:8765/motor-test` — legacy manual PWM page
- `http://<robot-ip>:8765/pid-tuning` — legacy PID-only page

Страница `/settings` собирает в одном месте:

- live platform status и revision state
- field tuning stabilized режима
- сохранённый motor trim с отображением live trim-mode значения
- ручной motor sound / PWM test

Backend surface для новой страницы:

- `GET /api/settings` — агрегированный snapshot platform, pid_tuning, motor_trim и motor_test
- `POST /api/settings/pid-tuning` — новые tuning-параметры stabilized режима
- `POST /api/settings/motor-trim` — сохранение нового trim пока платформа `disarmed`
- `POST /api/settings/motor-test` — короткий manual PWM test

PID tuning на `/settings` работает без рестарта контейнера и сразу сохраняется в `PID_TUNING_SETTINGS_PATH`. Обновления разрешены только пока платформа `disarmed`, а страница показывает `pending revision`, пока main loop не применит новый snapshot.

Motor trim на `/settings` показывает текущее сохранённое значение, queued revision state и live значение в trim-mode. Trim по-прежнему можно менять двумя путями:

- через операторскую страницу `/settings`
- через transmitter gesture в `disarm` с live источником на `CH9`

Legacy страницы `/motor-test` и `/pid-tuning` оставлены для совместимости и быстрых инженерных проверок.

Для текущего кода и текущего робота default уже `SOFTWARE`. Режим `HARDWARE` оставлен только для совместимых конфигураций, где PWM-линии не конфликтуют между собой.

Если после сборки одно из колёс едет в обратную сторону, достаточно выставить для него значение `1`.

Также поддерживается звуковая индикация через моторы:

- автоматический SOS после длительного failsafe
- ручное включение с тумблера передатчика через `CH_BEACON`
- режимы движения на `CH_DRIVE_MODE`: `manual`, `stabilized`
- общий мьют обычных звуков через `CH_MUTE`
- отключение маяка через `BEACON_ENABLED=0`

Отдельный hardware buzzer в текущей конфигурации не нужен: аудио, маяк и voice playback идут через моторный synth.

## Motor Trim

Для полевой подстройки прямолинейности робот поддерживает trim межколёсного баланса:

- при `disarm` держите первые четыре канала в максимуме 5 секунд, чтобы войти в trim-mode
- в trim-mode на Lua-экране появляется badge `t`
- пока trim-mode активен, контроллер берёт trim напрямую из `CH9`
- полный ход `CH9` используется целиком для точности, но на моторы применяется только до `MOTOR_TRIM_MAX_EFFECT` коррекции
- при повторном 5-секундном жесте в `disarm` текущее значение `CH9` сохраняется в `/data/motor-trim.json`
- после выхода из trim-mode используется уже сохранённое значение, а `CH9` снова игнорируется

То же сохранённое значение видно и редактируется на `http://<robot-ip>:8765/settings`.

Файл trim хранится на named Docker volume `biba-controller-data`, поэтому переживает перезапуск контейнера и обновление образа.

## Офлайн voice pipeline

Для голосовых ассетов используется офлайн-пайплайн, а не генерация речи на роботе.

Правила:

- канонические фразы в `voice-src/phrases.yml` должны быть на русском языке
- production runtime по умолчанию использует по одному утверждённому WAV на событие
- новые варианты сначала попадают в `voice-work/`, а не сразу в `biba-controller/voice/`
- при сборке controller image production WAV из `biba-controller/voice/` дополнительно преобразуются в derived spectral cache внутри image, чтобы робот не тратил секунды на FFT-предобработку при arm/disarm/connect voice events

Базовый цикл такой:

1. Обновить русские фразы в `voice-src/phrases.yml`.
2. Сгенерировать approved WAV-кандидаты в `voice-work/`.
3. Явно продвинуть их в production каталог командой `scripts/voice_prep.py promote-approved --manifest voice-src/phrases.yml --base-dir voice-work --repo-root .`.
4. Закоммитить обновлённые WAV в ветку и доставить их на робота через штатный robot-side update workflow `bbupdate`.

Так production voice assets обновляются предсказуемо и без отдельного audition runtime path.

Сами spectral cache artifacts в git не хранятся. Они пересобираются внутри Docker image и в runtime используются автоматически для production voice путей, а для временных или нестандартных WAV контроллер по-прежнему умеет падать обратно на live-анализ.

## CI и образы

GitHub Actions выполняет:

- `ruff check biba-controller/ tests/`
- `pytest`
- сборку arm64 Docker-образа через Buildx на стороне GitHub Actions
- push глобального образа в GHCR

Workflow'ы организованы по схеме `G-*`:

- `G-Build-Controller-Image.yml` — линт, тесты, сборка и push образа контроллера
- `G-Build-All.yml` — верхнеуровневый запуск полной сборки проекта

Базовая модель деплоя композиции A:

```bash
docker compose -f docker/legacy-pi/docker-compose.yml pull
docker compose -f docker/legacy-pi/docker-compose.yml up -d
```

Либо на роботе через alias `bbupdate` (`scripts/biba_aliases.sh`).

Raspberry Pi не обязан собирать образ локально, он просто забирает готовый arm64-образ из GHCR.

Полное руководство по развёртыванию: [docs/deployment.md](docs/deployment.md)

## Экран телеметрии

Скопируйте `lua/SCRIPTS/TELEMETRY/biba.lua` на SD-карту передатчика в каталог `SCRIPTS/TELEMETRY/`, затем добавьте скрипт как экран телеметрии в EdgeTX/OpenTX.

Текущая версия экрана показывает:

- общее напряжение батареи
- ток в mA
- SOC в процентах
- link quality `RQly`
- 6 ячеек батареи
- `min/max/delta` по ячейкам
- CPU и RAM контроллера
- ток левого и правого моторов
- локальные бейджи `a/b/mode` и speed badge для arm, beacon, drive mode и speed mode
- бейдж `t`, когда на роботе активен trim-mode
- бейдж зарядки, когда батарея находится в состоянии `CHG`
- мигающее предупреждение `LOW`, если минимальная ячейка уходит ниже порога
- wheel animation по throttle/steering с передатчика
- VCP serial logging для захвата telemetry screen данных

Скрипт пытается читать реальные cell sensors (`Cels`), а если передатчик их не отдает, использует fallback-оценку от общего напряжения пакета. Для robot-side status он использует существующие telemetry bits из battery capacity field, а `a/m/b` берёт локально с передатчика.

Для токов колёс semantic contract теперь считается BIBA-специфичным: controller нормализует левый и правый wheel current в канонические значения, а Lua-экран читает уже BIBA-layer helpers. Текущий CRSF carrier mapping через GPS-поля остаётся лишь transport-совместимостью и не должен использоваться как UI-level контракт.

## Каталог skills

В репозитории присутствует вендорный каталог `.agents/skills/`, чтобы локально использовать тот же набор skills, что и в другом рабочем окружении. На первом проходе импорт выполнен без адаптации содержимого.

## Дорожная карта

**Текущий milestone: RP2040 Port** — портирование управляющего runtime на RP2040 как standalone embedded target (ветка `rp2040-port`).

| Фаза | Цель | Статус |
| --- | --- | --- |
| **Phase 1: Core Drive** | CRSF + BTS7960 PWM + Arming/Failsafe + SpeedRamp | В работе (01–04 выполнены, финальная сборка) |
| **Phase 2: Stabilization & Sensing** | IMU heading-hold + current sense + trim persistence | Не начата |
| **Phase 3: Field Ready** | Тепловая защита ESC + матрица вариантов + полевой тест | Не начата |

Полевые испытания проведены 09.05.2026 (двор). Основная проблема — тепловой режим BTS7960 при длительной езде; решается аппаратно (крепёж плат на металлическую пластину).

Долгосрочные направления (за пределами RP2040 Port):

- BMS интеграция и голос на RP2040 (отложено — недостаточно RAM)
- ROS2-ноды для Pi Zero 2W (отдельный milestone)
- Follow-me режим, автономная навигация (после field-ready RP2040)
