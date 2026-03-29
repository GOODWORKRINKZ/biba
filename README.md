# BiBa

BiBa — это колесная робот-платформа на базе Raspberry Pi Zero 2W с управлением по ExpressLRS/CRSF, телеметрией от Daly 6S BMS, двухканальным моторным драйвером и звуковой индикацией через буззер.

## Состав железа

- Raspberry Pi Zero 2W
- ELRS-приемник с подключением по UART/CRSF
- Daly BMS с USB-UART адаптером
- 6S аккумулятор с телеметрией BMS
- Два драйвера BTS7960 для левого и правого моторов
- Буззер на GPIO17

## Распиновка

| Назначение | BCM | Физический пин |
| --- | --- | --- |
| ELRS TX | 14 | 8 |
| ELRS RX | 15 | 10 |
| Buzzer | 17 | 11 |
| Left BTS7960 RPWM | 18 | 12 |
| Left BTS7960 LPWM | 13 | 33 |
| Left BTS7960 REN | 23 | 16 |
| Left BTS7960 LEN | 24 | 18 |
| Right BTS7960 RPWM | 12 | 32 |
| Right BTS7960 LPWM | 19 | 35 |
| Right BTS7960 REN | 20 | 38 |
| Right BTS7960 LEN | 21 | 40 |
| GND драйвера | - | 14 |

Подробное описание подключения находится в [docs/wiring.md](docs/wiring.md).

Текущий двухмоторный runtime на Pi Zero 2W должен быть запущен с `BTS7960_PWM_MODE=SOFTWARE`, потому что распиновка `18/13` и `12/19` делит общие hardware-PWM каналы. Кодовый дефолт остаётся `HARDWARE`, но для этой конкретной проводки compose уже принудительно переводит BTS7960 в software PWM.

## Структура репозитория

- `biba-controller/` — Python-контроллер для CRSF, моторов, буззера и телеметрии BMS
- `lua/SCRIPTS/TELEMETRY/biba.lua` — экран телеметрии EdgeTX для оператора
- `.github/workflows/` — global builder workflows для Ruff, pytest, shellcheck и сборки arm64 Docker-образа в GHCR
- `scripts/setup/` — bringup-скрипты для Raspberry Pi (Docker, Compose, systemd-автозапуск)
- `scripts/update.sh` — быстрое обновление (git pull + image pull + restart)
- `scripts/diagnostics.sh` — диагностика хоста и контейнера
- `scripts/voice_prep.py` — офлайн-подготовка русскоязычных voice assets и явный promote в production voice каталог
- `voice-src/phrases.yml` — канонический набор русских фраз по событиям
- `voice-work/` — staging-каталог для сгенерированных кандидатов перед promote в production voice каталог
- `docs/deployment.md` — полное руководство по развёртыванию
- `.agents/skills/` — вендорный каталог skills

## Подготовка Raspberry Pi

1. Включите UART на Raspberry Pi.
2. Освободите основной UART от Bluetooth, добавив в конфигурацию:

   ```ini
   enable_uart=1
   dtoverlay=disable-bt
   ```

3. Перезагрузите Raspberry Pi.
4. Подключите USB-UART адаптер от Daly BMS.

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

## Запуск

```bash
docker compose pull
docker compose up -d
```

Локальная сборка по-прежнему доступна при необходимости:

```bash
docker compose build
docker compose up -d
```

Контейнер запускает `pigpiod`, слушает ELRS CRSF кадры на `/dev/ttyAMA0`, управляет моторами, опрашивает Daly BMS на `/dev/ttyUSB0` и отправляет батарейную телеметрию обратно на передатчик.

Docker-образ собирается под `linux/arm64`, чтобы совпадать с Raspberry Pi Zero 2W. Для этого `pigpiod` собирается внутри образа из upstream `pigpio`, так как готовый пакет `pigpio` отсутствует в Debian bookworm arm64.

Тип драйвера и распиновку можно переопределить через переменные окружения в `docker-compose.yml`:

