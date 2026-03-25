# Подключение

## Распиновка Raspberry Pi Zero 2W

| Назначение | GPIO BCM | Физический пин |
| --- | --- | --- |
| ELRS TX (Pi -> RX приемника) | 14 | 8 |
| ELRS RX (Pi <- TX приемника) | 15 | 10 |
| Buzzer | 17 | 11 |
| Left BTS7960 RPWM | 18 | 12 |
| Left BTS7960 LPWM | 13 | 33 |
| Left BTS7960 REN | 23 | 16 |
| Left BTS7960 LEN | 24 | 18 |
| Right BTS7960 RPWM | 12 | 32 |
| Right BTS7960 LPWM | 16 | 36 |
| Right BTS7960 REN | 20 | 38 |
| Right BTS7960 LEN | 21 | 40 |
| GND драйвера | - | 14 |

## Примечания

- Включите основной UART на Raspberry Pi и освободите его от Bluetooth перед использованием CRSF на скорости 420000 бод.
- Daly BMS подключается через USB-UART адаптер и обычно появляется как `/dev/ttyUSB0`.
- Для BTS7960 каждый мотор использует две линии PWM (`RPWM` и `LPWM`) и две линии enable (`REN` и `LEN`).
- Если на стенде `REN` и `LEN` временно соединены вместе, это можно отразить одинаковым GPIO в env-конфигурации.
- Земля силовой части и земля Raspberry Pi должны быть объединены.
- Если одно из колёс вращается в неверную сторону, это можно исправить без перепайки через `MOTOR1_INVERTED` или `MOTOR2_INVERTED` в compose-конфигурации.

## Рекомендуемая конфигурация Raspberry Pi

Добавьте следующие строки в `/boot/firmware/config.txt` или `/boot/config.txt` в зависимости от образа системы:

```ini
enable_uart=1
dtoverlay=disable-bt
```

После этого отключите serial console, если она включена, и перезагрузите плату.