# Развёртывание BiBa на Raspberry Pi

## Предварительные требования

### Оборудование

- Raspberry Pi Zero 2W (или другая плата с arm64 и GPIO)
- ELRS-приемник, подключенный к UART (`/dev/ttyAMA0`)
- Daly BMS по BLE или через USB-UART адаптер (`/dev/ttyUSB0`)
- Двухканальный драйвер моторов (PWM + DIR)
- Буззер на GPIO17
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
docker compose pull
docker compose up -d
```

`biba-controller.service` на старте системы выполняет только `docker compose up -d`.
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

Быстрое обновление одной командой:

```bash
bbupdate
```

Или через скрипт:

```bash
bash ~/biba/scripts/update.sh
```

## Диагностика

```bash
bash ~/biba/scripts/diagnostics.sh
```

Выводит: Docker-версию, статус контейнера, последние логи, температуру CPU, память, диск, USB-устройства и состояние git.

## Конфигурация

Переменные окружения задаются в `docker-compose.yml`:

| Переменная | По умолчанию | Описание |
|------------|-------------|---------|
| `CRSF_PORT` | `/dev/ttyAMA0` | UART-порт ELRS |
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
| `BTS7960_PWM_MODE` | `HARDWARE` | Режим PWM для `BTS7960`: `HARDWARE` по умолчанию в коде, `SOFTWARE` для текущей двухмоторной проводки на Pi Zero 2W |
| `CH_STEERING` | `0` | Номер канала руления |
| `CH_THROTTLE` | `1` | Номер канала газа |
| `CH_ARM` | `4` | Номер канала арма |
| `THROTTLE_FILTER_MODE` | `KALMAN` | Фильтрация газа до wheel-mix; `NONE` отключает, `KALMAN` сглаживает выбросы канала |
| `THROTTLE_KALMAN_PROCESS_NOISE` | `0.02` | Насколько быстро фильтр принимает изменение реального газа |
| `THROTTLE_KALMAN_MEASUREMENT_NOISE` | `0.5` | Насколько сильно фильтр подавляет шум и ложные выбросы канала |
| `BEACON_ENABLED` | `1` | Включить звуковой маяк/SOS на роботе |
| `BEACON_DELAY_S` | `300` | Через сколько секунд failsafe включать авто-SOS |
| `CH_BEACON` | `5` | Канал тумблера для ручного включения маяка |
| `CH_MUTE` | `6` | Канал мьюта обычных звуков; SOS не приглушается |
| `RAMP_ACCEL_RATE` | `2.0` | Макс. скорость разгона мотора (ед/сек); 0→100% за 0.5с |
| `RAMP_DECEL_RATE` | `0.5` | Макс. скорость отпускания/торможения (ед/сек); 100%→0 за 2с |
| `RAMP_REVERSE_DECEL_RATE` | `1.0` | Скорость подхода к нулю перед сменой направления; меньше значение делает реверс мягче |
| `RAMP_ZERO_HOLD_S` | `0.15` | Пауза на нуле (сек) после торможения перед реверсом; даёт мотору физически остановиться |
| `MOTOR_DEADBAND` | `0.05` | Мёртвая зона: значения ниже порога → мотор стоит |
| `LEFT_MOTOR_RPWM` | `18` | Левый BTS7960 `RPWM` |
| `LEFT_MOTOR_LPWM` | `13` | Левый BTS7960 `LPWM` |
| `LEFT_MOTOR_REN` | `23` | Левый BTS7960 `REN` |
| `LEFT_MOTOR_LEN` | `24` | Левый BTS7960 `LEN` |
| `RIGHT_MOTOR_RPWM` | `12` | Правый BTS7960 `RPWM` |
| `RIGHT_MOTOR_LPWM` | `19` | Правый BTS7960 `LPWM` |
| `RIGHT_MOTOR_REN` | `20` | Правый BTS7960 `REN` |
| `RIGHT_MOTOR_LEN` | `21` | Правый BTS7960 `LEN` |
| `MOTOR1_INVERTED` | `0` | Инверсия мотора 1 |
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
CH_BEACON=5
CH_MUTE=6
```

Для текущего робота c проводкой `LEFT 18/13` и `RIGHT 12/19` оставляйте `BTS7960_PWM_MODE=SOFTWARE`. Кодовый дефолт `HARDWARE` сохранён для будущих конфигураций без конфликта hardware-PWM каналов.

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

BiBa использует пьезо-буззер на GPIO17 для:

- startup/shutdown мелодий
- arm/disarm сигналов
- low-voltage warning
- сигнала потери связи
- SOS-маяка после длительного failsafe

На передатчике EdgeTX Lua-скрипт дополнительно проигрывает `playTone` события при старте, восстановлении/потере связи и low battery.

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

Убедитесь, что USB-UART адаптер подключен. Если порт отличается от `/dev/ttyUSB0`, обновите `BMS_PORT` в `docker-compose.yml`.

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
ls -la /dev/ttyAMA0             # проверить UART
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
docker compose -f ~/biba/docker-compose.yml logs --tail 50
```

Частая причина — pigpiod не может подключиться к GPIO. Убедитесь, что `/dev/gpiomem` существует и контейнер запускается с `privileged: true`.

### Образ не pull'ится

```bash
docker login ghcr.io            # проверить авторизацию
docker pull ghcr.io/goodworkrinkz/biba/biba-controller:latest
```

Убедитесь, что токен имеет право `read:packages`.
