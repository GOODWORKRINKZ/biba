# Развёртывание BiBa

## Обзор композиций

BiBa разворачивается в одной из трёх композиций железа. Каноническое описание — в [system_architecture.md](system_architecture.md). Кратко:

- **Композиция A: Pi-only** — текущий продакшен-путь. Raspberry Pi Zero 2W сам читает CRSF и крутит PWM. Развёртывание полностью описано ниже.
- **Композиция B: STM32-only** — без SBC. Развёртывание сводится к сборке и прошивке прошивки STM32F103.
- **Композиция C: Pi + STM32** — в разработке. ROS2-стек на SBC + companion-прошивка на STM32.

## Композиция A (Pi-only)

Рабочая компоновка стека — [`docker/legacy-pi/docker-compose.yml`](../docker/legacy-pi/docker-compose.yml). На роботе все стандартные действия проходят через `bb*`-aliases (`scripts/biba_aliases.sh`); путь к compose-файлу можно переопределить переменной `BIBA_COMPOSE_FILE`.

## Предварительные требования

### Оборудование

- Raspberry Pi Zero 2W (или другая плата с arm64 и GPIO)
- ELRS-приемник, подключенный к UART (`/dev/ttyS0`)
- Daly BMS по BLE или через USB-UART адаптер (`/dev/ttyUSB0`)
- Два драйвера BTS7960 для левого и правого моторов
- ADS1115 для current sense и телеметрии токов колёс (опционально)
- 6S LiPo аккумулятор

### Подключение

Полная распиновка — в [wiring.md](wiring.md).

## Быстрая установка

Запустите bringup-скрипт на Raspberry Pi:

```bash
curl -fsSL https://raw.githubusercontent.com/GOODWORKRINKZ/biba/main/scripts/setup/setup_node.sh | bash
```

Скрипт выполнит:

1. Установку системных утилит (`git`, `curl`, `vim`, `htop`, и др.)
2. Установку Docker и Docker Compose plugin
3. Клонирование репозитория в `~/biba`
4. Настройку shell-алиасов для управления стеком
5. Создание `/etc/default/biba-controller` с `BIBA_IMAGE_TAG=latest`
6. Создание systemd unit `biba-controller.service` для автозапуска без image pull на boot

## Авторизация в GHCR

Образ контейнера хранится в GitHub Container Registry. Для pull требуется авторизация:

```bash
echo YOUR_GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin
```

