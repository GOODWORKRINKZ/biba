# Таргет: RP2040_BLDC_VESC_CAN

RP2040-вариант BiBa для управления парой BLDC-приводов через
**Flipsky dual FSESC** (спаренный VESC) по CAN. Третий BLDC-таргет
проекта наряду с `RP2040_BLDC_ODRIVE_CAN` и
`RP2040_BLDC_ODRIVE_UART`.

Электрически это **тот же самый мост MCP2515+TJA1050 на SPI0**, что и
у ODrive-CAN-таргета — распиновка Pico совпадает пин-в-пин. Отличается
диалект шины: VESC говорит 29-битными расширенными ID на 500 кбит/с,
ODrive CANSimple — 11-битными на 250 кбит/с.

> **Спутник:** `docs/adr/0002-target-naming-and-vesc.md` — почему
> VESC заехал отдельным таргетом, а не флагом внутри BLDC-таргета, и
> почему имя таргета теперь несёт тип линка.

## Распиновка по группам периферии

### 1. CRSF / ELRS приёмник (UART0)

| Пин | Сигнал   | Направление | Примечание                   |
|-----|----------|-------------|------------------------------|
| GP0 | CRSF_TX  | ВЫХ UART0  | К пину RX приёмника          |
| GP1 | CRSF_RX  | ВХ  UART0  | От пина TX приёмника         |

### 2. MCP2515 SPI→CAN мост (SPI0)

| Пин  | Сигнал  | Направление | Примечание                            |
|------|---------|-------------|---------------------------------------|
| GP16 | SO/MISO | ВХ SPI0     | ← MCP2515 SO                          |
| GP17 | CS      | ВЫХ GPIO    | Чип-селект MCP2515, active LOW        |
| GP18 | SCK     | ВЫХ SPI0    | SPI clock, ~7.8125 МГц (HW SPI0)      |
| GP19 | SI/MOSI | ВЫХ SPI0    | → MCP2515 SI                          |
| GP15 | INT     | ВХ GPIO IRQ | MCP2515 → host, open-drain (active low), on-board 10 kΩ pull-up |

Режим SPI — **Mode 0,0** (CPOL=0, CPHA=0), **MSB first**, baud
**7.8125 МГц**. Один в один с ODrive-таргетом: это тот же драйвер
`drivers/mcp2515.c`, разница только в тайминге шины и режиме
фильтров (см. §3).

### 3. Подключение к Flipsky dual FSESC

По схеме производителя (лист «Wiring diagram», разъём **1. CAN**):

| FSESC «CAN» | Куда                                              |
|-------------|---------------------------------------------------|
| `CAH`       | CANH трансивера TJA1050 на модуле MCP2515         |
| `CAL`       | CANL трансивера TJA1050                           |
| `-`         | Общая земля Pico ↔ FSESC                          |
| `5V`        | **не подключать** — модуль MCP2515 питается от 5 В Pico, чтобы ребут FSESC не ронял мост |

Важные детали именно этой платы:

- **Переключатель `ON: dual` / `OFF: single`** должен стоять в
  положении **dual**. Обе половины FSESC уже сидят на одной внутренней
  CAN-шине, поэтому достаточно подключиться к **одному** из двух
  разъёмов CAN.
- **VESC ID.** Обе половины с завода имеют ID `0`. Правой надо задать
  `1` в VESC Tool (*App Settings → General → VESC ID*), иначе прошивка
  физически не может их различить, и оба колеса отвечают на каждую
  команду. Дефолты — в `target_config.h`
  (`BIBA_BLDC_LEFT_NODE_ID` / `BIBA_BLDC_RIGHT_NODE_ID`).
- **CAN status messages.** В VESC Tool (*App Settings → General → CAN
  status message mode*) включить как минимум `CAN_STATUS_1_4_5` на
  50 Гц. Без них колёса крутятся, но прошивка считает оба узла
  мёртвыми и не даёт заармиться: телеметрии (напряжение, ток,
  liveness) взять больше неоткуда.
