# Таргет `RPICO_RP2040_BLDC` — BLDC/ODrive через CAN

Этот документ — пошаговая инструкция по запуску таргета «с нуля»: что
купить, как спаять, как собрать, как прошить, как проверить, что всё
работает. Архитектурные обоснования выбора железа и протокола лежат в
`docs/adr/0001-pico-bldc-target.md`, фундаментальное сравнение пинов с
соседним таргетом — в [`target.md`](./target.md). Здесь — только «как
включить и убедиться, что крутится».

> Таргет `RPICO_RP2040_BLDC` — это альтернативная сборка той же
> платы **Raspberry Pi Pico / YD-RP2040**, на которой вместо двух
> BTS7960 (щёточный DC) живёт MCP2515+TJA1050 (SPI↔CAN мост) и пара
> ODrive на шине. Переключение — выбором `env` в PlatformIO (см.
> [`targets/README.md`](../README.md)), никаких #ifdef в `src/`.

## 1. Что нужно купить

| Кол-во | Что                                | Зачем                                       | Заметки |
|--------|------------------------------------|---------------------------------------------|---------|
| 1      | Raspberry Pi Pico **или** YD-RP2040| MCU: RP2040, 125 МГц, 264 КБ SRAM, 2 МБ Flash | YD-RP2040 удобнее — onboard WS2812 + USB-C |
| 1      | Модуль MCP2515 + TJA1050           | SPI↔CAN, 5 В phy                            | Один из типовых модулей с кварцем 8 МГц |
| 2      | ODrive Pro / S1 / Micro            | BLDC-контроллер, CAN 2.0B                   | Любой вариант с CAN-разъёмом |
| 1      | CRSF/ELRS-совместимый приёмник      | Радиоканал RC (UART0)                        | TX на GP0, RX на GP1 |
| 1      | DC-DC 5 В (≥ 600 мА)               | Питание MCP2515-модуля от Rail 12 В         | Если модуль принимает только 5 В |
| 2      | BLDC-мотор + энкодер              | Нагрузка на каждый ODrive                    | Поддерживается любая распиновка ODrive |
| 1      | USB-C кабель (data, не charge-only) | Прошивка через BOOTSEL + USB-CDC лог         | |

Расходники: dupont-провода, терминаторы 120 Ω (обычно уже запаяны на
концах шины и переключаются на одном из ODrive DIP-переключателем),
блок питания 12–24 В под ODrive.

## 2. Схема подключения

ASCII-схема (только сигнальные линии; питание показано там, где важно).

```
                          ┌──────────────┐
   CRSF TX ─► GP0  UART0_TX┤              ├ GND
   CRSF RX ◄─ GP1  UART0_RX│              ├ GND
                          │              ├ VIN
                          │              ├ GND
                          │              ├ GP23 WS2812 (YD-RP2040)
       GP14 ─[резерв]─────┤              ├ GP22 IMU_INT1
       GP13 ─[резерв]─────┤              ├ GP21 I2C0_SCL
       GP12 ─[резерв]─────┤              ├ GP20 I2C0_SDA
        GND ──────────────┤              ├ 3V3(OUT)  ──┐ питание Pico
                          │   RP2040     ├ VREF         │
       GP9 ─[резерв]──────┤              ├ GP28 ADC2     │
       GP8 ─[резерв]──────┤              ├ GP27 ADC1     │
       GP7 ─[резерв]──────┤              ├ GP26 ADC0     │
       GP6 ─[резерв]──────┤              ├ GP29 ADC3     │
       GP5 ─[резерв]──────┤              ├ GP15 INT ◄─── MCP2515 INT (active LOW, 10k pull-up на модуле)
       GP4 ─[резерв]──────┤              ├ GP14 [резерв] │
       GP3 ─[резерв]──────┤              ├              │
       GP2 ─[резерв]──────┤              ├ GP19 MOSI ──► MCP2515 SI
                          │              ├ GP18 SCK ───► MCP2515 SCK
                          │              ├ GP17 CS ────► MCP2515 CS  (active LOW)
                          └──────USB─────┘ GP16 MISO ◄── MCP2515 SO
                                                                  │
                                            (по USB: BOOTSEL, USB-CDC лог)
                                       (по USB: питание 5 В)
```

