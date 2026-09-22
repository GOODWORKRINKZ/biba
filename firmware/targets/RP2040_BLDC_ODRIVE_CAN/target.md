# Таргет: RP2040_BLDC_ODRIVE_CAN

RP2040-вариант BiBa для управления парой BLDC-приводов через ODrive
по CAN. Заменяет BTS7960 (см. соседний `RP2040_DC_BTS7960_PWM/target.md`) в
проектах, где thermal-режим щёточных модулей стал узким местом.

> **Спутник:** см. `docs/adr/0001-pico-bldc-target.md` — этот
> документ фиксирует только «что отличается в распиновке». Все
> архитектурные обоснования (почему HW SPI, а не bit-banging; почему
> один бэкенд через `BIBA_TARGET_HAS_*`, а не vtable; почему нет
> FreeRTOS) — в ADR.

## Распиновка по группам периферии

### 1. CRSF / ELRS приёмник (UART0)

| Пин | Сигнал   | Направление | Примечание                   |
|-----|----------|-------------|------------------------------|
| GP0 | CRSF_TX  | ВЫХ UART0  | К пину RX приёмника          |
| GP1 | CRSF_RX  | ВХ  UART0  | От пина TX приёмника         |

### 2. MCP2515 SPI→CAN мост (SPI0)

| Пин | Сигнал  | Направление | Примечание                            |
|-----|---------|-------------|---------------------------------------|
| GP16 | SO/MISO  | ВХ SPI0   | ← MCP2515 SO                          |
| GP17 | CS       | ВЫХ GPIO  | Чип-селект MCP2515, active LOW        |
| GP18 | SCK      | ВЫХ SPI0  | SPI clock, ~7.8125 МГц (HW SPI0)      |
| GP19 | SI/MOSI  | ВЫХ SPI0  | → MCP2515 SI                          |
| GP15 | INT      | ВХ GPIO IRQ | MCP2515 → host, open-drain (active low), on-board 10 kΩ pull-up |

Режим SPI — **Mode 0,0** (CPOL=0, CPHA=0), **MSB first**, baud
**7.8125 МГц**. Это делитель 16 от `clk_peri = 125 МГц` —
целочисленный. Ниже cap MCP2515 (10 МГц @ Vdd ≥ 4.5 В, 5 МГц @ 3.0–4.5 В).

Подробности по физическому уровню CAN — `docs/mcp2515_bldc_research.md`
§3 (питание модуля 5 В vs 3.3 В, level-shifter, терминаторы).

### 3. ODrive-pair на шине CAN

| Параметр | Значение |
|----------|----------|
| Шина | CAN 2.0B, 11-bit ID, 250 кбит/с |
| Терминатор | 120 Ω на каждом конце шины (включить DIP на одном ODrive + RTERM-перемычку на самом MCP2515-модуле, если он на конце) |
| Ожидаемое железо | 2 × ODrive Pro / S1 / Micro |
| Адресация по умолчанию | `node_id 0 → LEFT wheel`, `node_id 1 → RIGHT wheel` (override в `target_config.h` через `BIBA_BLDC_*_NODE_ID`) |
| Протокол | CANSimple: `message_id = (node_id << 5) \| cmd_id`, little-endian, IEEE-754 float для `Input_Vel` |
| Команда цикла | `Set_Input_Vel` (cmd_id 0x0D) на каждый ODrive @ 50 Гц |

Полная таблица команд — `docs/mcp2515_bldc_research.md` §6.5.

### 4. IMU (I2C0) — без изменений относительно RP2040_DC_BTS7960_PWM

| Пин   | Сигнал   | Направление | Примечание               |
|-------|----------|-------------|--------------------------|
| GP20  | I2C0_SDA | I/O I2C     | IMU + ADS1115 + AHT30    |
| GP21  | I2C0_SCL | ВЫХ I2C    |                          |
| GP22  | IMU_INT1 | ВХ GPIO    |                          |

### 5. Статус и RGB LED

| Пин   | Сигнал | Примечание                          |
|-------|--------|-------------------------------------|
| GP25  | LED    | Onboard LED Pico, active high       |
| GP23  | WS2812 | YD-RP2040 NeoPixel                  |

### 6. Свободные пины (резерв)

GP2 / GP3 / GP6 / GP7 / GP8 / GP9 / GP10 / GP11 / GP12 / GP13 / GP14
— свободны. Могут быть использованы для:

- второго MCP2515 (если когда-то понадобится отдельная CAN-сеть),
- GPIO общего назначения,
- PIO UART (для второго ODrive в bench-test ASCII-режиме).

### 7. Аналоговые входы

Все четыре канала RP2040 ADC (GP26 / GP27 / GP28 / GP29) на этом
таргете **не задействованы** — вся информация о токах/напряжениях
приходит через CAN (`Get_Iq`, `Get_Bus_Voltage_Current`,
`Get_Temperature`). Если в будущем понадобится мониторинг внешнего
питания (Rail 12V, NTC на драйвере) — раскомментировать каналы в
`target.h` и включить в `BIBA_ADC_CHANNEL_SEQ`.

