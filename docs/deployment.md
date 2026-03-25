# Развёртывание BiBa на Raspberry Pi

## Предварительные требования

### Оборудование

- Raspberry Pi Zero 2W (или другая плата с arm64 и GPIO)
- ELRS-приемник, подключенный к UART (`/dev/ttyAMA0`)
- Daly BMS с USB-UART адаптером (`/dev/ttyUSB0`)
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
6. Создание systemd unit `biba-controller.service` для автозапуска

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
| `BMS_PORT` | `/dev/ttyUSB0` | USB-UART порт Daly BMS |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `MOTOR_DRIVER_TYPE` | `BTS7960` | Тип драйвера моторов: штатный `BTS7960` или старый `PWM_DIR` |
| `CH_STEERING` | `0` | Номер канала руления |
| `CH_THROTTLE` | `1` | Номер канала газа |
| `CH_ARM` | `4` | Номер канала арма |
| `BEACON_ENABLED` | `1` | Включить звуковой маяк/SOS на роботе |
| `BEACON_DELAY_S` | `300` | Через сколько секунд failsafe включать авто-SOS |
| `CH_BEACON` | `5` | Канал тумблера для ручного включения маяка |
| `RAMP_ACCEL_RATE` | `2.0` | Макс. скорость разгона мотора (ед/сек); 0→100% за 0.5с |
| `RAMP_DECEL_RATE` | `3.0` | Макс. скорость торможения (ед/сек); 100%→0 за 0.33с |
| `MOTOR_DEADBAND` | `0.05` | Мёртвая зона: значения ниже порога → мотор стоит |
| `LEFT_MOTOR_RPWM` | `18` | Левый BTS7960 `RPWM` |
| `LEFT_MOTOR_LPWM` | `13` | Левый BTS7960 `LPWM` |
| `LEFT_MOTOR_REN` | `23` | Левый BTS7960 `REN` |
| `LEFT_MOTOR_LEN` | `23` | Левый BTS7960 `LEN` (по умолчанию общий GPIO с `REN`) |
| `RIGHT_MOTOR_RPWM` | `12` | Правый BTS7960 `RPWM` |
| `RIGHT_MOTOR_LPWM` | `16` | Правый BTS7960 `LPWM` |
| `RIGHT_MOTOR_REN` | `20` | Правый BTS7960 `REN` |
| `RIGHT_MOTOR_LEN` | `20` | Правый BTS7960 `LEN` (по умолчанию общий GPIO с `REN`) |
| `MOTOR1_INVERTED` | `0` | Инверсия мотора 1 |
| `MOTOR2_INVERTED` | `0` | Инверсия мотора 2 |

Тег образа задается в `/etc/default/biba-controller` или `.env`:

```
BIBA_IMAGE_TAG=latest
MOTOR_DRIVER_TYPE=BTS7960
BEACON_ENABLED=1
BEACON_DELAY_S=300
CH_BEACON=5
```

### Звуковая индикация

BiBa использует пьезо-буззер на GPIO17 для:

- startup/shutdown мелодий
- arm/disarm сигналов
- low-voltage warning
- сигнала потери связи
- SOS-маяка после длительного failsafe

На передатчике EdgeTX Lua-скрипт дополнительно проигрывает `playTone` события при старте, восстановлении/потере связи и low battery.

## Troubleshooting

### Нет USB-устройства BMS

```bash
lsusb                           # проверить адаптер
ls -la /dev/ttyUSB*             # проверить порт
dmesg | tail -20                # лог ядра
```

Убедитесь, что USB-UART адаптер подключен. Если порт отличается от `/dev/ttyUSB0`, обновите `BMS_PORT` в `docker-compose.yml`.

### Нет CRSF-сигнала

```bash
bblogs | grep -i crsf           # поиск ошибок CRSF
ls -la /dev/ttyAMA0             # проверить UART
```

Убедитесь, что:
- UART включен в config.txt (`enable_uart=1`)
- Bluetooth отключен (`dtoverlay=disable-bt`)
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