### 2.1 MCP2515 ↔ Pico (SPI0)

| MCP2515 пин | RP2040 пин | Сигнал        | Примечание                       |
|-------------|-----------|---------------|----------------------------------|
| VCC         | VBUS (5В) | Питание 5 В   | Если модуль 5 В-толерантный; иначе через DC-DC 5 В и **проверить** VIO↔3V3 совместимость |
| GND         | GND       | Земля         | Общая с ODrive-шиной             |
| CS          | GP17      | Чип-селект    | GPIO OUT, active LOW             |
| SCK         | GP18      | SPI0 SCK      | HW SPI0, Mode 0, MSB first, 7.8125 МГц |
| SI (MOSI)   | GP19      | SPI0 MOSI     |                                  |
| SO (MISO)   | GP16      | SPI0 MISO     |                                  |
| INT         | GP15      | IRQ (вход)    | MCP2515 INT, open-drain, на модуле уже подтянут к Vdd через 10 кОм |

Если модуль рассчитан на 3.3 В — подавайте `VCC` от `3V3(OUT)`, без
DC-DC, а землю объедините с общей.

### 2.2 MCP2515 ↔ ODrive-шина (CAN)

| MCP2515 | ODrive-CAN (оба контроллера параллельно) |
|---------|------------------------------------------|
| CANH    | CANH                                     |
| CANL    | CANL                                     |
| GND     | GND (общая земля с RP2040)               |

```
   MCP2515/TJA1050                 ODrive #0 (LEFT, node_id=0)
   ┌──────────┐                    ┌────────────┐
   │ CANH ────┼────────────────────┼ CANH       │
   │ CANL ────┼────────────────────┼ CANL       │
   │ GND  ────┼────────────────────┼ GND        │
   └──────────┘                    └────────────┘
       │                               │
       │ 120 Ω                        │ 120 Ω   ← терминаторы на каждом конце шины.
       │                               │          на одном ODrive — DIP-переключателем,
       └───────────────────────────────┘          на MCP2515-модуле — RTERM-перемычкой
                                                  (если модуль на конце)
                  ODrive #1 (RIGHT, node_id=1)
                  ┌────────────┐
                  │ CANH       │
                  │ CANL       │
                  │ GND        │
                  └────────────┘
```

### 2.3 CRSF / ELRS (UART0)