- `MOTOR_DRIVER_TYPE=BTS7960|PWM_DIR`
- `BTS7960_PWM_MODE=HARDWARE|SOFTWARE` — для Pi Zero 2W с текущей двухмоторной проводкой нужен `SOFTWARE`
- `LEFT_MOTOR_RPWM=18`
- `LEFT_MOTOR_LPWM=13`
- `LEFT_MOTOR_REN=23`
- `LEFT_MOTOR_LEN=24`
- `RIGHT_MOTOR_RPWM=12`
- `RIGHT_MOTOR_LPWM=19`
- `RIGHT_MOTOR_REN=20`
- `RIGHT_MOTOR_LEN=21`
- `MOTOR1_INVERTED=0|1`
- `MOTOR2_INVERTED=0|1`
- `THROTTLE_FILTER_MODE=KALMAN|NONE` — фильтрация газа до wheel-mix; `KALMAN` сглаживает выбросы канала
- `THROTTLE_KALMAN_PROCESS_NOISE=0.02` — насколько быстро фильтр принимает изменения реального setpoint
- `THROTTLE_KALMAN_MEASUREMENT_NOISE=0.5` — насколько сильно фильтр подавляет шум и ложные выбросы канала
- `BMS_TELEMETRY_TRACE_ENABLED=0|1` — включает точные controller-side trace-логи на этапах consume/send для battery telemetry
- `BEACON_ENABLED=0|1`
- `BEACON_DELAY_S=300`
- `CH_BEACON=5`
- `CH_MUTE=6` — канал мьюта; при активном тумблере обычные звуки подавляются, SOS остаётся
- `CH_TRIM=8` — `CH9` на передатчике; в trim-mode используется как live-источник подстройки межколёсного баланса
- `MOTOR_TRIM_MAX_EFFECT=0.20` — максимальная коррекция, применяемая к одной стороне от полного хода `CH9`
- `MOTOR_TRIM_CONFIRM_HOLD_S=5.0` — сколько секунд держать trim-жест для входа и подтверждения
- `MOTOR_TRIM_SETTINGS_PATH=/data/motor-trim.json` — файл сохранённого trim на persistent Docker volume
- `RAMP_ACCEL_RATE=2.0` — скорость разгона мотора (единиц/сек, 0→100% за 0.5с)
- `RAMP_DECEL_RATE=0.5` — скорость отпускания/торможения (единиц/сек, 100%→0 за 2с)
- `RAMP_REVERSE_DECEL_RATE=1.0` — скорость подхода к нулю перед сменой направления; меньше значение = мягче переход в реверс
- `RAMP_ZERO_HOLD_S=0.15` — пауза на нуле (секунды) после торможения перед реверсом; даёт мотору физически остановиться и убирает «гавканье» BTS7960
- `MOTOR_DEADBAND=0.05` — мёртвая зона стика (меньше порога → мотор стоит)

`HARDWARE` остаётся дефолтом в коде для совместимых конфигураций, где PWM-линии не конфликтуют между собой. Для текущего робота override на `SOFTWARE` считается временной эксплуатационной конфигурацией.

Если после сборки одно из колёс едет в обратную сторону, достаточно выставить для него значение `1`.

Также поддерживается звуковой маяк на буззере:

- автоматический SOS после длительного failsafe
- ручное включение с тумблера передатчика через `CH_BEACON`
- общий мьют обычных звуков через `CH_MUTE`
- отключение маяка через `BEACON_ENABLED=0`

## Motor Trim

Для полевой подстройки прямолинейности робот поддерживает trim межколёсного баланса:

- при `disarm` держите первые четыре канала в максимуме 5 секунд, чтобы войти в trim-mode
- в trim-mode на Lua-экране появляется badge `t`
- пока trim-mode активен, контроллер берёт trim напрямую из `CH9`
- полный ход `CH9` используется целиком для точности, но на моторы применяется только до `20%` коррекции
- при повторном 5-секундном жесте в `disarm` текущее значение `CH9` сохраняется в `/data/motor-trim.json`
- после выхода из trim-mode используется уже сохранённое значение, а `CH9` снова игнорируется

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
4. Закоммитить обновлённые WAV в ветку и доставить их на робота через обычный workflow обновления.

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

Базовая модель деплоя теперь такая:

```bash
docker compose pull
docker compose up -d
```

Raspberry Pi не обязан собирать образ локально, он просто забирает готовый arm64-образ из GHCR.

Полное руководство по развёртыванию: [docs/deployment.md](docs/deployment.md)

## Экран телеметрии

Скопируйте `lua/SCRIPTS/TELEMETRY/biba.lua` на SD-карту передатчика в каталог `SCRIPTS/TELEMETRY/`, затем добавьте скрипт как экран телеметрии в EdgeTX/OpenTX.

Текущая версия экрана показывает:

- общее напряжение батареи
- ток
- SOC в процентах
- RSSI
- 6 ячеек батареи
- `min/max/delta` по ячейкам
- мигающее предупреждение `LOW`, если минимальная ячейка уходит ниже порога
- звуки `playTone` на передатчике: стартовый сигнал, connect/disconnect, low battery

Скрипт пытается читать реальные cell sensors (`Cels`), а если передатчик их не отдает, использует fallback-оценку от общего напряжения пакета.

## Каталог skills

В репозитории присутствует вендорный каталог `.agents/skills/`, чтобы локально использовать тот же набор skills, что и в другом рабочем окружении. На первом проходе импорт выполнен без адаптации содержимого.

## Дорожная карта

- Стабилизировать CRSF-контур управления и парсинг BMS на реальном железе
- Добавить unit-тесты для CRSF кадров, парсинга BMS и микширования привода
- Разделить контроллер на ROS 2-ноды после стабилизации одноконтейнерной версии