Создайте Personal Access Token (classic) с правом `read:packages` в [GitHub Settings → Developer settings → Tokens](https://github.com/settings/tokens).

## Запуск

После установки и авторизации:

```bash
# Через systemd (рекомендуется)
sudo systemctl start biba-controller.service

# Или вручную
cd ~/biba
docker compose -f docker/legacy-pi/docker-compose.yml pull
docker compose -f docker/legacy-pi/docker-compose.yml up -d
```

`biba-controller.service` на старте системы из `WorkingDirectory=$REPO_DIR/docker/legacy-pi` выполняет только `docker compose up -d`.
Pull новых образов остается в ручном обновлении и в `bbupdate`, чтобы не дергать сеть и GHCR во время boot.

## Управление стеком

После установки доступны shell-алиасы:

| Команда | Описание |
|---------|----------|
| `bbstatus` | Статус контейнеров |
| `bblogs` | Логи в реальном времени |
| `bbpull` | Скачать новый образ |
| `bbstart` | Запустить стек |
| `bbstop` | Остановить стек |
| `bbrestart` | Перезапустить стек |
| `bbupdate` | Полное обновление: git pull + pull + up |
| `bbhealth` | Обзор запущенных контейнеров |

## Обновление

Поддерживаемый robot-side путь обновления:

```bash
bbupdate
```

Если текущая shell-сессия была открыта до установки алиасов, сначала загрузите их:

```bash
source ~/biba/scripts/biba_aliases.sh
bbupdate
```

## Диагностика

```bash
bash ~/biba/scripts/diagnostics.sh
```

Выводит: Docker-версию, статус контейнера, последние логи, температуру CPU, память, диск, USB-устройства и состояние git.

## Конфигурация

Переменные окружения задаются в [`docker/legacy-pi/docker-compose.yml`](../docker/legacy-pi/docker-compose.yml):

| Переменная | По умолчанию | Описание |
|------------|-------------|---------|
| `CRSF_PORT` | `/dev/ttyS0` | UART-порт ELRS |
| `BMS_TRANSPORT` | `BLE` | Транспорт BMS: `BLE` или явный fallback `UART` |
| `BMS_PORT` | `/dev/ttyUSB0` | USB-UART порт Daly BMS |
| `BMS_BLE_ADDRESS` | `` | MAC-адрес BLE-модуля Daly |
| `BMS_BLE_SERVICE_UUID` | `0000fff0-0000-1000-8000-00805f9b34fb` | BLE service UUID Daly |
| `BMS_BLE_WRITE_UUID` | `0000fff2-0000-1000-8000-00805f9b34fb` | BLE characteristic для команд |
| `BMS_BLE_NOTIFY_UUID` | `0000fff1-0000-1000-8000-00805f9b34fb` | BLE characteristic для ответов |
| `BMS_BLE_TIMEOUT_S` | `1.5` | Таймаут ответа BMS по BLE |
| `BMS_TELEMETRY_TRACE_ENABLED` | `0` | Включает точные monotonic trace-логи на этапах consume/send для battery telemetry |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `MOTOR_DRIVER_TYPE` | `BTS7960` | Тип драйвера моторов: штатный `BTS7960` или старый `PWM_DIR` |
| `BTS7960_PWM_MODE` | `SOFTWARE` | Режим PWM для `BTS7960`: текущий рабочий и кодовый default для двухмоторной проводки на Pi Zero 2W; `HARDWARE` используйте только для совместимой раскладки без конфликта PWM-каналов |
| `CH_STEERING` | `3` | Номер канала руления |
| `CH_THROTTLE` | `1` | Номер канала газа |
| `CH_ARM` | `4` | Номер канала арма |
| `THROTTLE_FILTER_MODE` | `NONE` | Фильтрация газа до wheel-mix; `NONE` отключает, `KALMAN` сглаживает выбросы канала |
| `THROTTLE_KALMAN_PROCESS_NOISE` | `0.02` | Насколько быстро фильтр принимает изменение реального газа |
| `THROTTLE_KALMAN_MEASUREMENT_NOISE` | `0.5` | Насколько сильно фильтр подавляет шум и ложные выбросы канала |
| `CH_DRIVE_MODE` | `6` | `CH7`; селектор режимов `manual` / `stabilized` |
| `BEACON_ENABLED` | `1` | Включить звуковой маяк/SOS на роботе |
| `BEACON_DELAY_S` | `300` | Через сколько секунд failsafe включать авто-SOS |
| `CH_BEACON` | `7` | `CH8`; канал тумблера для ручного включения маяка |
| `CH_MUTE` | `9` | `CH10`; канал мьюта обычных звуков; SOS не приглушается |
| `CH_TRIM` | `8` | `CH9`; live-источник trim в режиме калибровки прямолинейности |
| `IMU_ENABLED` | `0` | Включить autodetect IMU backend на I2C: BMI160/BMI166 или ST LSM6DS3-class |
| `IMU_I2C_BUS` | `1` | Номер Linux I2C bus для IMU |
| `IMU_I2C_ADDRESS` | `104` | Адрес IMU на I2C; для BMI обычно `0x68/0x69`, для ST LSM6DS3-class часто `0x6A/0x6B` |
| `IMU_EXPECTED_CHIP_ID` | `209` | Ожидаемый chip-id BMI (`0xD1`); используется только на BMI-пути autodetect |
| `IMU_SAMPLE_RATE_HZ` | `100.0` | Частота чтения IMU |
| `IMU_STALE_TIMEOUT_S` | `0.2` | После какого возраста sample assist отключается в fallback |
| `IMU_GYRO_BIAS_CALIBRATION_S` | `1.0` | Длительность bias-калибровки гиры в разоружённом состоянии |
| `IMU_GYRO_Z_SIGN` | `1.0` | Знак yaw-оси, если IMU установлена зеркально |
| `DRIVE_MODE_STEERING_DEADBAND` | `0.05` | Deadband steering stick для stabilized assist |
| `DRIVE_MODE_STEERING_LIMIT` | `1.0` | Верхний предел steering output assist-контура |
| `DRIVE_MODE_YAW_RATE_MAX_DPS` | `90.0` | Максимальный целевой yaw-rate для stabilized режима |
| `DRIVE_MODE_YAW_RATE_KP` | `0.010` | `Kp` yaw-rate PID контура stabilized режима |
| `DRIVE_MODE_YAW_RATE_KI` | `0.0` | `Ki` yaw-rate PID контура stabilized режима |
| `DRIVE_MODE_YAW_RATE_KD` | `0.001` | `Kd` yaw-rate PID контура stabilized режима |
| `DRIVE_MODE_YAW_RATE_DEADBAND_DPS` | `4.0` | Deadband по измеренному yaw-rate для подавления мелкого шума гиры |
| `DRIVE_MODE_YAW_RATE_FILTER_HZ` | `5.0` | Low-pass фильтр измеренного yaw-rate |
| `DRIVE_MODE_STABILIZATION_MIN_THROTTLE` | `0.1` | Ниже этого газа stabilized-контур не подруливает при нейтральном руле |
| `DRIVE_MODE_NEUTRAL_STABILIZATION_STEERING_LIMIT` | `0.12` | Максимальная величина автоматической подрулёжки на нейтрали |
| `DRIVE_MODE_NEUTRAL_STABILIZATION_MAX_THROTTLE` | `0.25` | До какого газа действует ограничение neutral stabilization |
| `PID_TUNING_SETTINGS_PATH` | `/data/pid-tuning.json` | Persistent JSON с последними значениями field tuning |
| `MOTOR_TRIM_MAX_EFFECT` | `0.30` | Максимальная односторонняя коррекция PWM от полного хода `CH9` |
| `MOTOR_TRIM_CONFIRM_HOLD_S` | `5.0` | Длительность trim-жеста для входа и подтверждения |
| `MOTOR_TRIM_SETTINGS_PATH` | `/data/motor-trim.json` | Путь к persistent JSON-файлу сохранённого trim |
| `MOTOR_TEST_API_ENABLED` | `1` | Включает встроенный HTTP settings UI контроллера |
| `MOTOR_TEST_API_HOST` | `0.0.0.0` | Bind host для settings UI |
| `MOTOR_TEST_API_PORT` | `8765` | Bind port для settings UI |
| `ENABLE_RC_MELODIES` | `0` | Включает выбор BLHeli-мелодий с передатчика |
| `CH_MELODY` | `8` | Канал выбора мелодии при `ENABLE_RC_MELODIES=1` |
| `STARTUP_MELODY` | `biba_signature` | Стартовая BLHeli-мелодия |
| `SOUND_MODE` | `synth` | Режим системных звуков: `voice`, `spectral_voice` или `synth` |
| `RAMP_ACCEL_RATE` | `2.0` | Макс. скорость разгона мотора (ед/сек); 0→100% за 0.5с |
| `PWM_FREQUENCY_HZ` | `20000` | Частота PWM для motor runtime |
| `RAMP_DECEL_RATE` | `2.0` | Макс. скорость отпускания/торможения (ед/сек); 100%→0 за 0.5с |
| `RAMP_REVERSE_DECEL_RATE` | `0.5` | Скорость подхода к нулю перед сменой направления; меньше значение делает реверс мягче |
| `RAMP_ZERO_HOLD_S` | `0.15` | Пауза на нуле (сек) после торможения перед реверсом; даёт мотору физически остановиться |
| `MOTOR_DEADBAND` | `0.05` | Мёртвая зона: значения ниже порога → мотор стоит |
| `LEFT_MOTOR_RPWM` | `12` | Левый BTS7960 `RPWM` |
| `LEFT_MOTOR_LPWM` | `18` | Левый BTS7960 `LPWM` |
| `LEFT_MOTOR_REN` | `23` | Левый BTS7960 `REN` |
| `LEFT_MOTOR_LEN` | `24` | Левый BTS7960 `LEN` |
| `RIGHT_MOTOR_RPWM` | `19` | Правый BTS7960 `RPWM` |
| `RIGHT_MOTOR_LPWM` | `13` | Правый BTS7960 `LPWM` |
| `RIGHT_MOTOR_REN` | `20` | Правый BTS7960 `REN` |
| `RIGHT_MOTOR_LEN` | `21` | Правый BTS7960 `LEN` |
| `MOTOR1_INVERTED` | `1` | Инверсия мотора 1 |
| `MOTOR2_INVERTED` | `0` | Инверсия мотора 2 |

Тег образа задается в `/etc/default/biba-controller` или `.env`:

```
BIBA_IMAGE_TAG=latest
BMS_TRANSPORT=BLE
BMS_BLE_ADDRESS=
MOTOR_DRIVER_TYPE=BTS7960
BTS7960_PWM_MODE=SOFTWARE
BEACON_ENABLED=1
BEACON_DELAY_S=300
CH_DRIVE_MODE=6
CH_BEACON=7
CH_MUTE=9
CH_TRIM=8
SOUND_MODE=synth
IMU_ENABLED=1
IMU_I2C_BUS=1
IMU_I2C_ADDRESS=104
IMU_EXPECTED_CHIP_ID=209
IMU_SAMPLE_RATE_HZ=100.0
IMU_STALE_TIMEOUT_S=0.2
IMU_GYRO_BIAS_CALIBRATION_S=1.0
IMU_GYRO_Z_SIGN=1.0
DRIVE_MODE_STEERING_DEADBAND=0.05
DRIVE_MODE_STEERING_LIMIT=1.0
DRIVE_MODE_YAW_RATE_MAX_DPS=90.0
DRIVE_MODE_YAW_RATE_KP=0.010
DRIVE_MODE_YAW_RATE_KI=0.0
DRIVE_MODE_YAW_RATE_KD=0.001
DRIVE_MODE_YAW_RATE_DEADBAND_DPS=4.0
DRIVE_MODE_YAW_RATE_FILTER_HZ=5.0
DRIVE_MODE_STABILIZATION_MIN_THROTTLE=0.1
DRIVE_MODE_NEUTRAL_STABILIZATION_STEERING_LIMIT=0.12
DRIVE_MODE_NEUTRAL_STABILIZATION_MAX_THROTTLE=0.25
PID_TUNING_SETTINGS_PATH=/data/pid-tuning.json
MOTOR_TRIM_MAX_EFFECT=0.30
MOTOR_TRIM_CONFIRM_HOLD_S=5.0
MOTOR_TRIM_SETTINGS_PATH=/data/motor-trim.json
```

Если робот уже запускался со старым `.env`, обновите каналы вручную перед первым стартом новой прошивки: `CH_DRIVE_MODE=6` это передаточный `CH7`, `CH_BEACON=7` это `CH8`, а `CH_MUTE=9` перенесен на `CH10`. Старое значение `CH_MUTE=6` конфликтует с новым селектором drive mode.

Для текущего робота с единственным IMU на шине `i2c-1` обнаружен ST LSM6DS3-class модуль на адресе `0x6A`, поэтому в robot-side override нужно выставить `IMU_ENABLED=1` и `IMU_I2C_ADDRESS=106`. Значение `IMU_EXPECTED_CHIP_ID=209` при этом можно не трогать: оно используется только если autodetect находит BMI160/BMI166.

Для текущего робота c проводкой `LEFT 12/18` и `RIGHT 19/13` оставляйте `BTS7960_PWM_MODE=SOFTWARE`. В этой раскладке у левого мотора обе PWM-линии сидят на hardware PWM channel 0, а у правого мотора обе PWM-линии сидят на hardware PWM channel 1, поэтому для движения нужен software PWM.

### BLE BMS

BLE теперь используется по умолчанию. Для явной настройки BMS задайте в `.env` или `/etc/default/biba-controller`:

```bash
BMS_TRANSPORT=BLE
BMS_BLE_ADDRESS=71:C1:46:20:25:4F
```

Остальные BLE UUID можно не менять, если используется стандартный Daly BLE bridge.

Если нужен старый USB-UART путь, задайте:

```bash
BMS_TRANSPORT=UART
```

### Звуковая индикация

BiBa использует моторный synth/audio runtime для:

- startup/shutdown мелодий
- arm/disarm сигналов
- low-voltage warning
- сигнала потери связи
- SOS-маяка после длительного failsafe

Параметр `SOUND_MODE` управляет backend системных звуков:

- `voice` - прямое WAV-воспроизведение
- `spectral_voice` - FFT/spectral motor speech playback
- `synth` - только синтовые мелодии и сигналы

Текущий production compose по умолчанию запускается с `SOUND_MODE=synth`, чтобы системные события не использовали voice WAV.

Если запускать controller вне compose и без env override, raw fallback в `config.py` остаётся `spectral_voice`; для робота актуальным default считайте именно compose-настройку `synth`.

На передатчике EdgeTX Lua-скрипт дополнительно проигрывает `playTone` события при старте, восстановлении/потере связи и low battery.

### Motor trim

Контроллер умеет хранить подстроенный межколёсный trim в persistent Docker volume `biba-controller-data`.

Операторский цикл:

1. Разармить платформу.
2. Держать первые четыре канала в максимуме `5` секунд, чтобы войти в trim-mode.
3. Крутилкой на `CH9` подобрать прямолинейность. На Lua-экране в этот момент виден badge `t`.
4. Снова в `disarm` удержать первые четыре канала в максимуме `5` секунд.
5. Контроллер сохранит текущее effective trim в `/data/motor-trim.json` и выйдет из trim-mode.

Вне trim-mode live `CH9` не используется: применяется только последнее сохранённое значение.

То же значение доступно и в HTTP settings UI на `http://<robot-ip>:8765/settings`, где его можно увидеть, сохранить из браузера и сверить с live trim-mode state.

### Settings UI

В том же controller runtime доступен встроенный settings UI:

1. Откройте `http://<robot-ip>:8765/settings`.
2. Разармите платформу.
3. Измените PID, trim или запустите короткий motor test.
4. Нажмите нужную action-кнопку в секции.

Поведение `/settings`:

- `GET /api/settings` возвращает агрегированный snapshot platform, pid_tuning, motor_trim и motor_test
- PID tuning изменения применяются live без рестарта контейнера и сразу сохраняются в `PID_TUNING_SETTINGS_PATH`
- motor trim изменения ставятся в pending и применяются только пока платформа `disarmed`
- после рестарта controller загружает последние сохранённые PID/trim значения автоматически
- пока платформа `armed`, `POST /api/settings/pid-tuning` и `POST /api/settings/motor-trim` отклоняются
- UI сама опрашивает status API и показывает pending revision state

В `/settings` доступны:

- `yaw_rate_kp`, `yaw_rate_ki`, `yaw_rate_kd`
- `yaw_rate_deadband_dps`, `yaw_rate_filter_hz`
- `stabilization_min_throttle`
- `neutral_stabilization_steering_limit`
- `neutral_stabilization_max_throttle`
- сохранённый motor trim и live trim-mode значение
- manual motor PWM/sound test

Legacy страницы `http://<robot-ip>:8765/pid-tuning` и `http://<robot-ip>:8765/motor-test` остаются доступными для совместимости и быстрых инженерных проверок.

### Обновление voice assets на роботе

Новые голосовые варианты не нужно копировать на робота вручную. Используйте только репозиторий и robot-side update workflow.

Рекомендуемый порядок:

1. Подготовьте русские исходные фразы в `voice-src/phrases.yml`.
2. Сгенерируйте approved WAV-кандидаты в `voice-work/`.
3. Продвиньте их в production voice каталог:

```bash
python scripts/voice_prep.py promote-approved \
	--manifest voice-src/phrases.yml \
	--base-dir voice-work \
	--repo-root .
```

4. Закоммитьте изменения в ветку.
5. Обновите робота через `bbupdate`.

Новые voice assets по-прежнему доставляются только через репозиторий и обычный robot-side update workflow, без ручной подмены файлов на роботе.

Во время сборки controller image production WAV из `biba-controller/voice/` дополнительно преобразуются в derived spectral cache внутри image. Эти cache-файлы не коммитятся в репозиторий: они генерируются заново в CI и затем используются runtime автоматически для production voice путей. Если контроллер получает временный WAV вне production voice каталога, он по-прежнему делает live-анализ как fallback.

## Troubleshooting

### Нет USB-устройства BMS

```bash
lsusb                           # проверить адаптер
ls -la /dev/ttyUSB*             # проверить порт
dmesg | tail -20                # лог ядра
```

Убедитесь, что USB-UART адаптер подключен. Если порт отличается от `/dev/ttyUSB0`, обновите `BMS_PORT` в [`docker/legacy-pi/docker-compose.yml`](../docker/legacy-pi/docker-compose.yml).

### Нет BLE-соединения с BMS

```bash
bluetoothctl scan on
bluetoothctl connect 71:C1:46:20:25:4F
docker compose logs --tail 50 biba-controller
```

Проверьте, что:

- `BMS_TRANSPORT=BLE`
- `BMS_BLE_ADDRESS` совпадает с MAC-адресом BMS
- на хосте активна служба `bluetooth`
- в контейнер примонтирован `/run/dbus/system_bus_socket`

Если нужно измерить controller-side задержку battery telemetry до UART, временно включите `BMS_TELEMETRY_TRACE_ENABLED=1`. Тогда контроллер начнёт писать monotonic timestamps на этапах consume/send вокруг CRSF battery packet.

### Нет CRSF-сигнала

```bash
bblogs | grep -i crsf           # поиск ошибок CRSF
ls -la /dev/ttyS0               # проверить UART
```

Убедитесь, что:
- UART включен в config.txt (`enable_uart=1`)
- Pi перезагружен после изменений

### Docker permission denied

```bash
sudo usermod -aG docker $USER
# Перелогиньтесь
```

### Контейнер падает при старте

```bash
bblogs                          # посмотреть причину
docker compose -f ~/biba/docker/legacy-pi/docker-compose.yml logs --tail 50
```

Частая причина — pigpiod не может подключиться к GPIO. Убедитесь, что `/dev/gpiomem` существует и контейнер запускается с `privileged: true`.

### Образ не pull'ится

```bash
docker login ghcr.io            # проверить авторизацию
docker pull ghcr.io/goodworkrinkz/biba/biba-controller:latest
```

Убедитесь, что токен имеет право `read:packages`.

## Композиция B (STM32-only)

Без SBC. Развёртывание сводится к сборке и заливке прошивки `standalone` на STM32F103. Полная инструкция — в [`firmware/README.md`](../firmware/README.md). Подключение CRSF, питания и силовой части — в [wiring.md](wiring.md). Архитектура и SPI-протокол — в [stm32_architecture.md](stm32_architecture.md).

## Композиция C (Pi + STM32)

> Статус: **в активной интеграции**. Скелет ROS2-стека и docker-compose готовы, hardware-plugin и twist_mux ещё в работе.

В композиции C STM32 принимает CRSF и держит низкоуровневую часть (PWM, current limit, failsafe), а SBC запускает ROS2-стек поверх SPI-bridge'а к STM32. Целевая структура контейнеров и пакетов — в [ros2_stack.md](ros2_stack.md). Общая картина и failsafe-уровни — в [system_architecture.md](system_architecture.md). Исходный design-doc — в [plans/2026-04-28-sbc-architecture-redesign-design.md](plans/2026-04-28-sbc-architecture-redesign-design.md).

### Compose-стек

Рабочая компоновка ROS2-стека — [`docker/ros2/docker-compose.yml`](../docker/ros2/docker-compose.yml). Сервисы:

| Сервис | Образ | Назначение |
|--------|-------|-----------|
| `zenoh-router` | `ghcr.io/goodworkrinkz/biba/biba-ros2:${BIBA_ROS2_IMAGE_TAG}` (entrypoint `rmw_zenohd`) | Локальный zenoh router для `rmw_zenoh_cpp` |
| `biba-control` | тот же | `controller_manager` + `diff_drive_controller` поверх `biba_hardware_stm32` SystemInterface (C++): `/cmd_vel` → SPI → STM32. Единственный владелец `/dev/spidev0.0`. Запускает и `robot_state_publisher`. |
| `twist-mux` | тот же | Арбитраж `cmd_vel_*` → `/cmd_vel` |

Все сервисы используют `network_mode: host` и общий шаблон env-переменных (см. [docker/ros2/.env.example](../docker/ros2/.env.example)).

### Bringup на Pi

Композиция C наследует Docker и клон репо от композиции A — поэтому сначала запустите её bringup, а затем поверх — ROS2-bringup:

```bash
# 1. Базовая установка (Docker, репо, алиасы) — общая с композицией A
curl -fsSL https://raw.githubusercontent.com/GOODWORKRINKZ/biba/main/scripts/setup/setup_node.sh | bash

# 2. ROS2-стек: env-файл, systemd-юнит biba-ros2.service, проверка SPI-overlay
bash ~/biba/scripts/setup/setup_node_ros2.sh
```

[`scripts/setup/setup_node_ros2.sh`](../scripts/setup/setup_node_ros2.sh) идемпотентен и поддерживает флаги:

- `--dry-run` — печатает действия без записи в систему
- `--no-spi` — пропустить включение `dtparam=spi=on` (dev-машины, не Pi)

Скрипт создаёт:

- `/etc/default/biba-ros2` — env-файл с тегом образа и параметрами bridge'а (см. [docker/ros2/.env.example](../docker/ros2/.env.example))
- `/etc/systemd/system/biba-ros2.service` — `oneshot` + `RemainAfterExit`, `WorkingDirectory=$REPO/docker/ros2`, на boot выполняет `docker compose up -d` без `pull` (политика та же, что у композиции A)

### Запуск и обновление

```bash
# Авторизация в GHCR (если образ приватный)
echo $GHCR_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Pull образов и старт
sudo systemctl start biba-ros2.service
# или вручную:
cd ~/biba/docker/ros2 && docker compose pull && docker compose up -d

# Логи моста
cd ~/biba/docker/ros2 && docker compose logs -f biba-control
```

### Несовместимости с композицией A

`biba-controller.service` (композиция A) и `biba-ros2.service` (композиция C) **нельзя запускать одновременно** на одной плате: оба претендуют на CRSF UART/SPI и на одни и те же `/dev/spidev*`/`/dev/ttyS*`. Перед стартом C остановите A: `sudo systemctl stop biba-controller.service && sudo systemctl disable biba-controller.service`.

Текущие `bb*`-алиасы из [`scripts/biba_aliases.sh`](../scripts/biba_aliases.sh) указывают на `docker/legacy-pi/`. Для управления стеком C временно используйте `docker compose` напрямую из `~/biba/docker/ros2/` либо переопределите `BIBA_COMPOSE_FILE=$HOME/biba/docker/ros2/docker-compose.yml` и `BIBA_ENV_FILE=/etc/default/biba-ros2` в shell-окружении.