| Pico | Приёмник ELRS/CRSF |
|------|---------------------|
| GP0 (TX) | RX приёмника |
| GP1 (RX) | TX приёмника |
| GND | GND приёмника |
| VBUS/5V | +5V (или запитать от BEC'а ESC) |

### 2.4 ODrive-set_Limits на старте (важно для первого запуска)

Адреса узлов по умолчанию (в `target_config.h`):

- `BIBA_ODRIVE_LEFT_NODE_ID  = 0`
- `BIBA_ODRIVE_RIGHT_NODE_ID = 1`

Если платы уже настроены на другие ID — поменяйте обе константы
**до** первой прошивки либо перенастройте ODrive штатно (`<od> h`
по USB):

```
odrv0.axis0.motor.config.can_node_id = 0   # left
odrv1.axis0.motor.config.can_node_id = 1   # right
```

## 3. Сборка

Сборка делается через **PlatformIO** (CI-путь, основной) или **вручную
через CMake/Ninja/picotool** (для IDE / отладки).

### 3.1 PlatformIO — обычный путь

Из корня репозитория:

```bash
# PoC: только SPI↔MCP2515 self-test, без ODrive.
# Прошить первым делом на новой плате — проверяет SPI и питание.
pio run -e rpico_rp2040_bldc_can_loopback_poc
pio run -e rpico_rp2040_bldc_can_loopback_poc --target upload

# Продакшен-сборки:
pio run -e rpico_rp2040_bldc_standalone   # автономная логика (без SBC)
pio run -e rpico_rp2040_bldc_companion    # работает в паре с SBC по USB-CDC
pio run -e rpico_rp2040_bldc_combined     # режим выбирается MODE_SEL джампером

# Проверить, что UF2 собран, без прошивки:
pio run -e rpico_rp2040_bldc_can_loopback_poc --target size
```

`upload_protocol = picotool`, поэтому PlatformIO сам позовёт `picotool`.
Если он не в PATH — поставьте (`brew install picotool`,
`apt install picotool` или соберите из
[pico-sdk-tools](https://github.com/raspberrypi/picotool)).

### 3.2 CMake + Ninja + picotool — ручной путь (опционально)

Удобно для CLion / VS Code с CMake Tools. Готовый
`CMakeLists.txt` лежит прямо в таргете: [`CMakeLists.txt`](./CMakeLists.txt).

```bash
cd firmware/targets/RPICO_RP2040_BLDC
mkdir build && cd build
cmake -G Ninja -DPICO_SDK_PATH=/path/to/pico-sdk ..
ninja
picotool load -p /dev/ttyACM0 firmware.uf2
```

Требования к host'у: Pico SDK 1.5+ (на момент написания — 2.x),
`arm-none-eabi-gcc`, `picotool`, согласование `pico_enable_stdio_usb()`
(см. шапку `CMakeLists.txt`). Этот путь **не используется CI** — CI
гоняет только `pio run`.

## 4. Прошивка

Есть два пути; второй — запасной, если PlatformIO/picotool недоступны.

### 4.1 Автоматически (PlatformIO + picotool)

1. Зажать кнопку **BOOTSEL** на Pico.
2. Подключить USB-C к хосту.
3. Отпустить BOOTSEL — на хосте появится mass-storage `RPI-RP2`.
4. `pio run -e <env> --target upload` — PlatformIO сам переключит
   плату в нормальный режим и зашлёт UF2.

Одновременно с этим USB-CDC открывается как `/dev/ttyACM0` (Linux) /
`COMx` (Windows) — туда идёт `printf`-лог.

### 4.2 Ручной перетаскиванием UF2

1. Шаг 1–3 выше.
2. Из артефактов PlatformIO:
   ```bash
   ls .pio/build/rpico_rp2040_bldc_can_loopback_poc/firmware.uf2
   ```
3. `cp .pio/build/<env>/firmware.uf2 /media/$USER/RPI-RP2/`
4. Pico сама ребутнётся и начнёт исполнять код.

### 4.3 Что увидеть в логе (PoC, без ODrive)

После `can_loopback_poc` с подключённой шиной (но без ответчика) в
USB-CDC @ 115200 8N1 появляется:

```
[biba] RPICO_RP2040_BLDC CAN-loopback PoC
[biba] build: Jul 20 2026 17:12:34
[biba] target: RPICO_RP2040_BLDC @ 125 MHz, MCP2515 SPI @ 7812500 Hz
[biba] MCP2515 up @ 250000 bps
[biba] PoC running: TX Heartbeat @ 5 Hz, Set_Input_Vel @ 1 Hz
[biba] status t=... tx=... rx=0 rx_drop=0 q_rx_push=0 q_rx_pop=0 ...
```

`rx=0` без второго ODrive — это нормально. Если `MCP2515 init FAILED`
— проверяйте SPI-провода и питание модуля.

## 5. Конфигурация

В этом таргете **нет Kconfig / menuconfig** — это сознательное
решение, зафиксированное в ADR-0001 и согласованное с дисциплиной
[`targets/README.md`](../README.md). Переключение — выбор `env` в
PlatformIO, конфигурация — двумя header'ами рядом с этим README:

```
targets/RPICO_RP2040_BLDC/
├── target.h            # распиновка + capability-флаги BIBA_TARGET_HAS_*
├── target_config.h     # калибровки и лимиты
└── README.md           # ← этот файл
```

Допустимые ручки (все — через `#define`):

**Распиновка — `target.h`.** Изменять только если вы переносите
прошивку на другой клон Pico или распиновка именно вашей ревизии
YD-RP2040 конфликтует.

**Лимиты / адреса — `target_config.h`.** Вот что типично правится при
первом запуске:

| Макрос                            | Что меняет                                            | Дефолт          |
|-----------------------------------|--------------------------------------------------------|-----------------|
| `BIBA_ODRIVE_LEFT_NODE_ID`        | CAN-ID левого ODrive                                   | `0`             |
| `BIBA_ODRIVE_RIGHT_NODE_ID`       | CAN-ID правого ODrive                                  | `1`             |
| `BIBA_ODRIVE_LEFT_DIR`            | Полярность колеса: `1.0f` или `-1.0f`                  | `1.0f`          |
| `BIBA_ODRIVE_RIGHT_DIR`           | Полярность колеса                                      | `1.0f`          |
| `BIBA_ODRIVE_LEFT_MAX_VEL_REV_S`  | Макс. скорость левого при `duty = ±1.0` (rev/s)        | `6.0f` (~360 RPM на колесе) |
| `BIBA_ODRIVE_RIGHT_MAX_VEL_REV_S` | Макс. скорость правого                                | `6.0f`          |
| `BIBA_ODRIVE_MAX_CURRENT_A`       | Лимит тока, едет в ODrive через `Set_Limits`           | `30.0f`         |
| `BIBA_ODRIVE_MAX_VEL_LIMIT_REV_S` | Жёсткий ceiling, отправляется через `Set_Limits`       | `10.0f`         |
| `BIBA_CAN_BITRATE_BPS`            | Битрейт CAN-шины                                      | `250000u`       |
| `BIBA_ODRIVE_HEARTBEAT_TIMEOUT_MS`| Через сколько ms без Heartbeat'а прекращаем слать `Set_Input_Vel` | `250`           |
| `BIBA_ODRIVE_SETPOINT_RATE_HZ`    | Частота `Set_Input_Vel`                                | `50`            |
| `BIBA_SYS_CLOCK_HZ`               | Тактовая RP2040 (менять не надо)                      | `125000000u`    |

Capability-флаги в `target.h` (менять, только если понимаете
последствия):

| Макрос                                  | Значение | Что значит                              |
|-----------------------------------------|----------|-----------------------------------------|
| `BIBA_TARGET_HAS_BTS7960_2CH`           | `0`      | BTS7960 не распаян, brushed backend выключен |
| `BIBA_TARGET_HAS_BLDC_2CH`              | `1`      | BLDC-backend включён                    |
| `BIBA_TARGET_HAS_MCP2515`               | `1`      | SPI↔CAN-мост есть                       |
| `BIBA_TARGET_HAS_CRSF`                  | `1`      | CRSF/ELRS на UART0                      |
| `BIBA_TARGET_HAS_IMU`                   | `1`      | I2C0 IMU (GP20/21)                      |
| `BIBA_TARGET_HAS_SPI_SLAVE`             | `0`      | SBC по USB-CDC, не по SPI                |
| `BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM` | `0`      | ШИМ не разведён (не используется)       |

## 6. Проверка после прошивки

Пошагово, минимально-достаточно чтобы понять «живо/не живо»:

1. **Boot-логи.** Откройте USB-CDC терминал на 115200 8N1. Должны
   увидеть строки `[biba] RPICO_RP2040_BLDC …` и `[biba] MCP2515 up
   @ 250000 bps`. Если `MCP2515 init FAILED (status=-N)` — нет связи
   по SPI (проверьте провода MISO/SCK/MOSI/CS и питание модуля).

2. **CAN discover.** Подайте питание на ODrive (12–24 В), дождитесь
   их boot-up. При физической шине с двумя ответчиками в логе
   должны появиться RX-кадры от ODrive:

   ```
   [can] RX id=0x001 dlc=7 data= 08 00 00 00 00 00 00 00  ← heartbeat node 0
   [can] RX id=0x021 dlc=7 data= 08 00 00 00 00 00 00 00  ← heartbeat node 1
   ```

   Heartbeat-формат: dlc=7, data[0] = axis state (0x08 = closed loop).

3. **Drive.** Включите передатчик, газ в нейтрали — статус LED
   (GP25) должен моргать/гореть постоянно (означает «heartbeat
   идёт»), RGB-LED (GP23) — режим idle. Дайте ~10 % газа: левый
   ODrive должен крутить левое колесо вперёд, правый — правое.
   Если одно колесо идёт в обратную сторону — переверните
   соответствующий `BIBA_ODRIVE_*_DIR` в `target_config.h`.

4. **Failsafe.** Выключите питание ODrive (но не Pico). В течение
   `BIBA_ODRIVE_HEARTBEAT_TIMEOUT_MS` (250 мс по умолчанию)
   firmware перестанет слать `Set_Input_Vel`; ODrive сам disarm'нется
   по своему watchdog (100 мс). Лог покажет
   `biba_odrive_node_alive(0) == false`.

## 7. Минимальный пример обмена

Полный рабочий пример лежит в
[`../../src/poc/can_loopback_poc.cpp`](../../src/poc/can_loopback_poc.cpp).
Здесь — сжатый фрагмент «как отправить Set_Input_Vel и как
прочитать Heartbeat» из этого PoC'а — для C/C++, ровно как в этом
проекте:

```c
#include "drivers/mcp2515.h"
#include "drivers/odrive_can.h"

/* Формирование CAN-ID по CANSimple: (node_id << 5) | cmd_id,
 * 11 бит, big-endian bit-fields внутри 32-битного поля id. */
static inline uint32_t can_id(uint8_t node_id, uint8_t cmd_id) {
    return ((uint32_t)(node_id & 0x3Fu) << 5u) | (uint32_t)(cmd_id & 0x1Fu);
}

static void pack_f32_le(uint8_t *dst, float v) {
    union { float f; uint32_t u; } x = { .f = v };
    for (int i = 0; i < 4; ++i) dst[i] = (uint8_t)((x.u >> (8u * i)) & 0xFFu);
}

/* 1) Init — один раз, в setup(). */
biba_mcp2515_status_t st = biba_mcp2515_init();   /* 250 kbps, 87.5 % sample point */
biba_can_queue_rx_init();
biba_can_queue_tx_init();
biba_odrive_can_init();  /* отправит Set_Axis_State=CLOSED_LOOP + Set_Limits */

/* 2) Set_Input_Vel: 8 байт, [0..3] = velocity float LE, [4..7] = torque_ff float LE. */
static void send_set_input_vel(uint8_t node_id, float vel_rev_s, float torque_ff_nm) {
    uint8_t payload[8];
    pack_f32_le(&payload[0], vel_rev_s);
    pack_f32_le(&payload[4], torque_ff_nm);
    biba_can_frame_t f = {
        .id  = can_id(node_id, OD_CMD_SET_INPUT_VEL),  /* 0x0D */
        .dlc = 8,
    };
    memcpy(f.data, payload, sizeof(payload));
    (void)biba_mcp2515_tx(&f);
}

/* 3) Главный цикл (50 Гц): */
void loop_50hz(void) {
    float throttle = 0.0f;  /* из CRSF: [-1.0, +1.0] */
    /* duty → velocity: умножаем на BIBA_ODRIVE_*_MAX_VEL_REV_S из target_config.h */
    send_set_input_vel(BIBA_ODRIVE_LEFT_NODE_ID,
                       throttle * BIBA_ODRIVE_LEFT_MAX_VEL_REV_S * BIBA_ODRIVE_LEFT_DIR,
                       0.0f /* torque_ff */);
    send_set_input_vel(BIBA_ODRIVE_RIGHT_NODE_ID,
                       throttle * BIBA_ODRIVE_RIGHT_MAX_VEL_REV_S * BIBA_ODRIVE_RIGHT_DIR,
                       0.0f);

    /* 4) Дренаж RX: декодирует Heartbeat, Get_Iq, Get_Bus_Voltage_Current и т. д. */
    biba_odrive_can_tick_50hz();
}
```

Если на шине есть второй ODrive, в RX-очереди будут появляться
Heartbeat'ы:

```
id=0x001 dlc=7 data= 08 00 00 00 00 00 00
  │  │    │    └─── [0] axis state (0x08 = CLOSED_LOOP_CONTROL)
  │  │    └─────── data length
  │  └──────────── 0x001 = (node_id 0 << 5) | cmd_id 0x01 (HEARTBEAT)
  └─────────────── CAN ID
```

Узел жив, если `biba_odrive_node_alive(node_id) == true`. Возвращает
`false` через `BIBA_ODRIVE_HEARTBEAT_TIMEOUT_MS` без кадров.

## 8. Решение типовых проблем

| Симптом                                             | Скорее всего                                              |
|-----------------------------------------------------|-----------------------------------------------------------|
| `MCP2515 init FAILED (status=-1)` `BIBA_MCP2515_ERR_SPI`    | SPI peripheral не поднялся — кварц 8 МГц не идёт, пропало питание модуля, либо GP16/18/19 не заведены как SPI0 |
| `MCP2515 init FAILED (status=-2)` `BIBA_MCP2515_ERR_RESET`  | RESET instruction не отвечает — CS не дёргается (проверьте GP17, уровень на нём HIGH в покое), либо MISO/MOSI перепутаны |
| `MCP2515 init FAILED (status=-3)` `BIBA_MCP2515_ERR_CONFIG` | CNF1/CNF2/CNF3 не принимаются — чип уже в Normal, либо lock-бит не сброшен после warm-reset (выключите-включите питание MCP2515) |
| `rx=0 rx_drop=N` при живых ODrive                   | Терминаторы (120 Ω на обоих концах), земля общая           |
| Один мотор идёт в обратную сторону                  | Поменяйте `BIBA_ODRIVE_{LEFT,RIGHT}_DIR` в `target_config.h` |
| Моторы дёргаются                                    | Лимиты `BIBA_ODRIVE_MAX_CURRENT_A` слишком мягкие / питание проседает |
| Heartbeat'ы не приходят, ошибки декодера растут      | Битрейт не совпадает (`BIBA_CAN_BITRATE_BPS` vs `odrvN.can.config.bitrate`) |
| PoC не печатает ничего в CDC                        | USB-кабель без data; либо 300 ms ещё не прошли (USB-CDC enum) |

## 9. Куда смотреть дальше

- [`target.md`](./target.md) — детальная распиновка по группам
  периферии и «что убрано по сравнению с RPICO_RP2040».
- [`../../src/poc/can_loopback_poc.cpp`](../../src/poc/can_loopback_poc.cpp) —
  самый короткий путь «увидеть байты в шине» без ODrive.
- [`../../../docs/adr/0001-pico-bldc-target.md`](../../../docs/adr/0001-pico-bldc-target.md) —
  ADR с обоснованием выбора SPI/HW/MCP2515 и почему нет Kconfig.
- [`../../../docs/mcp2515_bldc_research.md`](../../../docs/mcp2515_bldc_research.md) —
  полный research: питание модуля, терминаторы, ODrive CANSimple,
  полная таблица cmd_id.
- [`../RPICO_RP2040/target.md`](../RPICO_RP2040/target.md) — если нужно
  сравнить со щёточным вариантом на той же плате.
