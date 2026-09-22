# Таргет: RP2040_BLDC_ODRIVE_UART

RP2040-вариант BiBa для управления парой ODrive по **ASCII-протоколу
на UART1**. Близнец `RP2040_BLDC_ODRIVE_CAN`: те же контроллеры, тот
же контракт `drivers/bldc.h`, та же логика режимов — другой физический
линк.

Это **два разных таргета, а не флаг**, потому что распиновка реально
разная: здесь два пина UART1, там мост MCP2515 на SPI0. Причина
разделения зафиксирована в `docs/adr/0002-target-naming-and-vesc.md`.

> **Почему UART, а не CAN.** CANSimple-стек в прошивке ODrive 0.5.6
> тихо залипает на холостом ходу: контроллер перестаёт слать
> heartbeat, но продолжает принимать команды и остаётся в closed-loop.
> ASCII-линк этой болезнью не страдает, поэтому в продакшене сейчас
> именно он. История вопроса — `docs/adr/0001-pico-bldc-target.md`.

## Распиновка по группам периферии

### 1. CRSF / ELRS приёмник (UART0)

| Пин | Сигнал   | Направление | Примечание                   |
|-----|----------|-------------|------------------------------|
| GP0 | CRSF_TX  | ВЫХ UART0  | К пину RX приёмника          |
| GP1 | CRSF_RX  | ВХ  UART0  | От пина TX приёмника         |

### 2. ODrive UART-A (UART1)

| Пин | Сигнал  | Направление | Примечание                       |
|-----|---------|-------------|----------------------------------|
| GP4 | UART1_TX | ВЫХ UART1  | → ODrive UART-A RX (GPIO1)       |
| GP5 | UART1_RX | ВХ  UART1  | ← ODrive UART-A TX (GPIO2)       |
| —   | GND      | —           | Обязательная общая земля         |

Baud — **115200** (`BIBA_ODRIVE_UART_BAUD`), 8N1. UART0 занят CRSF,
поэтому ODrive достаётся UART1.

Оба ODrive висят на **одной паре проводов**: команда адресует ось
номером внутри самой ASCII-строки (`v 0 …` / `v 1 …`), поэтому
отдельный линк на каждый контроллер не нужен.

Со стороны ODrive UART-A надо включить:

```python
odrv0.config.enable_uart_a = True
odrv0.config.uart_a_baudrate = 115200
odrv0.save_configuration()
```

Готовый скрипт — `scripts/odrive_setup_uart.py`.

### 3. Что НЕ разведено

| Пины | Почему свободны |
|------|-----------------|
| GP15, GP16–GP19 | MCP2515 (INT + SPI0) — только на `RP2040_BLDC_ODRIVE_CAN`. `BIBA_TARGET_HAS_MCP2515 = 0` |
| GP2, GP3, GP6–GP14 | Резерв общего назначения |

### 4. IMU (I2C0) — без изменений относительно RP2040_DC_BTS7960_PWM

| Пин   | Сигнал   | Направление | Примечание               |
|-------|----------|-------------|--------------------------|
| GP20  | I2C0_SDA | I/O I2C     | IMU + ADS1115 + AHT30    |
| GP21  | I2C0_SCL | ВЫХ I2C     |                          |
| GP22  | IMU_INT1 | ВХ GPIO     |                          |

### 5. Статус и RGB LED

| Пин   | Сигнал | Примечание                          |
|-------|--------|-------------------------------------|
| GP25  | LED    | Onboard LED Pico, active high       |
| GP23  | WS2812 | YD-RP2040 NeoPixel                  |

### 6. Аналоговые входы

Все четыре канала RP2040 ADC (GP26 / GP27 / GP28 / GP29) на этом
таргете **не задействованы** — напряжение шины и ток мотора приходят
от ODrive по ASCII-линку. `BIBA_ADC_SCAN_LEN = 0`, макросы
IS/IBAT/VBAT в `target_config.h` занулены.

## Что отличается от `RP2040_BLDC_ODRIVE_CAN`

- Драйвер `drivers/odrive_uart.c` вместо `drivers/odrive_can.c`
  (оба реализуют контракт `drivers/bldc.h`).
- `BIBA_ODRIVE_LINK_UART = 1` зафиксирован в `target_config.h` — это
  больше не переключатель, а свойство таргета.
- Нет MCP2515, нет `can_queue`, нет CAN-тайминга: параметры
  `BIBA_CAN_BITRATE_BPS` / фильтров здесь отсутствуют.
- Liveness считается не по heartbeat, а по ответу на опрос:
  `BIBA_ODRIVE_UART_TIMEOUT_MS` (500 мс, опрос каждые ~200 мс).

## Build

```bash
pio run -e rp2040_bldc_odrive_uart_standalone
pio run -e rp2040_bldc_odrive_uart_companion
pio run -e rp2040_bldc_odrive_uart_combined
```

## Проверка после прошивки

1. **Линк**: в телеметрии по USB-CDC счётчики `tx` / `rx` растут,
   `alive_l` и `alive_r` — `1`. Стоят на нуле — почти всегда не
   включён `enable_uart_a` либо перепутаны TX/RX.
2. **Drive**: колёса в воздух, малый газ — левое колесо от оси 0,
   правое от оси 1. Едет назад — флипнуть `BIBA_ODRIVE_LEFT_DIR` /
   `BIBA_ODRIVE_RIGHT_DIR`.
3. **Фейлсейф**: выключить пульт — прошивка перестаёт слать setpoint,
   ODrive разармится по собственному watchdog.

## References

- `../RP2040_BLDC_ODRIVE_CAN/target.md` — CAN-вариант тех же контроллеров
- `../RP2040_BLDC_VESC_CAN/target.md` — VESC-вариант BLDC-привода
- `docs/adr/0001-pico-bldc-target.md` — ADR по BLDC-таргету
- `docs/adr/0002-target-naming-and-vesc.md` — ADR: стандарт имён + VESC
- `scripts/odrive_setup_uart.py` — включение UART-A на ODrive
