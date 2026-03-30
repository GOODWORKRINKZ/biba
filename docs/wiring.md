# Подключение

## Распиновка Raspberry Pi Zero 2W

| Назначение | GPIO BCM | Физический пин |
| --- | --- | --- |
| ELRS TX (Pi -> RX приемника) | 14 | 8 |
| ELRS RX (Pi <- TX приемника) | 15 | 10 |
| I2C SDA (ADS1115, опционально) | 2 | 3 |
| I2C SCL (ADS1115, опционально) | 3 | 5 |
| Left BTS7960 RPWM | 18 | 12 |
| Left BTS7960 LPWM | 13 | 33 |
| Left BTS7960 REN | 23 | 16 |
| Left BTS7960 LEN | 24 | 18 |
| Right BTS7960 RPWM | 12 | 32 |
| Right BTS7960 LPWM | 19 | 35 |
| Right BTS7960 REN | 20 | 38 |
| Right BTS7960 LEN | 21 | 40 |
| GND драйвера | - | 14 |

## Статус текущей двухмоторной проводки

Текущая распиновка выше считается рабочей эксплуатационной схемой для двух BTS7960 на Pi Zero 2W.

- `LEFT RPWM=12` и `LEFT LPWM=18` делят hardware PWM channel 0.
- `RIGHT RPWM=19` и `RIGHT LPWM=13` делят hardware PWM channel 1.
- Поэтому для одновременной работы двух моторов с этой проводкой нужно явно выставлять `BTS7960_PWM_MODE=SOFTWARE`.

Пример текущего runtime-конфига:

```ini
BTS7960_PWM_MODE=SOFTWARE
LEFT_MOTOR_ENABLED=1
RIGHT_MOTOR_ENABLED=1
LEFT_MOTOR_RPWM=12
LEFT_MOTOR_LPWM=18
RIGHT_MOTOR_RPWM=19
RIGHT_MOTOR_LPWM=13
```

## Целевая hardware-PWM конфигурация

Кодовый дефолт `BTS7960_PWM_MODE=SOFTWARE` оставлен намеренно: это безопасный режим для текущей рабочей проводки.

Для Raspberry Pi Zero 2W это означает одно из двух:

- либо включён только один BTS7960-мотор на паре `RPWM/LPWM`, использующей разные hardware-каналы;
- либо двухмоторная схема переведена на внешний PWM-генератор или другой драйвер, который не требует четырёх независимых hardware-PWM линий от самой Pi.

С текущей проводкой `12/18` и `19/13` режим `HARDWARE` для двух моторов использовать нельзя.

## Подключение current sense через ADS1115

Для ограничения по току и вывода токов колёс в телеметрию контроллер может читать BTS7960 `IS`-линии через ADS1115.

Рекомендуемая схема первого варианта:

| Сигнал | Куда подключать |
| --- | --- |
| ADS1115 VDD | 3.3V Raspberry Pi |
| ADS1115 GND | GND Raspberry Pi |
| ADS1115 SDA | GPIO 2 / pin 3 |
| ADS1115 SCL | GPIO 3 / pin 5 |
| Left BTS7960 `R_IS` | ADS1115 A2 |
| Left BTS7960 `L_IS` | ADS1115 A3 |
| Right BTS7960 `R_IS` | ADS1115 A0 |
| Right BTS7960 `L_IS` | ADS1115 A1 |
| Общая земля силовой части | Общая с GND Raspberry Pi и ADS1115 |

Текущая реализация использует по два ADS1115-канала на мотор: отдельный sense-вход для прямого и обратного направления. Активный канал выбирается по знаку duty в рантайме.

## Env-переменные current sense и limiter

Минимальный набор для включения функции:

```ini
MOTOR_CURRENT_SENSE_ENABLED=1
MOTOR_CURRENT_LIMITING_ENABLED=1
MOTOR_CURRENT_SENSE_I2C_ADDRESS=72
LEFT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL=2
LEFT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL=3
RIGHT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL=0
RIGHT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL=1
MOTOR_CURRENT_SENSE_GAIN=1
MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ=32
LEFT_MOTOR_MAX_CURRENT_A=18
RIGHT_MOTOR_MAX_CURRENT_A=18
LEFT_MOTOR_MAX_POWER_W=180
RIGHT_MOTOR_MAX_POWER_W=180
MOTOR_LIMIT_FALLBACK_VOLTAGE=24.0
LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V=0.0
RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V=0.0
LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT=1.0
RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT=1.0
```

Назначение:

- `MOTOR_CURRENT_SENSE_ENABLED=1` включает чтение ADS1115.
- `MOTOR_CURRENT_LIMITING_ENABLED=1` включает уменьшение PWM по measured current/power.
- `*_FORWARD_CHANNEL` и `*_REVERSE_CHANNEL` задают ADS1115-каналы для каждого направления каждого мотора.
- `*_MAX_CURRENT_A` ограничивают ток каждого мотора независимо.
- `*_MAX_POWER_W` ограничивают мощность каждого мотора независимо.
- `MOTOR_LIMIT_FALLBACK_VOLTAGE` используется для расчёта мощности, если Daly BMS временно недоступен.
- `*_ZERO_OFFSET_V` и `*_AMPS_PER_VOLT` задают калибровку конкретного BTS7960-модуля.