- **Терминатор.** У FSESC своего 120 Ω нет, у модуля MCP2515 —
  есть (джампер `RTERM`). Оставить его установленным. На шине меньше
  метра одного терминатора хватает; если полезут ошибки — добавить
  второй 120 Ω со стороны FSESC.

Параметры шины:

| Параметр | Значение |
|----------|----------|
| Шина | CAN 2.0B, **29-bit extended ID**, **500 кбит/с** |
| Адресация | `ext_id = vesc_id \| (packet_id << 8)` |
| Порядок байт | **big-endian** (в ODrive CANSimple — little-endian!) |
| Команда цикла | `SET_DUTY` / `SET_RPM` / `SET_CURRENT` @ 50 Гц, выбор через `BIBA_VESC_CONTROL_MODE` |
| Телеметрия | `STATUS` (ERPM, ток, duty), `STATUS_4` (температуры), `STATUS_5` (напряжение) |
| Фильтры MCP2515 | **accept-all** (`BIBA_MCP2515_ACCEPT_ALL = 1`) |

Почему accept-all: у VESC номер узла живёт в младшем байте 29-битного
ID, и аппаратные фильтры MCP2515 в стандартном режиме не умеют
выразить «любой VESC, вот эти типы пакетов». На шине из двух узлов
программный демукс дешевле возни с extended-масками — подробности в
шапке `src/drivers/vesc_can.h`.

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

### 6. Свободные пины (резерв)

GP2 / GP3 / GP6 / GP7 / GP8 / GP9 / GP10 / GP11 / GP12 / GP13 / GP14 —
свободны.

GP4 / GP5 **зарезервированы** под UART-линк к FSESC (разъём
**3. COMM**, пины `TX` / `RX`), но не разведены: по принятому стандарту
именования это был бы отдельный таргет `RP2040_BLDC_VESC_UART`,
которого пока нет.

### 7. Аналоговые входы

Все четыре канала RP2040 ADC (GP26 / GP27 / GP28 / GP29) на этом
таргете **не задействованы** — напряжение, ток и температуры приходят
из status-кадров VESC. `BIBA_ADC_SCAN_LEN = 0`.

## Режим управления

`biba_bldc_drive()` отдаёт нормированные `[-1, +1]`; как это ложится
на провод, решает `BIBA_VESC_CONTROL_MODE`:

| Режим | Пакет | Когда брать |
|-------|-------|-------------|
| `BIBA_VESC_MODE_DUTY` (по умолчанию) | `SET_DUTY` | Первый запуск. Работает на любом моторе, у которого прошла детекция: ни энкодера, ни PID-тюнинга, ни холлов не нужно. Ведёт себя как BTS7960-таргеты, поэтому вся тюнинговка ramp/trim/failsafe в `src/modes` переносится без правок. |
| `BIBA_VESC_MODE_ERPM` | `SET_RPM` | Когда подключены холлы (разъём **2. SENSE**: `H1`/`H2`/`H3`/`TMP`/`5V`/`-`) и прошла hall-детекция. Колёса держат скорость на уклоне — этого и хочет PI-петля в `src/app/rpm_pi.c`. |
| `BIBA_VESC_MODE_CURRENT` | `SET_CURRENT` | Моментное управление, для экспериментов с тягой. |

ERPM — электрические обороты: `ERPM = RPM × число пар полюсов`.
Для 14-полюсного (7 пар) мотор-колеса 12000 ERPM ≈ 1700 об/мин вала.

## Что отличается от `RP2040_BLDC_ODRIVE_CAN`

- Драйвер `drivers/vesc_can.c` вместо `drivers/odrive_can.c`
  (оба реализуют один контракт `drivers/bldc.h`).
- 29-битные ID вместо 11-битных, 500 кбит/с вместо 250, big-endian
  вместо little-endian.
- **Нет арм/дизарм-состояния.** У ODrive есть `Set_Axis_State`
  (CLOSED_LOOP / IDLE); у VESC такого понятия нет. Дизарм = послать
  ноль и замолчать; страхует собственный таймаут VESC (*App Settings →
  General → Timeout*, 1 с по умолчанию). Пока заармлены, прошивка шлёт
  setpoint 50 раз в секунду; пока разармлены — шлёт явный ноль.
