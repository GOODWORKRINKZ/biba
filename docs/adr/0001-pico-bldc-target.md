# ADR-0001 — Новый firmware-таргет `RPICO_RP2040_BLDC`

| Поле | Значение |
|------|----------|
| **Статус** | Proposed |
| **Дата** | 2026-07-20 |
| **Автор** | architect (задача `t_3cca56ce`) |
| **Заменяет / supersedes** | — |
| **Relates to** | research `docs/mcp2515_bldc_research.md` (родительская задача #1) |
| **Downstream tasks** | `t_a3ed6b73` (драйвер MCP2515), `t_83ccac50` (общий decomposition) |

---

## 0. Контекст

Текущий RP2040-таргет `RPICO_RP2040` управляет двумя щёточными DC-моторами
через драйверы BTS7960 (см. `firmware/targets/RPICO_RP2040/target.md`).
Эксплуатация выявила тепловой режим как системное ограничение BTS7960 —
дешёвые модули без радиатора перегреваются после 20–30 минут активной езды.

Ресёрч (`docs/mcp2515_bldc_research.md`, родительская задача #1) исследовал
вариант замены коллекторных моторов на BLDC через ODrive Pro/S1/Micro,
соединённые с Pico через модуль **MCP2515 + TJA1050** по SPI. Вывод
ресёрча — production-канал CANSimple 11-bit ID, autobaud 250 кбит/с;
альтернативный канал ODrive UART ASCII @ 115200 для bench-test.

Настоящий ADR фиксирует архитектуру нового таргета
`RPICO_RP2040_BLDC` (директория `firmware/targets/RPICO_RP2040_BLDC/`),
включая:

1. Стек прошивки (Pico SDK + FreeRTOS vs bare-metal).
2. Способ подключения MCP2515 к Pico (HW SPI vs bit-banging vs PIO).
3. Структуру CAN-пакетов и дисциплину адресации узлов.
4. Способ переключения между существующим и новым таргетом.
5. Абстракцию motor backend (`bts7960` → `odrive_can`) без переписывания modes.

Цель: минимальный, обратимый, KISS-friendly дизайн, который ложится на
текущую target/ABI-дисциплину проекта (см. `firmware/targets/README.md`).

---

## 1. Решение

Мы вводим третий target **`RPICO_RP2040_BLDC`** как полноценную
параллель `RPICO_RP2040`. Он собирается из того же дерева `firmware/src/`,
но использует **другой набор драйверов** и **другую распиновку**.

Все шесть решений ниже образуют единый связный набор и должны быть
приняты/отвергнуты вместе.

### 1.1 Стек — bare-metal Pico SDK, без FreeRTOS

Решено: **bare-metal Pico SDK (через arduino-pico framework) + один
control loop на core0 + один secondary core poll на core1. Без
FreeRTOS.**

Обоснование:

- Существующий таргет уже использует паттерн «один setup() → один
  loop() → ISR/DMA-driven I/O». CRSF, ADC, PWM, WS2812 — всё работает
  через DMA + прерывания; никакой RTOS не нужен.
- Наша нагрузка на CAN-цикле:
  - 50 Гц `Set_Input_Vel` × 2 ODrive = 100 команд/с, payload 8 байт.
  - 100 Гц heartbeat/encoder-est через MCP2515 RXINT.
  - 200 Гц телеметрия в SBC (`biba_telemetry_publish`).
  - Итого: один десяток коротких SPI-транзакций в миллисекунду. На
    125 МГц это **ничтожная** нагрузка даже без DMA.
- FreeRTOS дал бы структурную ясность (отдельные task'и для CRSF,
  Motor, Telemetry), но потребовал бы:
  - подключения CMSIS-FreeRTOS через `lib_deps` PlatformIO;
  - переписывания `main_rp2040.cpp` (входная точка FreeRTOS отличается
    от Arduino setup/loop);
  - переноса lock-step семантики mode_dispatcher на семафоры.
- При нашем объёме выгода от RTOS **не окупает** её цену — это
  классический «overengineering because it's possible».

Альтернативы, которые **сознательно отвергнуты**:

- **FreeRTOS (SMP)** — рассмотрен выше, недостаточно обоснования для v1.
- **Zephyr** — слишком тяжёлый стек, нет оперативной выгоды для
  embedded-проекта 200 строк логики на BLDC.
- **Bare-metal без arduino-pico** — Pico SDK напрямую. Это устранило
  бы один слой зависимостей, но arduino-pico уже доехал до production и
  используется в существующем target — менять ради чистоты нерационально.

Точка обратимости: если в будущем придётся поддерживать >2 колёс
(новая ходовая часть) или SD-карту logging — переключение на FreeRTOS
SMP делается переносом `biba_mode_*_tick` в task'и. Это **локальное**
изменение, не требующее переделки mode API.

### 1.2 MCP2515 — аппаратный SPI0 Pico, не bit-banging

Решено: **аппаратный SPI0 Pico, baud 7.8125 МГц (делитель 16 от
125 МГц `clk_peri`), Mode 0,0, MSB first. CS = GP17 (GPIO). INT
= GP15 (GPIO с прерыванием).**

Обоснование:

- MCP2515 datasheet (DS20001801J, §Electrical Characteristics) cap —
  **10 МГц при Vdd ≥ 4.5 В** и **5 МГц при 3.0–4.5 В**. Берём
  7.8125 МГц: целочисленный делитель (без jitter), ниже cap, даёт
  ~50 µs SPI round-trip на пакет в худшем случае (read status + write
  TX buffer). Latency budget укладывается в control loop 20 мс с
  100× запасом.
- У RP2040 spi0 выделен на пины GP16(MISO)/GP18(SCK)/GP19(MOSI). Эти
  пины в текущем `RPICO_RP2040` target свободны — там заняты только
  GP0/1 CRSF, GP2-9 мотор, GP20/21 I2C, GP22 IMU_INT1, GP25 LED,
  GP26-29 ADC. GP15 у текущего таргета свободен. Никакого
  переиспользования нет.
- Bit-banging на RP2040 — антипаттерн: тратит CPU впустую (~10–50
  циклов на бит), джиттер зависит от того, что ISR делает, не
  отвечает требованию «10 МГц cap модуля» (а не «я могу поднять
  bit-bang до 20 МГц»). На реальном проекте ни одной причины для
  bit-banging.
- **PIO SPI** — реальная альтернатива HW SPI, если нужно гибко
  выбирать пины. В нашем случае GP16/18/19 свободны и идеально подходят,
  нет причины использовать PIO.

Альтернативы, отвергнутые сознательно:

- **Bit-banging SPI** — рассмотрен выше.
- **PIO SPI** — оставлен как fallback (комментарий в target.h), если
  когда-то понадобится иная распиновка.

Точка обратимости: замена на PIO SPI — это `mcp2515.c` внутренняя
деталь, mode API не меняется. CS, INT, формат MCP2515-пакетов — те
же. Принимаем «HW SPI сейчас, PIO если понадобится» без блокировки.

### 1.3 Структура CAN-пакетов — зеркалим ODrive CANSimple

Решено: использовать **ODrive CANSimple 1:1** как протокол поверх MCP2515.
Никакого собственного расширения, никакого байт-стаффинга, никакой
дополнительной CRC — всё, что нам нужно, уже документировано
(`docs/mcp2515_bldc_research.md` §6).

Конкретно:

| Параметр | Значение |
|----------|----------|
| CAN ID (11 bit) | `(node_id << 5) \| cmd_id` (`node_id ∈ 0..63`, `cmd_id ∈ 0..31`) |
| Endianness | little-endian |
| Float | IEEE-754 single (4 байта), LE byte order |
| Bit-rate | **250 кбит/с** для первого запуска. Переключение на 500 — одной перезагрузкой MCP2515 через `BIT-MODIFY CNF1/CNF2/CNF3` |
| Sample point | 87.5 % (1 sync + 6 propseg+phase1 + 1 phase2, SJW = 1) |
| Addressing | Хост держит таблицу `left → node_id` / `right → node_id`; по умолчанию `{0, 1}` |
| Frame filter | mask = `0x7E0` (фильтруем по `cmd_id`); acceptance filters на `Heartbeat(0x01)`, наши `node_id << 5`, broadcast `0x06` |

Обоснование: ODrive CANSimple — документированный, открытый, обратно
совместимый с любой стандартной ODrive-прошивкой. Не изобретаем
протокол — это анти-KISS и лишняя поверхность для багов.

Внутри firmware CAN-кадр представляется структурой:

```c
typedef struct {
    uint32_t id;          // 11-bit CAN ID
    uint8_t  dlc;         // 0..8
    uint8_t  data[8];
} biba_can_frame_t;
```

Этого достаточно — ODrive всегда использует ≤ 8 байт на команду
(`Set_Input_Vel`: 8 байт, `Set_Limits`: 8 байт, `Address`: 7 байт и т. д.).

### 1.4 Переключение таргетов — `platformio.ini` target-stanza

Решено: **target-stanza в `platformio.ini` + `[env:rpico_rp2040_bldc_*]`**
(envs по числу firmware mode). Никакого Kconfig, никакого
`menuconfig`-инструмента.

Обоснование:

- Существующая дисциплина проекта (см. `firmware/targets/README.md`,
  раздел «Как добавить новый таргет») — это именно PlatformIO target
  stanza. Каждый новый target добавляется копированием существующего
  env. Это **согласованная** практика проекта.
- Kconfig / `menuconfig` — это LVGL/Zephyr-стиль. Он тянет за собой
  огромный toolchain (Python scripts, генерация `*.h` из `*.config`),
  требует CI-адаптации, вынуждает переделывать `biba_config.h`-стиль
  через `#ifndef`-гарды (которые уже есть). Для одного нового таргета
  это **несоразмерное расширение** инфраструктуры.
- Параллельно с таргетом режим выбирается, как и раньше:
  `BIBA_MODE_STANDALONE` / `BIBA_MODE_COMPANION` / `BIBA_MODE_COMBINED`
  через `mode_*_build_flags`. Это **ортогональные** оси — target и
  mode — что даёт в матрице 3×N target'ов столько же env, сколько было.

Конкретные имена env (см. §2 для детальной раскладки):

```
[env:rpico_rp2040_bldc_standalone]
[env:rpico_rp2040_bldc_companion]
[env:rpico_rp2040_bldc_combined]
```

Сборка: `pio run -e rpico_rp2040_bldc_standalone`. Переключение между
старым и новым таргетом — смена имени env, никаких изменений в коде.

Точка обратимости: если когда-то захотим Kconfig (например, при
появлении > 8 таргетов с нетривиальными опциями) — миграция
происходит через `gen_kconfig` поверх существующих `#define`,
это **аддитивное** изменение.

### 1.5 Motor backend: `bts7960` → `odrive_can` через `BIBA_TARGET_HAS_*`

Решено: **новая пара функций `biba_odrive_*` с сигнатурой
API-совместимой с `biba_bts7960_*`** + `#if BIBA_TARGET_HAS_*`
в местах вызова в mode-коде. BTS7960 driver **не подменяется**, а
именно **заменяется** в таргете.

Обоснование:

- Текущая поверхность BTS7960 (4 функции — `set_enabled`, `drive`,
  `thermal_reset`, плюс зависимость от HAL) используется в:
  - `firmware/src/modes/mode_dispatcher.c` — init (1 вызов)
  - `firmware/src/modes/mode_standalone.c` — tick и arm-edge (3 вызова)
  - `firmware/src/modes/mode_companion.c` — tick и init (2 вызова)
  Всего **6 точек вызова**.
- Создание «общего» `biba_motor_backend_t` интерфейса с vtable —
  новый слой, который для двух backend'ов избыточен. Это анти-KISS.
- Соблюдаем уже работающую в проекте дисциплину
  `BIBA_TARGET_HAS_*` (см. `BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM`,
  `BIBA_TARGET_HAS_IMU`, etc.). Mode-код пишется как:
  ```c
  #if BIBA_TARGET_HAS_BTS7960_2CH
      biba_bts7960_drive(out.left, out.right);
  #elif BIBA_TARGET_HAS_BLDC_2CH
      biba_odrive_drive(out.left, out.right);
  #endif
  ```
  Это уже **привычный** паттерн для проекта.

Альтернатива, отвергнутая сознательно:

- **Виртуальный backend через vtable** — не для двух бэкендов.
- **Дублирование mode_*.c под каждый target** — мгновенный рост
  maintenance-стоимости и расхождение логики IMU-стабилизации между
  двумя файлами. Категорически нет.

Новая пара функций:

```c
void biba_odrive_set_enabled(bool enabled);     // → CAN Set_Axis_State
void biba_odrive_drive(float left, float right);// → CAN Set_Input_Vel
void biba_odrive_thermal_reset(uint32_t us);    // BLDC: no-op (ODrive собственный watchdog)
```

`drive` принимает аргументы **в тех же единицах**, что и BTS7960: `[-1, 1]`,
где `+1.0` = максимальная скорость вперёд, `-1.0` = максимальная
назад. `biba_odrive_drive` внутри умножает на
`BIBA_ODRIVE_MAX_VEL_REV_S`, упаковывает в float32 little-endian
и отправляет как `Set_Input_Vel` (cmd_id 0x0D) на node_id 0 и 1.

### 1.6 Распиновка (firmware/targets/RPICO_RP2040_BLDC/target.h)

Решено: занимаем ровно те пины, которые нужны. Делаем чистый
target-файл (не наследуем от `RPICO_RP2040`).

Сводная таблица:

| Функция | Pico GPIO | Peripheral | Цель |
|---------|-----------|------------|------|
| SPI0 SCK | GP18 | SPI0 SCK | MCP2515 SCK |
| SPI0 MOSI | GP19 | SPI0 TX | MCP2515 SI |
| SPI0 MISO | GP16 | SPI0 RX | MCP2515 SO |
| MCP2515 CS | GP17 | GPIO | MCP2515 CS |
| MCP2515 INT | GP15 | GPIO (с IRQ) | MCP2515 INT |
| CRSF TX | GP0 | UART0 TX | ELRS RX pin |
| CRSF RX | GP1 | UART0 RX | ELRS TX pin |
| Status LED | GP25 | GPIO | встроенный LED Pico |
| NeoPixel | GP23 | WS2812 (через PIO/PIO-WS2812-stub) | YD-RP2040 onboard |
| (резерв) | GP4/GP5 | UART1 опционально | debug, см. §3 |
| (резерв) | GP2/GP3 | PWM1 (не задействован) | — |
| (резерв) | GP10/GP11/GP14 | GPIO | резерв |

Новые `BIBA_TARGET_HAS_*` флаги:

```c
#define BIBA_TARGET_HAS_BTS7960_2CH  0   /* brushed DC драйвер снят */
#define BIBA_TARGET_HAS_BLDC_2CH     1   /* ODrive через CAN/UART */
#define BIBA_TARGET_HAS_MCP2515      1   /* SPI0 → CAN мост */
#define BIBA_TARGET_HAS_CRSF         1   /* как и раньше */
#define BIBA_TARGET_HAS_IMU          1   /* I2C IMU — пока оставлен */
#define BIBA_TARGET_HAS_SPI_SLAVE    0   /* SBC link заменён на UART1/USB-CDC */
#define BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM 0
```

`IMU` пока оставлен — он не мешает, отдаёт heading для
IMU-стабилизированного вождения. Если приоритеты поменяются —
выключается одной строкой.

---

## 2. Матрица сборки

### 2.1 Env'ы, которые добавляем в `platformio.ini`

```ini
[target_rpico_rp2040_bldc]
board = vccgnd_yd_rp2040
target_include = targets/RPICO_RP2040_BLDC
build_flags =
    -DBIBA_TARGET_RPICO_RP2040_BLDC=1
    -DBIBA_TARGET_HAS_BTS7960_2CH=0
    -DBIBA_TARGET_HAS_BLDC_2CH=1

; --- Режимы (standalone / companion / combined) -------------------------

[env:rpico_rp2040_bldc_standalone]
platform = file:///home/ros2/.platformio/platforms/rp2040
framework = arduino
board = ${target_rpico_rp2040_bldc.board}
upload_protocol = picotool
debug_tool = cmsis-dap
build_src_filter = ${rp2040_bldc_src_filter.build_src_filter}
build_flags =
    -Iinclude
    -Isrc
    -Isrc/proto
    -I${target_rpico_rp2040_bldc.target_include}
    ${target_rpico_rp2040_bldc.build_flags}
    ${mode_standalone.build_flags}

[env:rpico_rp2040_bldc_companion]
... (аналогично)

[env:rpico_rp2040_bldc_combined]
... (аналогично)
```

### 2.2 src_filter

В `platformio.ini` добавляется:

```ini
[rp2040_bldc_src_filter]
build_src_filter =
    +<*>
    -<hal/biba_hal.c>
    -<hal/biba_hal_motor.c>
    -<hal/biba_hal_motor_rp2040.c>     ; PWM нам не нужен — нет BTS7960
    -<hal/biba_hal_debug.c>
    -<main.c>
    -<poc/>
    -<drivers/bts7960.c>               ; brushed DC драйвер убран
    +<drivers/mcp2515.c>               ; новый SPI→CAN драйвер
    +<drivers/odrive_can.c>            ; парсер CANSimple
    +<drivers/can_queue.c>             ; очередь RX/TX
    +<hal/biba_hal_motor_bldc.c>       ; HAL-уровень BLDC backend
```

`mode_dispatcher.c`, `mode_standalone.c`, `mode_companion.c`
**остаются** — они теперь компилируются с `#if BIBA_TARGET_HAS_*`-гардами
вокруг вызовов BTS7960/ODrive.

### 2.3 Пример вызова

```bash
# Обычная brushed-DC сборка (как было)
pio run -e rpico_rp2040_standalone

# Новая BLDC-CAN сборка
pio run -e rpico_rp2040_bldc_standalone
```

---

## 3. Опциональный UART ASCII fallback

Research §6.8 предлагает ODrive UART ASCII @ 115200 как bench-test
канал (без MCP2515). Решение ADR: **поддерживаем в коде как опцию,
активируемую compile-time флагом `-DODRIVE_LINK=ASCII`**.

Поведение при `-DODRIVE_LINK=CAN` (default, production):

- MCP2515 driver инициализирован.
- CAN queue + odrive_can driver инициализированы.
- `biba_odrive_drive` шлёт `Set_Input_Vel` (cmd_id 0x0D) обеим ODrive.
- Heartbeat, Get_Encoder_Estimates принимаются асинхронно (RX INT).

Поведение при `-DODRIVE_LINK=ASCII` (bench-test):

- MCP2515 driver **не** инициализируется.
- На UART1 (GP4=TX, GP5=RX) поднимается PIO-UART для левого ODrive,
  на **втором PIO-UART** — для правого (оба через `pico-pio-uart`).
  В коде `biba_odrive_can.c` условно компилируется в
  `biba_odrive_ascii.c`.
- `biba_odrive_drive` шлёт ASCII-команду `v <motor> <vel>\n`.

Это **позволяет** запустить таргет на макете с одним ODrive без
MCP2515 (только три провода), что полезно при отладке питания и
проводки до установки CAN-модуля. В production остаётся CAN.
Опция отключена по умолчанию, поэтому не нагружает CI.

### Почему PIO-UART, а не второй hardware UART

У RP2040 **ровно два** аппаратных UART'а (UART0 занят CRSF, UART1 —
UART ASCII на левый ODrive). На второй ODrive альтернативы:

1. PIO-UART (наш выбор) — стабильно тянет 115200, библиотека
   `pico-pio-uart` от Camel CASE (см. ссылки в research.md §11).
   ~12 PIO-инструкций, ~32 байта RAM на канал.
2. Возврат к CAN для второго ODrive — гибрид усложняет code path
   без реальной выгоды.

Принято: PIO-UART через `pico-pio-uart`.

---

## 4. Модули, которые добавляются в `firmware/src/`

| Модуль | Назначение | Линий кода (ориентир) |
|--------|------------|-----------------------|
| `drivers/mcp2515.h/.c` | SPI0 ↔ MCP2515 register-level driver, передача TX-frame, приём RX-frame по INT, bit-modify конфигурации | ~400 |
| `drivers/can_queue.h/.c` | Lock-free очередь CAN-кадров (TX-ring, RX-ring) с ISR-safe push | ~150 |
| `drivers/odrive_can.h/.c` | Высокоуровневый ODrive API поверх can_queue: `set_axis_state`, `set_input_vel`, `set_limits`, `heartbeat_poll`, encode/decode cmd_id | ~300 |
| `hal/biba_hal_motor_bldc.c` | HAL-shim: привязывает CAN-команды к RP2040 SPI0 + MCP2515 INT | ~80 |
| `app/biba_odrive_state.c` | (опц.) кеш heartbeat/encoder последних known good, чтобы tick-fast-path не блокировал SPI | ~60 |

Совокупный объём модулей — около **1000 LoC** плюс комментарии и тесты.
Это реалистичный размер для PoC-реализации; для production-готовности
нужно ещё ~500 строк тестов + CRC-проверка CAN frame acceptance в MCP2515.

---

## 5. Точки расширения

ADR фиксирует **v1** минимальный набор. Точки, куда v2 может расти без
ломающих изменений:

1. **FreeRTOS** (см. §1.1) — замена при расширении до > 2 колёс или SD.
2. **Galvanic isolation CAN** через ISO1050 / ADM3050 — аппаратная
   правка, firmware не меняется (только bit-timing).
3. **VESC-совместимость** — отдельный cmd_id-range driver
   (`drivers/vesc_can.c`), переключение флагом `-DBIBA_DRIVER=VESC`.
   v1 прицеливаемся только на ODrive, чтобы не размывать scope.
4. **DroneCAN** (UAVCAN v0) — для других BLDC-контроллеров
   (MKS SERVO57D). Потребуется 29-bit extended ID в MCP2515 и новая
   таблица cmd_id. Это **новая** ветка, не ломающая текущую.
5. **Persistent config на flash RP2040** — параметры мотора
   (current limit, vel limit) сохраняются через `flash_safe_exec`
   для переживания перезагрузки. Сейчас — сохраняем дефолты при
   boot, конфиг перенастраивается через ODrive Tool.

---

## 6. Открытые вопросы (для следующих итераций)

1. **Watchdog timeout на стороне RP2040.** Если ODrive heart перестал
   приходить N секунд — наш fail-режим: шлём `Estop` на оба node_id
   или просто прекращаем `Set_Input_Vel` (полагаемся на ODrive-side
   watchdog). ADR не фиксирует — это политика mode_standalone,
   решается на уровне application-кода.
2. **Galvanic isolation** — модуль ODrive Pro имеет встроенный CAN
   isolation, legacy ODrive — нет. Если используется legacy и
   требуется изоляция, ставится ISO1050 + DC-DC isolator. ADR не
   обязывает: для PoC это откладывается.
3. **Persist ODrive address → node_id mapping через flash.** Сейчас
   node_id фиксируются в `target_config.h` (`{0, 1}`). Если
   используется discovery (CAN Address broadcast) — маппинг лучше
   хранить в flash, чтобы переживать перезагрузку.

Эти вопросы не блокируют имплементацию v1; они — в backlog.

---

## 7. Решение зафиксировано

| Что | Решение |
|-----|---------|
| Стек | Bare-metal Pico SDK (arduino-pico), без FreeRTOS |
| MCP2515 SPI | HW SPI0 @ 7.8125 МГц, Mode 0,0, MSB first |
| Резерв для SPI | PIO SPI через `pico_pio_spi` (если когда-то понадобится смена пинов) |
| CAN bit-rate | 250 кбит/с (default), 500 — переключается через `BIT-MODIFY CNF*` |
| CAN frame | 11-bit ID, ODrive CANSimple format (`node_id << 5 \| cmd_id`) |
| Endianness | little-endian, IEEE-754 LE |
| Discovery | CAN Address broadcast (cmd_id 0x06) один раз при boot |
| Watchdog | ODrive-side через прекращение `Set_Input_*` (100 ms типично) |
| Motor backend | `biba_odrive_*` API-совместимый с `biba_bts7960_*`, выбор через `BIBA_TARGET_HAS_*` |
| UART ASCII fallback | Опция `-DODRIVE_LINK=ASCII`, через PIO-UART на GP4/5 + второй PIO-UART |
| Переключение таргетов | `[target_rpico_rp2040_bldc]` stanza + `[env:rpico_rp2040_bldc_*]`, без Kconfig |
| Набор envs | `standalone`, `companion`, `combined` — как у текущего target |
| src_filter | Новая `[rp2040_bldc_src_filter]`: убирает `bts7960.c` и `biba_hal_motor_rp2040.c`, добавляет `mcp2515.c`/`odrive_can.c`/`can_queue.c`/`biba_hal_motor_bldc.c` |

---

## 8. Связанные документы

- `docs/mcp2515_bldc_research.md` — research (parent task)
- `docs/adr/0001-pico-bldc-target.md/diagram-components.mmd` —
  диаграмма компонентов (sibling)
- `firmware/targets/README.md` — дисциплина target-файлов
- `firmware/targets/RPICO_RP2040_BLDC/target.h` — скаффолд нового
  таргета (sibling)
- `firmware/targets/RPICO_RP2040_BLDC/target_config.h` — дефолты
  ODrive (sibling)
- `firmware/targets/RPICO_RP2040_BLDC/target.md` — описание распиновки
  и отличий от `RPICO_RP2040` (sibling)
- `firmware/platformio.ini` — добавление `[target_rpico_rp2040_bldc]`
  и трёх `[env:rpico_rp2040_bldc_*]` (sibling)

Sibling-документы ниже в `tasks`:
- `t_a3ed6b73` — реализация `drivers/mcp2515.c` + queue
- `t_83ccac50` — общий декомпозированный wbs для BLDC target