Если нужно только видеть токи колёс в телеметрии, а резать PWM пока не нужно, оставьте:

```ini
MOTOR_CURRENT_SENSE_ENABLED=1
MOTOR_CURRENT_LIMITING_ENABLED=0
```

Для калибровочных прогонов можно отдельно включить trace-файл:

```ini
MOTOR_CURRENT_TRACE_ENABLED=1
MOTOR_CURRENT_TRACE_PATH=/data/current-trace.jsonl
MOTOR_CURRENT_TRACE_POST_ROLL_S=2.0
MOTOR_CURRENT_TRACE_MIN_INTERVAL_S=0.0
```

Назначение:

- `MOTOR_CURRENT_TRACE_ENABLED=1` включает JSONL-трейс в основном controller loop.
- `MOTOR_CURRENT_TRACE_PATH` задаёт путь файла на persistent volume.
- `MOTOR_CURRENT_TRACE_POST_ROLL_S` помогает поймать запаздывающий ток BMS после окончания движения.
- `MOTOR_CURRENT_TRACE_MIN_INTERVAL_S` позволяет ограничить частоту записи, если trace становится слишком плотным.

## Калибровка BTS7960 `IS`

`IS` у BTS7960 на дешёвых модулях нельзя считать абсолютно точным датчиком без калибровки. Для первого запуска используйте такой порядок:

1. Включите только измерение, без limiter:
	`MOTOR_CURRENT_SENSE_ENABLED=1`, `MOTOR_CURRENT_LIMITING_ENABLED=0`.
2. Оставьте мотор без нагрузки и снимите напряжение на `IS`.
	Это значение запишите в `LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V` и `RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V`.
3. Дайте известную нагрузку и измерьте реальный ток внешним прибором.
4. Посчитайте коэффициент:

$$
amps\_per\_volt = \frac{I_{measured}}{V_{is} - V_{offset}}
$$

5. Запишите коэффициенты в `LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT` и `RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT`.
6. После этого включайте `MOTOR_CURRENT_LIMITING_ENABLED=1` и подбирайте `*_MAX_CURRENT_A` и `*_MAX_POWER_W` уже по реальным данным.

## Примечания

- Включите основной UART на Raspberry Pi и освободите его от Bluetooth перед использованием CRSF на скорости 420000 бод.
- Daly BMS подключается по BLE или через USB-UART адаптер и обычно появляется как `/dev/ttyUSB0` в UART-режиме.
- Для BTS7960 каждый мотор использует две линии PWM (`RPWM` и `LPWM`) и две линии enable (`REN`, `LEN`).
- Звуковая индикация и voice playback в текущей конфигурации идут через моторы, отдельный buzzer не требуется.
- Для Ubuntu на Raspberry Pi включите I2C через `/boot/firmware/config.txt` или `/boot/firmware/usercfg.txt`: добавьте строку `dtparam=i2c_arm=on`, перезагрузите плату и проверьте наличие `/dev/i2c-1`.
- Для ухода от слышимого свиста software PWM желательно временно оставить только как workaround. Полный hardware PWM на двух BTS7960 с текущими GPIO `12`, `13`, `18`, `19` конфликтует по shared channels.
- Если на конкретной плате `REN` и `LEN` объединены, это можно переопределить одинаковыми значениями в env-конфигурации.
- Если `IS` не выведен наружу на вашем BTS7960-модуле, текущая реализация current sense не заработает: нужен либо другой модуль, либо отдельный датчик тока.
- Земля силовой части и земля Raspberry Pi должны быть объединены.
- Если одно из колёс вращается в неверную сторону, это можно исправить без перепайки через `MOTOR1_INVERTED` или `MOTOR2_INVERTED` в compose-конфигурации.

## Рекомендуемая конфигурация Raspberry Pi

Добавьте следующие строки в `/boot/firmware/config.txt` или `/boot/config.txt` в зависимости от образа системы:

```ini
enable_uart=1
dtoverlay=disable-bt
```

После этого отключите serial console, если она включена, и перезагрузите плату.

Для Ubuntu на Raspberry Pi I2C обычно включается так:

```bash
sudo apt update
sudo apt install -y i2c-tools
sudoedit /boot/firmware/config.txt
```

Добавьте строку:

```ini
dtparam=i2c_arm=on
```

Если в `config.txt` уже подключается `usercfg.txt`, можно положить эту строку туда вместо правки основного файла.

После перезагрузки проверьте:

```bash
ls /dev/i2c-*
sudo i2cdetect -y 1
```

Для ADS1115 по умолчанию ожидается адрес `0x48`, поэтому в выводе `i2cdetect` обычно должен появиться `48`.