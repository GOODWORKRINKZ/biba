# Подключение

## Распиновка Raspberry Pi Zero 2W

| Назначение | GPIO BCM | Физический пин |
| --- | --- | --- |
| ELRS TX (Pi -> RX приемника) | 14 | 8 |
| ELRS RX (Pi <- TX приемника) | 15 | 10 |
| I2C SDA (ADS1115 / BMI160, опционально) | 2 | 3 |
| I2C SCL (ADS1115 / BMI160, опционально) | 3 | 5 |
| Left BTS7960 RPWM | 12 | 32 |
| Left BTS7960 LPWM | 18 | 12 |
| Left BTS7960 REN | 23 | 16 |
| Left BTS7960 LEN | 24 | 18 |
| Right BTS7960 RPWM | 19 | 35 |
| Right BTS7960 LPWM | 13 | 33 |
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

## Подключение IMU для stabilized / heading-hold

Новый stabilized / heading-hold режим использует IMU на том же `I2C-1`, что и ADS1115. Контроллер умеет autodetect для двух семейств датчиков: BMI160/BMI166 и ST LSM6DS3-class. Датчик можно вешать на общие `SDA/SCL`, если его адрес не конфликтует с `0x48` ADS1115.

Рекомендуемая схема подключения:

| Сигнал | Куда подключать |
| --- | --- |
| IMU VDD | 3.3V Raspberry Pi |
| IMU GND | GND Raspberry Pi |
| IMU SDA | GPIO 2 / pin 3 |
| IMU SCL | GPIO 3 / pin 5 |
| IMU ADDR/SDO/SA0 | По схеме модуля; BMI обычно `0x68/0x69`, ST LSM6DS3-class обычно `0x6A/0x6B` |

Минимальный env-набор для включения IMU:

```ini
IMU_ENABLED=1
IMU_I2C_BUS=1
IMU_I2C_ADDRESS=104
IMU_EXPECTED_CHIP_ID=209
IMU_SAMPLE_RATE_HZ=100.0
IMU_STALE_TIMEOUT_S=0.2
IMU_GYRO_BIAS_CALIBRATION_S=1.0
IMU_GYRO_Z_SIGN=1.0
```

На текущем роботе probing показал ST LSM6DS3-class модуль на `0x6A`, так что для него нужно переопределить `IMU_I2C_ADDRESS=106`.

Если IMU установлена развернутой по yaw-оси, поменяйте `IMU_GYRO_Z_SIGN` на `-1.0` вместо перепайки.

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
Для BMI160/BMI166-compatible IMU обычно ожидается `0x68` или `0x69`, для ST LSM6DS3-class чаще `0x6A` или `0x6B`, так что в таблице `i2cdetect` должен появиться ещё один адрес рядом с ADS1115.
## Подключение STM32F103

Прошивка [firmware/stm32f103](../firmware/stm32f103) — опциональный
STM32F103C8T6 ("Blue Pill") добавочный контроллер, который умеет
работать либо самостоятельно (CRSF + BTS7960 + лимитер), либо
SPI-slave к Raspberry Pi. Подробности — в
[docs/stm32_architecture.md](stm32_architecture.md).

Выбор режима жёстко определяется сборочным env (`standalone` /
`companion`) или пином `MODE_SEL` (только в env `combined`).

### Распиновка STM32F103C8T6 (target `BLUEPILL_F103C8`)

Это эталонная распиновка target'а `BLUEPILL_F103C8`
(см. [`firmware/stm32f103/targets/BLUEPILL_F103C8/target.md`](../firmware/stm32f103/targets/BLUEPILL_F103C8/target.md)).
Другие target'ы (например, `BIBA_F103_REV_A`) могут назначать эти
функции на другие пины — всегда сверяйтесь с `target.md` конкретной
платы, которую собираете.

| Назначение                                    | Пин STM32  |
| --------------------------------------------- | ---------- |
| TIM1_CH1 — Left RPWM                          | PA8        |
| TIM1_CH2 — Left LPWM                          | PA9        |
| TIM1_CH3 — Right RPWM                         | PA10       |
| TIM1_CH4 — Right LPWM                         | PA11       |
| Left BTS7960 R_EN / L_EN                      | PB0 / PB1  |
| Right BTS7960 R_EN / L_EN                     | PB5 / PB8  |
| ADC1 IN0..IN3 — 4× BTS7960 `IS` (L+R, L+R)    | PA0..PA3   |
| ADC1 IN4 — VBAT через делитель 1:11           | PA4        |
| ADC1 IN5 — опционально 12V rail (1:11)        | PA5        |
| ADC1 IN6 — резерв                             | PA6        |
| SPI2 NSS / SCK / MISO / MOSI (slave к SBC)    | PB12 / PB13 / PB14 / PB15 |
| USART3 TX / RX — CRSF                         | PB10 / PB11 |
| I2C1 SCL / SDA — IMU                          | PB6 / PB7  |
| DATA_READY → SBC (GPIO-прерывание)            | PA12       |
| MODE_SEL (pull-up; GND = companion)           | PB9        |
| Status LED (on-board blue pill)               | PC13       |
| SWD (оставлять для прошивки / отладки)        | PA13 / PA14 |

Конкретные значения собраны в `firmware/stm32f103/include/biba_board.h` и
`include/biba_config.h` — там же настраиваются частота PWM,
current-sense калибровка и таймауты failsafe.

### Нюансы, которые легко пропустить

- `USART1` на стандартных пинах `PA9/PA10` конфликтует с TIM1_CH2/CH3
  и не используется. CRSF едет через `USART3` (PB10/PB11).
- Перед тем как PB3/PB4/PA15 заработают как GPIO, прошивка отключает
  JTAG в `biba_hal_init()` (SWD остаётся доступен для прошивки).
  Поэтому `Left R_EN`=PB3 и `Left L_EN`=PB4 — это освобождённые
  JTAG-пины; если вы не отпускаете JTAG, перенесите enable-пины в
  `biba_board.h`.
- BTS7960 питаются отдельным силовым 5V/6V, а земля должна быть общей с
  STM32. VCC BOARD на STM32 — с 3.3V линии USB-UART программатора или
  с BEC.

### SPI к Raspberry Pi (companion mode)

| STM32     | Pi GPIO (BCM) | Физический пин Pi |
| --------- | ------------- | ------------------ |
| SPI2 NSS  | GPIO 8 (CE0)  | 24                 |
| SPI2 SCK  | GPIO 11       | 23                 |
| SPI2 MOSI | GPIO 10       | 19                 |
| SPI2 MISO | GPIO 9        | 21                 |
| DATA_READY| GPIO 25       | 22 (опциональное IRQ) |
| GND       | GND           | 20                 |

Для включения SPI-моста выставьте `STM32_LINK_ENABLED=1` в env-файле
Pi-runtime (см. `biba-controller/config.py`).