- **Нет `Clear_Errors`.** В наборе CAN-команд VESC эквивалента нет:
  фаулты держатся ровно пока держится их причина.
- **Нет remote-reset.** `biba_bldc_reset_count()` всегда 0 —
  это лечение зависания CANSimple-стека ODrive, у VESC такой болезни
  нет.
- Лимиты тока/скорости живут **в конфиге VESC**, а не в кадре
  `Set_Limits`. `target_config.h` только маппит `[-1, +1]` на провод.

## Что отличается от `RP2040_DC_BTS7960_PWM`

- **BTS7960 убран.** `BIBA_TARGET_HAS_BTS7960_2CH = 0`, пины
  `GP2..GP9` свободны, `drivers/bts7960.c` исключён из сборки.
- **Native ADC scan убран** — ток и напряжение приходят из VESC.
  Макросы IS/IBAT/VBAT в `target_config.h` занулены.
- **Добавлен MCP2515** (GP15/16/17/18/19) и драйверы
  `drivers/mcp2515.c`, `drivers/can_queue.c`, `drivers/vesc_can.c`,
  `hal/biba_hal_motor_bldc.c`.

## Build

```bash
# VESC, standalone
pio run -e rp2040_bldc_vesc_can_standalone

# VESC, companion (SBC по USB-CDC)
pio run -e rp2040_bldc_vesc_can_companion

# VESC, combined (режим выбирается на MODE_SEL)
pio run -e rp2040_bldc_vesc_can_combined
```

Переключение между таргетами — это выбор env, не флаг в исходниках:

```bash
pio run -e rp2040_dc_bts7960_pwm_standalone     # щёточные DC + BTS7960
pio run -e rp2040_bldc_odrive_can_standalone    # BLDC + ODrive по CAN
pio run -e rp2040_bldc_odrive_uart_standalone   # BLDC + ODrive по UART
pio run -e rp2040_bldc_vesc_can_standalone      # BLDC + VESC по CAN
```

## Порядок первого запуска

Делать строго по порядку — шаги 1–3 колёса не крутят.

1. **VESC Tool, обе половины по USB отдельно:**
   - прогнать детекцию мотора (*Motor Setup Wizard*);
   - выставить `Motor Current Max` / `Battery Current Max` /
     `Max ERPM` — это и есть настоящие лимиты, прошивка их не дублирует;
   - задать `VESC ID`: левой `0`, правой `1`;
   - *App Settings → General*: `CAN baud rate = 500k`,
     `CAN status message mode = CAN_STATUS_1_4_5`, `Timeout = 1000 ms`;
   - сохранить (**Write App Configuration** + **Write Motor
     Configuration**), переключатель платы в `dual`.
2. **Прошить Pico** `rp2040_bldc_vesc_can_standalone`, USB-CDC открыть
   терминалом.
3. **Проверить шину без движения** (питание моторов отключено, FSESC
   запитан): в телеметрии `rx` должен расти (status-кадры идут
   постоянно), `alive_l` и `alive_r` — `1`, напряжение батареи
   совпадать с реальным. Если `rx` стоит на нуле — не совпал
   baud rate либо не включены status messages. Если `alive_r = 0` —
   не сменили VESC ID правой половине.
4. **Колёса в воздух**, армить с пульта, малый газ: левое колесо
   вперёд от левого узла, правое — от правого. Поехало назад — флипнуть
   `BIBA_VESC_LEFT_DIR` / `BIBA_VESC_RIGHT_DIR` в `target_config.h`.
5. **Проверить фейлсейф**: выключить пульт — колёса должны встать
   сразу (явный ноль), а не через секунду по таймауту VESC.

## References

- `../RP2040_BLDC_ODRIVE_CAN/target.md` — ODrive-вариант той же шины
- `../RP2040_DC_BTS7960_PWM/target.md` — щёточный таргет, для сравнения
- `docs/adr/0002-target-naming-and-vesc.md` — ADR: стандарт имён + VESC
- `docs/mcp2515_bldc_research.md` — ресёрч по MCP2515 и физике CAN
- `src/drivers/vesc_can.h` — таблица пакетов VESC и их масштабы