## Что убрано по сравнению с `RP2040_DC_BTS7960_PWM`

- **BTS7960.** Все 8 пинов `GP2..GP9` теперь свободны.
  `BIBA_TARGET_HAS_BTS7960_2CH = 0`. Driver `drivers/bts7960.c`
  исключён из build по `[rp2040_bldc_odrive_can_src_filter]`.
- **Native ADC scan** для IS_LEFT / IS_RIGHT / IBAT / VBAT.
  Вместо них ODrive-side `Get_Iq` / `Get_Temperature`.
  `BIBA_ADC_SCAN_LEN = 0`. Макросы IS/IBAT/VBAT в
  `target_config.h` занулены, чтобы любой код, ссылающийся на них,
  коротко завершал логическую ветку.

## Что добавлено по сравнению с `RP2040_DC_BTS7960_PWM`

- **MCP2515 SPI→CAN мост** (GP16/17/18/19/15).
  С ним связаны новые бинари: `drivers/mcp2515.c`, `drivers/can_queue.c`,
  `drivers/odrive_can.c`, `hal/biba_hal_motor_bldc.c`. Все детали —
  в ADR-0001.

## Build

```bash
# BLDC, standalone
pio run -e rp2040_bldc_odrive_can_standalone

# BLDC, companion (SBC via USB-CDC)
pio run -e rp2040_bldc_odrive_can_companion

# BLDC, combined (режим выбирается MODE_SEL пинe / flag)
pio run -e rp2040_bldc_odrive_can_combined
```

## Переключение между RP2040_DC_BTS7960_PWM и RP2040_BLDC_ODRIVE_CAN

Это **разные таргеты**, не режимы. Чтобы переключиться, вызывающий
просто меняет имя env:

```bash
pio run -e rp2040_dc_bts7960_pwm_standalone          # ← brushed DC (старое поведение)
pio run -e rp2040_bldc_odrive_can_standalone    # ← BLDC через ODrive (новое)
```

Флаги `BIBA_TARGET_HAS_BTS7960_2CH = 0` / `BIBA_TARGET_HAS_BLDC_2CH = 1`
выставляются в `[target_rp2040_bldc_odrive_can]` stanza; mode code в
`src/modes/*.c` гардирует вызовы backend'а через эти флаги
(подробности — ADR-0001 §1.5).

> **Никаких Kconfig / menuconfig.** Переключение — это выбор env в
> PlatformIO, как и для всех остальных таргетов проекта (Blue Pill,
> BIBA_F103_REV_A). Это согласовано с существующей дисциплиной
> (`firmware/targets/README.md`).

## ASCII-линк вместо CAN

Те же ODrive можно вести по ODrive ASCII на UART1 (GP4/GP5), без
MCP2515 вообще. Это **отдельный таргет** `RP2040_BLDC_ODRIVE_UART`, а
не флаг сборки: по принятому стандарту имён тип линка входит в имя
таргета, а распиновка у двух вариантов действительно разная
(ADR-0002).

```bash
pio run -e rp2040_bldc_odrive_uart_standalone
```

Сейчас в production используется именно он: CANSimple-стек в прошивке
ODrive 0.5.6 тихо залипает на холостом ходу. Детали —
`../RP2040_BLDC_ODRIVE_UART/target.md` и
`docs/mcp2515_bldc_research.md` §6.8.

## Проверка после прошивки

1. **CAN discover**: ODrive должны ответить на broadcast `Address(0x06)` —
   загорается status-LED на каждом ODrive (если включена адресация).
2. **Telemetry**: GPIO 15 должен "ткнуться" вниз при наличии RX pending
   в MCP2515; наш ISR `biba_mcp2515_rx_isr` зачитывает кадр.
3. **Drive**: CRSF throttle → ODrive-1 крутит левое колесо вперёд,
   CRSF throttle→ ODrive-2 крутит правое.
4. **Heartbeat**: при пропадании CAN от ODrive firmware
   перестаёт слать `Set_Input_Vel` после
   `BIBA_ODRIVE_HEARTBEAT_TIMEOUT_MS` (250 мс по умолчанию);
   ODrive сам disarm'нется через 100 мс по своему watchdog.

## References

- `../RP2040_DC_BTS7960_PWM/target.md` — старый (BTS7960) таргет, для сравнения
- `../RP2040_BLDC_ODRIVE_UART/target.md` — те же ODrive по ASCII-линку
- `../RP2040_BLDC_VESC_CAN/target.md` — VESC на том же MCP2515-мосту
- `docs/adr/0002-target-naming-and-vesc.md` — ADR: стандарт имён + VESC
- `docs/mcp2515_bldc_research.md` — full research with citations
- `docs/adr/0001-pico-bldc-target.md` — ADR, обоснование решений
- `docs/adr/diagram-components.mmd` — диаграмма компонентов
