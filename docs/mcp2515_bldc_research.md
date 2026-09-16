# MCP2515 + BLDC контроллер по SPI/CAN — research

> **Статус:** исследование под новый firmware-таргет `RPICO_RP2040_BLDC` (ветка для работы с BLDC-моторами через MCP2515 → CAN).
> **Назначение:** вводная база для архитектурного ADR и последующей реализации SPI-драйвера MCP2515, очереди CAN-сообщений, парсера BLDC-протокола.
> **Аудитория:** разработчики прошивки, схемотехник (вычитка wiring-части).

## 0. TL;DR

1. **Подключение к Pico** — модуль MCP2515+TJA1050 подключается к SPI0 RP2040: SCK=GP18, MOSI=GP19, MISO=GP16, CS=GP17, INT=GP15. На Pico всё 3.3 В, поэтому питать модуль **только от 5 В через BEC**, а SPI/INT линии соединить **через резистивный делитель 2 кОм/1 кОм** на стороне модуля (по 5 В → 3.3 В), либо взять готовый модуль с on-board level-shifter (см. §3). GP22 в новом target остаётся свободным (в существующем `RPICO_RP2040` он занят IMU_INT1).
2. **SPI mode 0,0** (CPOL=0, CPHA=0), **максимум 10 МГц** по datasheet MCP2515. На RP2040 берём `spi_clk ≈ 7.8 МГц` (делитель 16 от 125 МГц clk_peri) — целое число делителя, ниже 10 МГц cap модуля, совместимо с кварцем 8 МГц.
3. **Топология шины CAN** — два ODrive (left/right wheel) на одной витой паре, 120 Ω терминация на каждом конце. Включаем перемычку терминатора только на **последнем** физическом узле (на одном из ODrive — у ODrive Pro/S1 есть DIP "CAN 120R"; на самом MCP2515-модуле перемычка `RTERM`).
4. **Целевой BLDC-контроллер — ODrive (CANSimple)**. У пользователя уже есть пара ODrive, протокол документирован, есть дисcovery/broadcast (важно для первого включения), watchdog, и цикл `Set_Input_Vel` 8 байт укладывается в одну CAN-frame. См. §5 и §6.
5. **Альтернативный канал — ODrive UART ASCII** (см. §6.8). Тот же ODrive, тот же watchdog, но текстовый протокол по UART-A @ 115200 8N1, 3.3 В логика (RX 5V-tolerant — можно напрямую с RP2040 без level-shifter). Подходит для bench-test / debug / одноплатного PoC без MCP2515. **Не заменяет CAN** в production, но даёт вторую точку опоры при отладке.
6. **Длина проводов SPI ≤ 100 мм** при 10 МГц на макетной плате; CAN — витая пара, ≤ 5 м на 500 кбит/с (типичная скорость ODrive по умолчанию), ≤ 40 м на 125 кбит/с. UART @ 115200 — до 3 м.

---

## 1. Цель и мотивация

Текущая ветка `rp2040-port` управляет щёточными DC-моторами через BTS7960 (см. `firmware/targets/RPICO_RP2040/target.md` и `docs/wiring.md`). У BTS7960 зафиксирован тепловой режим — дешёвые модули без радиатора перегреваются после ~20-30 мин интенсивной езды (см. `.planning/PROJECT.md` → Context, и Phase 4 UAT).

**Идея:** добавить отдельный firmware-таргет, который вместо BTS7960 управляет парой BLDC-моторов через готовые BLDC-контроллеры, доступные по CAN. На Pico добавляется SPI → CAN мост на MCP2515+TJA1050, а силовая часть выносится в отдельный модуль (ODrive / VESC / …), у которого уже есть proper MOSFET-мост, токовые шунты, термодатчики и EMC-защита.

Преимущества по сравнению с текущим BTS7960:

- промышленный силовой каскад, рассчитан на непрерывную работу;
- встроенные current sense, temperature sense, brake resistor control;
- CAN — дифференциальная шина с приоритезацией сообщений и CRC;
- разделение низковольтной и силовой земли через изолированный трансивер (опционально).

Издержки:

- нужен отдельный модуль MCP2515;
- тайм-критичный код смещается: CRSF-кадр (ELRS) идёт всё ещё на UART0, но команда теперь идёт через SPI→MCP2515→CAN→ODrive, появляется дополнительный latency budget (типично ≤ 5 мс round-trip при 500 кбит/с).

---

## 2. MCP2515 — datasheet essentials

Источник: [MCP2515 Stand-Alone CAN Controller with SPI — DS20001801J (Microchip)](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP2515-Stand-Alone-CAN-Controller-with-SPI-20001801J.pdf), 84 страницы, ревизия 2019 г.

### 2.1 Ключевые характеристики

| Параметр | Значение | Комментарий |
|----------|----------|-------------|
| Поддержка CAN | CAN 2.0B active, до 1 Мбит/с | Совместим с CAN 2.0A (11-bit ID) и 2.0B (29-bit ID) |
| SPI clock (max) | **10 МГц** | При Vdd ≥ 4.5 В; при 3.0–4.5 В — до 5 МГц (см. errata DS80000267) |
| SPI mode | **Mode 0,0** (CPOL=0, CPHA=0) | См. §2.2 |
| Vdd | 2.7–5.5 В | Модуль питаем от 5 В |
| Логические уровни SPI | Vdd-relative | **При Vdd=5 В — логика 5 В** (см. §3) |
| TX буферы | 3 с приоритезацией | — |
| RX буферы | 2 | — |
| Acceptance filters / masks | 6 / 2 (29-bit) | — |
| INT pin | open-drain, active LOW | Pull-up на Vdd модуля |
| Тактирование | external crystal 8 МГц или 16 МГц | На типовых модулях — 8 МГц |

### 2.2 SPI mode

Из datasheet, раздел *Serial Peripheral Interface (SPI)*:

- **CPOL=0** — SCLK idle LOW.
- **CPHA=0** — data sampled on the **rising edge** of SCLK, data changed on the falling edge.
- CS (chip select) — active LOW, должен идти LOW на всю транзакцию.
- Скорость — максимум 10 МГц при Vdd ≥ 4.5 В, 5 МГц при 3.0 ≤ Vdd < 4.5 В (см. errata sheet). Наш модуль питается от 5 В, поэтому 10 МГц доступен.

Для RP2040 это означает:

- `spi_set_slave(SPI_PERIPHERAL, &spi_cfg)` с `cpol = SPI_CPOL_0`, `cpha = SPI_CPHA_0`.
- В pico-sdk это даёт `SPI_CPOL_0 | SPI_CPHA_0` в `spi.cpol/cpha`.
- В arduino-mbed это будет `SPI.setDataMode(SPI_MODE0)` (mbed-style HAL).

### 2.3 SPI frame format

MCP2515 ожидает один управляющий байт (instruction byte), затем 0+ байт данных. Транзакция завершается подъёмом CS.

| Instruction | Формат |
|-------------|--------|
| RESET | `0xC0` |
| READ | `0x03` + addr[7:0] + N data bytes |
| WRITE | `0x02` + addr[7:0] + N data bytes |
| READ RX buffer | `0x90..0x9D` |
| LOAD TX buffer | `0x40..0x4D` |
| RTS (request-to-send) | `0x80..0x82` |
| READ STATUS | `0xA0` |
| BIT-MODIFY | `0x05` + addr + mask + data |

`RX_STATUS` / `BIT-MODIFY` / `RTS` — это single-byte операции, без дополнительной фазы данных.

### 2.4 INT pin

- Active LOW, open-drain, asserted когда в одном из RX-буферов появилось валидное сообщение (прошедшее фильтры), либо по ошибке.
- Host обрабатывает INT в ISR, читает RX buffer, очищает флаг прерывания через `BIT-MODIFY CANINTF`.
- На стороне модуля INT уже подтянут к Vdd через on-board резистор (часто 10 кОм); снаружи дублировать не нужно.

---

## 3. Типовой модуль MCP2515+TJA1050 — pinout, джамперы, питание

Источники: [Last Minute Engineers — MCP2515 tutorial](https://lastminuteengineers.com/mcp2515-can-module-arduino-tutorial/), [ComponentIndex MCP2515 page](https://componentindex.net/components/mcp2515/), [ShillehTek MCP2515 manual](https://shillehtek.com/blogs/shillehtek-product-manuals/mcp2515-can-bus-module-tja1050-receiver-spi-manual), [yasir-shahzad/MCP2515-CAN-Bus-Module schematics](https://github.com/yasir-shahzad/MCP2515-CAN-Bus-Module).

### 3.1 Схема модуля (ASCII)

```
                  ┌──────────────────────────────┐
                  │                              │
   SPI side  ◄───►│  VCC  GND  INT  SCK  SI  SO  CS│   ◄─── input header (6-pin)
                  │                              │
                  │       ┌──────────┐           │
                  │       │ MCP2515  │           │
                  │       │ (CAN ctrl)│          │
                  │       └────┬─────┘           │
                  │            │TXCAN/RXCAN      │
                  │       ┌────┴─────┐           │
                  │       │ TJA1050  │           │
                  │       │(transcv.)│           │
                  │       └────┬─────┘           │
                  │            │CANH/CANL        │
                  │   ┌────────┴────────┐        │
                  │   │ [RTERM JUMPER]  │   ◄─── screw terminal / 2-pin CAN connector
                  │   │ 120 Ω между     │        │
                  │   │   CANH и CANL   │        │
                  │   └─────────────────┘        │
                  └──────────────────────────────┘
```

### 3.2 Входной разъём модуля (со стороны MCU)

| Pin модуля | Функция | Подключение на RP2040 | Примечание |
|------------|---------|----------------------|------------|
| **VCC**    | +5 В питание модуля | BEC (5 В) робота, **не от 3V3 Pico** | TJA1050 требует ≥ 4.75 В для надёжной работы; см. §3.4 |
| **GND**    | земля | GND Pico + GND силовой части | Общая земля обязательна |
| **CS**     | chip select, active LOW | любой свободный GPIO (например GP17) | Один чип на шине — фиксированный GPIO; если несколько MCP2515 — отдельный CS на каждый |
| **SCK**    | SPI clock | SPI0 SCK (GP18) | До 10 МГц, см. §2.1 |
| **SI / MOSI** | host → MCP2515 | SPI0 TX (GP19) | — |
| **SO / MISO** | MCP2515 → host | SPI0 RX (GP16) | — |
| **INT**    | прерывание, open-drain LOW | любой GPIO с прерыванием (GP22 в Pico, GP22 в YD-RP2040; в текущем target уже занят под IMU — взять GP15, см. §3.6) | Внешний pull-up не нужен — он есть на борту |

### 3.3 Выходной разъём модуля (сторона CAN-шины)

- 2-pin винтовой клеммник либо 2-pin header: `CANH`, `CANL`.
- На некоторых модулях есть **дублирующий 2-pin header** для стыковки двух модулей коротким проводом (в этом случае терминация на промежуточных узлах снимается).

### 3.4 Питание: **5 В, не 3.3 В**

Это самый частый footgun с типовым модулем:

- TJA1050 datasheet требует **Vcc 4.75–5.25 В**. При 3.3 В CAN-уровни будут занижены и шина работать не будет.
- Логика SPI на TJA1050-модуле подключена прямо к Vdd (5 В). SCK/MOSI/CS на модуле становятся **5 В CMOS-входами**. RP2040 GPIO 3.3 В — **не 5 В tolerant**, и питать их 5 В нельзя (см. RP2040 datasheet, §1.9.4 "IO Electrical Characteristics", Vih max = 3.6 В).

Решения (по убыванию предпочтения для нашего случая):

1. **Использовать модуль с on-board level-shifter** (например, "MCP2515 CAN Bus Module V2" от ShillehTek — на плате стоит TXS0108E или аналог). Это лучший вариант, питание 3.3 В со стороны MCU.
2. **Резистивный делитель на каждой входной линии модуля**: 2 кОм на GND-стороне + 1 кОм на стороне 5 В. Это делит 5 В до ~3.3 В. Ток на линии мал (модуль потребляет < 1 мкА на входе), падение не мешает. **Нужно ставить делитель только на входы модуля (SCK, MOSI, CS)**; на MISO и INT — там MCP2515 сам тянет в 5 В, и они обратно в 3.3 В GPIO, поэтому **обязательно нужен резистор 1–4.7 кОм последовательно с MISO/INT**, либо external 3.3 В pull-up с диодным смещением.
3. **External level shifter IC** (TXS0108E, SN74LVC8T245, ADG3304) — самое надёжное решение, но добавляет компонент.

> **Рекомендация для PoC**: вариант 1 (купить модуль с shifter). Если модуль уже на руках и без shifter — вариант 2, с явным указанием резисторов на схеме.

### 3.5 Джамперы на типовых модулях

| Джампер / элемент | Назначение | Что делать для BiBa |
|-------------------|------------|--------------------|
| **RTERM (120 Ω)** | Терминатор шины между CANH и CANL | **Снять** на промежуточных узлах; **оставить** на одном физическом конце (на одном ODrive — там есть DIP; либо на самом MCP2515-модуле, если он висит на конце шины) |
| **J1 / J2 (кристалл)** | Не трогать, кварц 8 МГц припаян | — |
| **Резисторы-перемычки для pull-up на INT / TXCAN** | Обычно уже разведены | Не трогать |

> На **большинстве** продаваемых модулей (aliexpress-bulk) единственный пользовательский джампер — это `RTERM`. Некоторые модули (например, ShillehTek) имеют ещё джампер выбора питания 3.3 В vs 5 В.

### 3.6 Конфликт по GP22

GP22 уже занят под `IMU_INT1` в существующем таргете `RPICO_RP2040` (см. `firmware/targets/RPICO_RP2040/target.md` §5). Новый target `RPICO_RP2040_BLDC` стартует с чистого `target.h`, поэтому может свободно выбрать любой GPIO. Рекомендуемая раскладка под RP2040 SPI0:

| Функция    | Pico GPIO | SPI peripheral |
|------------|-----------|----------------|
| SCK        | GP18      | SPI0 SCK |
| MOSI (TX)  | GP19      | SPI0 TX  |
| MISO (RX)  | GP16      | SPI0 RX  |
| CS         | GP17      | GPIO    |
| INT (MCP2515 → RP2040) | GP15 | GPIO с прерыванием |
| Optional: LED status | GP23 | WS2812 — встроенный на YD-RP2040 |

GP15 выбран потому что у него **нет вторичной функции SPI/UART** на стандартной распиновке Pico (в отличие от GP10/14, которые тянут SPI1 — это оставим как резерв для второй SPI-шины, если когда-нибудь добавим второй CAN-модуль).

> При использовании модуля со встроенным level-shifter питание **VCC модуля = 3V3 Pico**, и тогда GP22/GP15 одинаково безопасны.

---

## 4. SPI требования

### 4.1 Электрические

| Параметр | Значение | Источник |
|----------|----------|----------|
| SPI mode | Mode 0,0 (CPOL=0, CPHA=0) | MCP2515 datasheet §SPI |
| Max clock | **10 МГц** (Vdd ≥ 4.5 В) | MCP2515 datasheet DS20001801J §Electrical Characteristics |
| Порядок бит | MSB first | — |
| Setup time (CS LOW до SCK HIGH) | ≥ 50 нс | datasheet AC-traits |
| Hold time (последний SCK HIGH до CS HIGH) | ≥ 50 нс | — |

Для RP2040: при `clk_peri = 125 МГц`, divisor = 16 → `f_spi = 7.8125 МГц`. Это безопасный выбор с запасом и без дробных делителей.

```c
// pico-sdk
spi_init(spi0, 7'812'500);
spi_set_format(spi0, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
```

### 4.2 Топология и длина проводов

На макетах (MCP2515-модуль, припаянный прямо на breakout-плату рядом с Pico):

- SCK/MOSI/MISO/CS ≤ **100 мм**. На 10 МГц фронт ≈ 35 нс; при длине 100 мм задержка распространения < 6 нс — это безопасно.
- GND должен идти **шиной** под сигнальными проводниками (как минимум параллельно) или быть сплошным polygon-ом — иначе ёмкостная связь через "земляной" провод ловит наводки.

На кабельных сборках (модуль удалён от Pico):

- ≤ 200 мм на 8 МГц при условии, что GND-ток идёт по **отдельной** жиле (или по витой паре SCK+GND, MOSI+GND и т.д.).
- Для стабильного 10 МГц уже нужен ribbon cable либо короткая витая пара; на 5 МГц — обычный dupont-дюпон.

### 4.3 Согласование и ёмкости

- MCP2515 input-pin ёмкость Cin ≈ 10 пФ (по datasheet). На 100 мм дорожке добавится ~10–15 пФ. Допустимый предел без специального termination — около 50 пФ.
- Подтяжки: MISO — внешняя 47–100 кОм pull-up не нужна, CS — отдельный GPIO, можно не подтягивать (RP2040 драйвит его сам).
- Защита: по входам со стороны Pico — TVS-диод 5 В SMAJ5.0A на линиях, приходящих с 5 В модуля, если level-shifter не используется.

---

## 5. Обзор BLDC-контроллеров с CAN

Родительская задача (`t_83ccac50`) явно фиксирует **ODrive** как предпочтительный вариант ("драйвер оldrive древний который, у него интерфейс еще на питоне через orodrive-tool"). Ниже — таблица сравнения и обоснование, почему ODrive остаётся целевым.

| Параметр | ODrive (Pro / S1 / Micro) | VESC 6 (HW 6.x) | MKS SERVO (DroneCAN) | BLHeli_32 / AM32 |
|----------|---------------------------|-----------------|-----------------------|------------------|
| Мотор | BLDC / PMSM, до ~5 кВт | BLDC / PMSM, до ~10 кВт | BLDC closed-loop stepper | BLDC (дрон) |
| Рабочее напряжение | 12–58 В (Pro: до 56 В) | 8–60 В | 12–36 В (по моделям) | до 6S (≈ 25 В) |
| Пиковый ток (тип.) | 60–120 А | 100–300 А | 5–10 А | 30–50 А |
| **CAN physical** | 5-контактный терминал (CANH, CANL, GND, …) | RJ45/4-pin (CANH, CANL, +5V, GND) | 4-pin (CANH, CANL, +5V, GND) | Нет native CAN — DShot |
| **CAN-протокол** | CANSimple (см. §6) | VESC native (см. §7) | DroneCAN (CYphal/UAVCAN v0) | — |
| Frame type | 11-bit ID | 29-bit extended ID | 11-bit ID, DroneCAN-формат | — |
| Битрейт по умолчанию | 250 000 (Pro/S1) или автоотбор (Micro/Pro) | 500 000 (настраивается) | 1 000 000 (DroneCAN) | — |
| Discovery / addressing | **Broadcast + heartbeat + can_enumerate.py** | Настраивается через VESC Tool | DroneCAN node-ID allocation | — |
| Watchdog / failsafe | **Set_Input_* сообщения сбрасывают watchdog** | 0.5 с timeout (настраивается) | DroneCAN health/heartbeat | Bidirectional DShot |
| Документация | Отличная, [docs.odriverobotics.com](https://docs.odriverobotics.com/v/latest/manual/can-protocol.html) | Хорошая, [vedderb/bldc comm_can.md](https://github.com/vedderb/bldc/blob/master/documentation/comm_can.md) | Средняя, [DroneCAN](https://dronecan.github.io) | Ограниченная для CAN |
| Цена (примерно) | ~150 USD / шт | ~70 USD за VESC 6 | ~30–60 USD | ~10–30 USD |
| Ключевая сила | Открытая прошивка, position/torque/velocity | Открытый исходник, e-bike focus | Stepper с обратной связью | Дёшево, дроны |
| Ключевая слабость | Дорого, устаревшая серия (Pro) | Сложный API, требует VESC Tool | DroneCAN требует libcyphal | Нет CAN, нет position control |

### 5.1 Решение по выбору целевого контроллера

**Целевой BLDC-контроллер — ODrive (Pro / S1 / Micro).**

Обоснование:

1. **У пользователя уже есть пара ODrive** — явное требование родительской задачи (`t_83ccac50`). Не покупаем новое железо.
2. **CANSimple протокол документирован** ([CAN Protocol — ODrive Docs](https://docs.odriverobotics.com/v/latest/manual/can-protocol.html)). 11-bit ID, формат `(node_id << 5) | cmd_id`. Это умещается в один регистр MCP2515 и не требует расширенного CAN-формата.
3. **Discovery через broadcast** (cmd 0x06 + RTR, `can_enumerate.py`) упрощает первый запуск: не надо лезть в odrivetool, чтобы выставить node_id.
4. **Watchdog на Set_Input_Vel** — если RP2040 зависнет, ODrive сам заармится в ESTOP через ~100 мс.
5. **Одна команда на команду движения** (`Set_Input_Vel` — 8 байт, float32 vel + float32 torque_ff). В CAN-frame помещается ровно одна команда для одного колеса.
6. **Силовая часть уже сертифицирована** — у Pro есть brake resistor control, overcurrent, overtemperature встроенные.

Trade-offs:

- Цена выше VESC. Принято как факт, что у пользователя уже куплено.
- Старая серия "ODrive (legacy)" может требовать ручной настройки через `odrivetool`. Новый `S1` / `Pro` имеет Web GUI.
- В старой линейке CAN-интерфейс изолирован только частично. Если нужна полная galvanic isolation — поставить изолированный DC-DC между 5 В Pico-стороны и 5 В ODrive-стороны и isolator (ADM3050/ISO1050) в разрыв CANH/CANL. Для **PoC — опционально**.

Резервные варианты на случай, если ODrive окажется недоступен:

- **VESC 6 / VESC 75/300** — стандарт в DIY-ebike. Протокол простой, но требует 29-bit ID. MCP2515 поддерживает, но в коде драйвера надо настраивать extended-frame mask/filter, а не 11-bit.
- **MKS SERVO57D / SERVO42D** — не BLDC в привычном смысле (closed-loop stepper), зато CAN-протокол DroneCAN. Применим для маленьких колёс / робо-руки, не для основного привода BiBa.

---

## 6. ODrive CANSimple — спецификация протокола

Источники:
- [CAN Protocol — ODrive Docs (latest)](https://docs.odriverobotics.com/v/latest/manual/can-protocol.html)
- [CAN Bus Guide — ODrive Docs](https://docs.odriverobotics.com/v/latest/guides/can-guide.html)
- [DBC file at odrive-firmware repository](https://github.com/odriverobotics/ODrive/blob/master/docs/can-protocol.md)

### 6.1 Физический уровень

- **Linear bus topology**, витая пара.
- **CANH ↔ CANH, CANL ↔ CANL** между всеми узлами.
- **120 Ω** терминатор между CANH и CANL на каждом **физическом конце** шины.
- Хороший общий GND между всеми узлами.
- На ODrive Pro / S1 / Micro: 5-pin разъём с CANH, CANL, GND, +5V (через него же питание CAN-трансивера на плате, не все версии), ERR/RST.

### 6.2 Битрейт

- По умолчанию — autobaud. ODrive автоматически определяет битрейт шины при старте. Поддерживает 125 к / 250 к / 500 к / 1000 к.
- Sample point: **87.5%** (8 time quanta: 1 sync + 6 propseg+phase1 + 1 phase2), SJW = 1.
- **Рекомендуемая для первого запуска: 250 кбит/с** — самый надёжный режим, прощает длинные провода и плохое качество земли. Переключить на 500 к если нужна более высокая частота команд.

### 6.3 Framing — CANSimple message ID

```
 11-bit CAN ID
┌───────┬────────┐
│[10:5] │ [4:0]  │
│ node  │ cmd_id │
│ _id   │        │
└───────┴────────┘
  6 бит    5 бит
```

- `node_id`: 0–63. По умолчанию unaddressed `node_id = 0x3F` (ODrive не шлёт cyclic до тех пор, пока не присвоен node_id).
- `cmd_id`: 0–31. Полный список — §6.5.
- `message_id = (node_id << 5) | cmd_id`.

> Пример: отправить `Set_Input_Vel` (cmd_id `0x0D`) на node_id `0` — это CAN-ID `0x0D`. На node_id `1` — `0x2D`.

### 6.4 Endianness и типы

- **Little-endian** для всех multibyte-полей.
- Float — IEEE-754 single (4 байта, little-endian byte order).
- RTR — Remote Transmission Request, для запроса `Get_*` сообщений от ODrive.
- Broadcast: `node_id = 0x3F` — host шлёт, все ODrive принимают.
- Reserved/padding — host ставит 0, ODrive игнорирует.

### 6.5 Команды CANSimple

Полная таблица из официальной документации:

| CMD ID | Name | Direction | Payload |
|-------:|------|-----------|---------|
| `0x00` | Get_Version | ODrive → Host | 8× uint8: Protocol_Version, Hw_Version_Major/Minor/Variant, Fw_Version_Major/Minor/Revision/Unreleased |
| `0x01` | Heartbeat | ODrive → Host | uint32 Active_Errors, uint8 Axis_State, uint8 Procedure_Result, uint8 Trajectory_Done_Flag |
| `0x02` | Estop | Host → ODrive | empty → disarms with `ESTOP_REQUESTED` |
| `0x03` | Get_Error | ODrive → Host | uint32 Active_Errors, uint32 Disarm_Reason |
| `0x04` | RxSdo | Host → ODrive | uint8 Opcode (0=read, 1=write), uint16 Endpoint_ID, uint8 Reserved, uint32 Value |
| `0x05` | TxSdo | ODrive → Host | mirror of RxSdo (response) |
| `0x06` | Address | both | uint8 Node_ID, uint48 Serial_Number — discovery + addressing |
| `0x07` | Set_Axis_State | Host → ODrive | uint32 Axis_Requested_State (0=IDLE, 8=CLOSED_LOOP_CONTROL) |
| `0x09` | Get_Encoder_Estimates | ODrive → Host | float32 Pos_Estimate (rev), float32 Vel_Estimate (rev/s) |
| `0x0C` | Set_Input_Pos | Host → ODrive | float32 Input_Pos, int16 Vel_FF (0.001 rev/s), int16 Torque_FF (0.001 Nm) |
| `0x0D` | Set_Input_Vel | Host → ODrive | **float32 Input_Vel (rev/s), float32 Input_Torque_FF (Nm)** |
| `0x0E` | Set_Input_Torque | Host → ODrive | float32 Input_Torque (Nm) |
| `0x0F` | Set_Limits | Host → ODrive | float32 Velocity_Limit (rev/s), float32 Current_Limit (A) |
| `0x11` | Set_Traj_Vel_Limit | Host → ODrive | float32 Traj_Vel_Limit (rev/s) |
| `0x12` | Set_Traj_Accel_Limits | Host → ODrive | float32 Traj_Accel_Limit, float32 Traj_Decel_Limit (rev/s²) |
| `0x13` | Set_Traj_Inertia | Host → ODrive | float32 Traj_Inertia (Nm/(rev/s²)) |
| `0x14` | Get_Iq | ODrive → Host | float32 Iq_Setpoint, float32 Iq_Measured (A) |
| `0x15` | Get_Temperature | ODrive → Host | float32 FET_Temperature, float32 Motor_Temperature (°C) |
| `0x16` | Reboot | Host → ODrive | uint8 Action (0=reboot, 1=save_config, 2=erase_config, 3=enter_dfu) |
| `0x17` | Get_Bus_Voltage_Current | ODrive → Host | float32 Bus_Voltage (V), float32 Bus_Current (A) |
| `0x18` | Clear_Errors | Host → ODrive | uint8 Identify (1=blink LED для identification) |
| `0x19` | Set_Absolute_Position | Host → ODrive | float32 Position (rev) |
| `0x1A` | Set_Pos_Gain | Host → ODrive | float32 Pos_Gain |
| `0x1B` | Set_Vel_Gains | Host → ODrive | float32 Vel_P_Gain, float32 Vel_I_Gain |
| `0x1C` | Get_Torques | ODrive → Host | float32 Torque_Target, float32 Torque_Estimate (Nm) |
| `0x1D` | Get_Powers | ODrive → Host | float32 Electrical_Power, float32 Mechanical_Power (W) |
| `0x1F` | Enter_DFU_Mode | Host → ODrive | empty |

### 6.6 Минимальный цикл управления

Цикл для режима **velocity control** (наша основная задача):

1. **Discovery (один раз при старте)**:
   - Host → broadcast (CAN-ID = `0x7F` = `0x3F << 5 | 0x06`, RTR=1)
   - ODrive → CAN-ID `0x7F`, payload `{Node_ID, Serial_Number}` (после рандомной задержки ~250 мс).
   - Host отправляет Address command с target `Node_ID` каждому ODrive.

2. **Конфигурация (один раз после addressing)**:
   - `Set_Axis_State(IDLE)`
   - `Set_Limits(velocity_max, current_max)`
   - `Set_Controller_Mode(VELOCITY_CONTROL)` — через RxSdo/TxSdo.

3. **Управление в основном цикле (50–100 Гц)**:
   - `Set_Axis_State(CLOSED_LOOP_CONTROL)` один раз перед стартом движения.
   - Каждый тик: `Set_Input_Vel(target_vel, torque_ff)` — 8 байт payload.
   - Параллельно принимаем `Heartbeat` и `Get_Encoder_Estimates`.

4. **Failsafe**:
   - Если host не шлёт `Set_Input_*` дольше watchdog timeout → ODrive задизармится автоматически. Это **встроенный failsafe уровня 2**: даже если RP2040 зависнет, колесо не закрутится бесконечно.
   - На стороне RP2040 — отдельный failsafe: если CRSF теряется → перестать слать `Set_Input_Vel`, оставить последнюю valid-команду или явный `Estop`.

### 6.7 Расчёт round-trip latency

- Шина 250 кбит/с. `Set_Input_Vel` — 8 байт payload + 47 bit (CAN frame overhead @ 11-bit ID): ≈ 47 × 4 + 64 × 4 = 444 мкс на шине. На 500 кбит/с — 222 мкс.
- MCP2515 SPI round-trip (read status + write TX buffer) ≈ 50 мкс при 8 МГц SPI.
- Итого round-trip host → CAN → ODrive: **~500 мкс** на 250 кбит/с. Это вписывается в CRSF control loop 50 Гц (20 мс).

### 6.8 ODrive UART ASCII — альтернатива CAN для single-board / debugging setup

Источники:
- [ODrive ASCII Protocol (latest docs)](https://docs.odriverobotics.com/v/latest/manual/ascii-protocol.html)
- [ODrive UART Interface (latest docs)](https://docs.odriverobotics.com/v/latest/manual/uart.html)
- [ODrive — Arduino UART guide](https://docs.odriverobotics.com/v/latest/guides/arduino-uart-guide.html)

ODrive, помимо CAN/CANSimple, поддерживает **text-based ASCII-протокол** через UART или USB-CDC. Это тот самый протокол, через который работает `odrivetool` и Arduino-библиотека `ODriveArduino`. Для нашего use-case он интересен в двух ситуациях:

1. **Отладочный/лабораторный setup** — когда хочется посмотреть параметры (`r vbus_voltage`, `r axis0.controller.input_vel`) или погонять мотор одной строкой, без поднятия MCP2515 и всей CAN-инфраструктуры.
2. **Одноплатная конфигурация без отдельного CAN-модуля** — если решено отказаться от MCP2515 и управлять парой ODrive по UART напрямую (на каждый ODrive свой UART-порт RP2040). Это упрощает BOM и устраняет 5V/3.3V-проблему с MCP2515.

#### 6.8.1 Физический уровень

| Параметр | Значение |
|----------|----------|
| UART-порт на ODrive | `UART_A` (по умолчанию), пины GPIO1 (TX) / GPIO2 (RX). Альтернатива — `UART_B` на GPIO3/GPIO4, если GPIO1/2 нужны под другое. |
| Логические уровни | **3.3 В**. RX **5V-tolerant** (это явно сказано в [ODrive UART docs](https://docs.odriverobotics.com/v/latest/manual/uart.html)) — то есть с RP2040 (3.3 В) можно подключать **напрямую**, без level-shifter. |
| Baudrate по умолчанию | **115200** 8N1. Меняется через `odrv0.config.uart_a_baudrate`. |
| Half/Full duplex | **Full duplex** (отдельные TX/RX линии). |
| Flow control | None (аппаратного нет — нужно держать частоту команд ≤ ~500 Гц, чтобы RX-буфер ODrive не переполнялся). |
| Длина проводов | UART 115200 — до **3 м** при нормальной земле. На 921600 (максимум, который тянет ODrive UART-A) — до ~1 м. |

#### 6.8.2 Сравнение с CAN

| Критерий | CANSimple (§6) | UART ASCII (§6.8) |
|----------|----------------|--------------------|
| Кол-во ODrive на шине | До 63 (по `node_id`) | **1 ODrive = 1 UART-порт** (на RP2040 два UART'а — два ODrive, дальше только software-UART, что для 50 Гц неудобно) |
| Доп. железо | MCP2515+TJA1050 модуль | **Ничего** (прямой UART) |
| Latency round-trip | ~500 мкс @ 250 кбит/с | ~870 мкс @ 115200 (14 байт ASCII-строки `v 0 1.0 0\n` ≈ 14 × 87 мкс + 1 ms turnaround от ODrive на парсинг). В реальности — **1–2 мс**. |
| Размер команды | 8 байт binary | 10–20 байт ASCII |
| Конфигурация/параметры | Через RxSdo/TxSdo (overhead) | Нативно: `r property` / `w property value` |
| Discovery | CAN Address broadcast | Нет — адресация по UART-порту |
| Документация | Хорошая | Отличная (каждый параметр через `r`/`w`) |
| Watchdog | Сбрасывается на каждый `Set_Input_*` | Тоже сбрасывается на каждый setpoint command (`v`/`q`/`p`/`c`/`t`/`u`) |
| Подходит для production на BiBa | **Да** (CAN — основной путь) | Как **fallback / debug** или для одноплатного PoC |
| Подходит для bench-test | Требует MCP2515 | **Идеален** — один USB-UART + терминал |

#### 6.8.3 Протокол ASCII — команды

Из [ODrive ASCII Protocol Reference](https://docs.odriverobotics.com/v/latest/manual/ascii-protocol.html). Все команды — ASCII-строки, заканчиваются `\n` (LF). ODrive **не эхо** команды. Опциональный GCode-checksum: `*XX` после команды, где `XX` — XOR всех предыдущих байт.

| Команда | Формат | Назначение | Пример | Watchdog |
|---------|--------|------------|--------|----------|
| `t` | `t motor destination` | Trapezoidal trajectory (position) | `t 0 -2\n` | ✓ |
| `q` | `q motor pos [vel_lim] [torque_lim]` | Position (одиночный setpoint) | `q 0 -2 1 0.1\n` | ✓ |
| `p` | `p motor pos [vel_ff] [torque_ff]` | Position в real-time loop | `p 0 -2 0 0\n` | ✓ |
| `v` | `v motor vel [torque_ff]` | **Velocity (наш основной)** | `v 0 1.0 0\n` | ✓ |
| `c` | `c motor torque` | Torque | `c 0 0.5\n` | ✓ |
| `f` | `f motor` → ответ `pos vel` | Feedback (pos/vel) | `f 0\n` → `1.234 0.567\n` | — |
| `u` | `u motor` | Touch watchdog (без setpoint) | `u 0\n` | ✓ |
| `r` | `r property` → ответ: текстовое значение | Read параметр | `r vbus_voltage\n` → `24.087744\n` | — |
| `w` | `w property value` | Write параметр | `w axis0.controller.input_pos -123.456\n` | — |
| `ss` | `ss` | Save config | `ss\n` | — |
| `se` | `se` | Erase config | `se\n` | — |
| `sr` | `sr` | Reboot ODrive | `sr\n` | — |
| `sc` | `sc` | Clear errors | `sc\n` | — |

`motor` — `0` или `1` (M0 / M1 на одном ODrive). `velocity` — в turns/s (= rev/s в терминах §6). `torque` — в Nm.

#### 6.8.4 Минимальный цикл управления (UART)

```c
// RP2040 / pico-sdk — отправка setpoint на левый ODrive (UART1, GP4/GP5)
char buf[32];
int n = snprintf(buf, sizeof buf, "v 0 %.4f 0\n", target_vel_left);
uart_write_blocking(uart1, (uint8_t*)buf, n);
// на правый — тот же шаблон через uart0 (GP12/GP13)
```

Цикл (50 Гц, как в §6.6 для CAN):

1. **Конфигурация (один раз, при старте)**: через ASCII `w axis0.controller.config.control_mode 2` (velocity), `w axis0.requested_state 8` (CLOSED_LOOP), `ss` (save config).
2. **Каждый тик**: `v 0 <vel>\n` на левый ODrive + `v 0 <vel>\n` на правый ODrive (через два UART'а).
3. **Feedback (опционально, по желанию)**: `f 0\n` → парсим строку `pos vel\n` (используем DMA RX на PIO UART, чтобы не блокировать loop).
4. **Failsafe**: перестать слать `v` → ODrive задизармится по watchdog (тот же механизм, что и в CAN-варианте).

#### 6.8.5 Latency budget

- 14 байт ASCII-строки `v 0 1.0000 0\n` @ 115200 = 14 × 87 мкс ≈ **1.2 мс** на передачу.
- ODrive парсит строку в основном loop, отзыв — **~500 мкс** (по измерениям ODriveArduino-комьюнити).
- Round-trip `host → UART → ODrive`: **~1.7 мс** (без feedback). С feedback через `f` — ещё +1.2 мс на запрос-ответ.
- В CRSF 50 Гц цикле (20 мс) — вписывается с запасом (~10%).

#### 6.8.6 Ограничения и подводные камни

1. **Один UART = один ODrive**. RP2040 имеет два аппаратных UART'а (UART0, UART1). Это покрывает наш случай (2 ODrive = 2 колеса). Если когда-нибудь добавится третий привод — придётся либо поднимать software-UART на PIO (реалистично, 115200 на PIO стабильно тянется), либо переходить обратно на CAN.
2. **Нет broadcast** — нельзя одной строкой сбросить оба ODrive. Дублируем команду на оба UART'а (это дешевле, чем CAN-альтернатива с broadcast на оба node_id).
3. **Нет hardware flow control** — если RP2040 будет слать команды быстрее, чем ODrive успевает парсить (например, > 500 Гц), ODrive начнёт терять байты. Держим частоту ≤ 200 Гц с запасом.
4. **Парсинг ASCII на ODrive** — заметный CPU-overhead. На одном ODrive при двух моторах одновременно это ~10% CPU по сравнению с CAN-binary. На PoC это неважно, на нагруженном контроллере — может стать узким местом.
5. **ACK/ответ приходит асинхронно** — нужно правильно разделять TX и RX-буферы на стороне RP2040, либо использовать DMA на RX.
6. **`f` не гарантирует актуальность данных** — это snapshot, между запросом и ответом мотор может уехать. Для closed-loop контроля достаточно `v` + опциональный `f`.

#### 6.8.7 Рекомендация для BiBa

- **Production target** — оставляем CANSimple как основной канал (§6.1–§6.7). UART ASCII держим как **debug-канал**: можно подключиться USB-UART к ODrive напрямую и через `screen` диагностировать параметры без участия RP2040.
- **Bench-test target** — если будет отдельный PoC с одним ODrive без CAN-модуля, UART ASCII — основной канал. Это убирает 5V/3.3V-проблему, BOM упрощается, latency всё равно укладывается.
- В `RPICO_RP2040_BLDC` target header'е имеет смысл оставить UART1 (GP4/GP5) как `ODRIVE_UART_TX/RX` и заложить опциональный код-путь для ASCII-протокола, активируемый через Kconfig (`-DODRIVE_LINK=UART`).

---

## 7. Альтернативы: VESC (для справки)

Источник: [vedderb/bldc comm_can.md](https://github.com/vedderb/bldc/blob/master/documentation/comm_can.md).

VESC native CAN:

- **29-bit extended ID**: `(controller_id) | ((uint32_t)cmd_id << 8)`.
- Все simple-команды имеют 4-байтовый payload = int32 big-endian с scaling factor.
- Пример: `Set_Current` = cmd `1`, scaling 1000. Чтобы задать 51 А на VESC ID 23: CAN-ID `0x0117`, payload `{0x00, 0x00, 0xC7, 0x38}` = 51000 (big-endian).
- Simple-команды:

  | CMD | Name | Scaling | Unit |
  |-----|------|---------|------|
  | 0 | SET_DUTY | 100000 | % / 100 |
  | 1 | SET_CURRENT | 1000 | A |
  | 2 | SET_CURRENT_BRAKE | 1000 | A |
  | 3 | SET_RPM | 1 | RPM |
  | 4 | SET_POS | 1000000 | deg |
  | 10..13 | relative-варианты | | |

- Status messages: `STATUS(9)`, `STATUS_2(14)`, `STATUS_3(15)`, `STATUS_4(16)`, `STATUS_5(27)`, `STATUS_6(58)`.
- Timeout по умолчанию — 0.5 с; рекомендуется слать команды с фиксированной частотой ≥ 50 Гц.

> Если в будущем добавим VESC-совместимость, потребуется extended-frame в MCP2515. Переключается одним битом в `CANCTRL` и фильтры (маски `0x1FFFFFFF`).

---

## 8. Диаграмма подключения (Mermaid)

```mermaid
flowchart LR
    subgraph RP2040["RP2040 (Pico)"]
        SPI0[("SPI0\nGP18 SCK\nGP19 MOSI\nGP16 MISO")]
        GPIO[("GPIO\nGP17 CS\nGP15 INT")]
        CRSF[("UART0\nGP0/GP1\nCRSF")]
        CR[("Main loop\n+ failsafe\nRP2040 C SDK")]
        SPI0 --- GPIO
    end

    subgraph MCP2515["MCP2515 module"]
        M[("MCP2515\n+ TJA1050\n+ 8 MHz XTAL\n+ 120Ω jumper")]
    end

    subgraph CANBUS["CAN bus (twisted pair, 120Ω at both ends)"]
        CANL((CANL))
        CANH((CANH))
    end

    subgraph ODrive["ODrive #1 (left wheel)"]
        OD1[("ODrive Pro/S1/Micro\nnode_id=0\nCL: vel")]
        TERM1[/"120Ω\nDIP 'CAN 120R'"/]
    end

    subgraph ODrive2["ODrive #2 (right wheel)"]
        OD2[("ODrive Pro/S1/Micro\nnode_id=1\nCL: vel")]
        TERM2[/"120Ω\nDIP 'CAN 120R'"/]
    end

    CR --> SPI0
    SPI0 -- SPI @ 8 MHz\nMode 0,0 --> M
    GPIO -- INT + CS --> M
    M -- CANH/CANL\n5 V diff --> CANH
    M -- CANL --> CANL
    CANH --- CANL
    CANH --- OD1
    CANL --- OD1
    OD1 --- TERM1
    CANH --- OD2
    CANL --- OD2
    OD2 --- TERM2
```

ASCII-вариант для печати:

```
                                +-------------+
        +-------+               | ODrive #1   |       +----+
  SPI   | MCP2515|    CANH ---- | left wheel  | ----+ | 120|
 <----> | +TJA1050|----CANL ---- | node_id = 0 |     +-+ Ω  |
  CS,   | (8 MHz)|              +-------------+       +----+
  INT   +-------+                              +
         |       |                  CANH ------+
   RP2040+-------+                  CANL ------+
                                  +
                         +-----------------+
                         | ODrive #2       |
                         | right wheel     |
                         | node_id = 1     |
                         +-----------------+
                              |      |
                              +------+ 120Ω (DIP on last ODrive)
```

---

## 9. Рекомендуемая распиновка таргета `RPICO_RP2040_BLDC`

| Функция | Pico GPIO | SPI/Peripheral | Цель |
|---------|-----------|----------------|------|
| SPI0 SCK | GP18 | SPI0 SCK | MCP2515 SCK |
| SPI0 MOSI (TX) | GP19 | SPI0 TX | MCP2515 SI |
| SPI0 MISO (RX) | GP16 | SPI0 RX | MCP2515 SO |
| MCP2515 CS | GP17 | GPIO | MCP2515 CS |
| MCP2515 INT | GP15 | GPIO (interrupt) | MCP2515 INT |
| CRSF TX | GP0 | UART0 TX | ELRS RX pin |
| CRSF RX | GP1 | UART0 RX | ELRS TX pin |
| Status LED | GP25 | GPIO | встроенный LED Pico |
| NeoPixel | GP23 | PWM / PIO | WS2812 на YD-RP2040 |

### 9.1 Опциональная раскладка при использовании UART ASCII-протокола (см. §6.8)

Если в target выбран режим `-DODRIVE_LINK=UART`, MCP2515 не нужен, и пины перераспределяются:

| Функция | Pico GPIO | Peripheral | Цель |
|---------|-----------|------------|------|
| ODrive-UART TX (host→ODrive) | GP4 | UART1 TX | ODrive UART-A RX (GPIO2) |
| ODrive-UART RX (ODrive→host) | GP5 | UART1 RX | ODrive UART-A TX (GPIO1) |

> На Pico 5V-tolerant RX у ODrive снимает проблему level-shifter'а (см. §6.8.1).
> **Один аппаратный UART = один ODrive.** RP2040 имеет ровно два аппаратных UART'а: UART0 занят под CRSF (GP0/GP1), UART1 — под один ODrive (GP4/GP5). На второй ODrive варианты:
> 1. Поднять **PIO-UART** (библиотека `pico-pio-uart` от Карлоса Гамбоа / `pio_uart` пример из pico-sdk-extras). 115200 на PIO тянется стабильно, остаётся GPIO-свобода.
> 2. Остаться на CAN для второго ODrive (гибрид: левый мотор — UART, правый — CAN). На практике это усложняет код, не рекомендуется.
> 3. Для полноценной пары ODrive по UART — мигрировать на RP2350 (3 аппаратных UART'а) или взять плату с двумя RP2040. Для BiBa — overkill, поэтому **production остаётся на CAN**, UART-вариант держим как bench-test.

### 9.2 Комбинированная раскладка (CAN — production, UART — debug)

Основная продакшен-конфигурация использует MCP2515 на SPI0 (GP16–GP19, GP17=CS, GP15=INT) + ODrive по CAN. Дополнительно оставляем UART1 (GP4/GP5) как опциональный debug-канал: при необходимости можно подключить USB-UART-кабель к ODrive напрямую (минуя RP2040) и через терминал (`screen`, `minicom` или odrivetool по USB) посмотреть параметры, либо подключить UART1 RP2040 к ODrive UART-A как в §9.1 для отдельного bench-теста без полной CAN-инфраструктуры.

> GP10/11/14 остаются свободными — могут быть резервом для второй MCP2515 (если когда-нибудь понадобится отдельная CAN-сеть для BMS/IMU) или для GPIO-выхода общего назначения.

Питание:

- Pico питается от USB (development) или от BEC 5 В через VBUS (на роботе).
- MCP2515-модуль питается от **BEC 5 В робота** (один общий rail с ODrive). Если используется модуль с on-board level-shifter — VCC модуля = 3V3 Pico (предпочтительно, чтобы не городить делители).
- Для UART-варианта: питание Pico и ODrive общее, дополнительных модулей нет.

---

## 10. Открытые вопросы и точки расширения

1. **Galvanic isolation**: на ODrive Pro есть изолированный CAN, на старой линейке — нет. Решение — поставить iso-coupler (ISO1050 / ADM3050) в разрыв CANH/CANL. **Для PoC — отложено**.
2. **RTR-сообщения**: MCP2515 умеет автоматически отвечать на RTR из буфера, но удобнее хосту самому опрашивать через periodic-encoder-msg, настроив `axis.config.can.encoder_msg_rate_ms`. Это упрощает код на стороне RP2040.
3. **Heartbeat → failsafe gate**: использовать Heartbeat от ODrive как дополнительный safety-канал. Если ODrive ушёл в disarmed state — host тоже должен перейти в failsafe (прекратить слать Set_Input_Vel).
4. **Boot-up time**: ODrive autobaud может занять 200–500 мс. RP2040 на это время должен уметь отдавать нулевые команды или явно ждать `Get_Version` от ODrive, и только потом слать `Set_Axis_State(CLOSED_LOOP)`. В UART-варианте этой задержки нет — autobaud касается только CAN.
5. **Термомониторинг**: на ODrive есть `Get_Temperature` (FET + Motor). У PICО пока нет IMU/ADC на этом target — можно переиспользовать GP26/GP27 как ADC0/ADC1 для NTC-термистора на радиаторе (если нужно). В UART-варианте есть нативный `r axis0.motor_thermistor.temperature` без CAN-overhead.
6. **Двухмоторный режим**: команды на левый/правый ODrive идут параллельно, ID разные (node_id=0, node_id=1). Шина успевает при частоте 50 Гц: `2 × 8 байт × ~500 мкс = 1 мс/cycle` из 20 мс — огромный запас. В UART-варианте — два UART'а (один аппаратный + один PIO), либо PIO на оба, либо гибрид с CAN.
7. **Конфликт UART0**: GP0/GP1 заняты под CRSF (UART0). Если в production хотим UART-debug канал на ODrive — он идёт через UART1 (GP4/GP5) и работает одновременно с CAN-шиной. Никаких конфликтов.
8. **PIO-UART как опция для второго ODrive** (см. §9.1): нужно выбрать готовую библиотеку. Кандидаты: `pico-pio-uart` (Camel CASE, GitHub), пример `pio_uart` в pico-sdk-extras, либо самописный PIO-программный UART. Размер PIO-программы ~12 инструкций, RAM-буфер на 32 байта хватит для 14-байт команды + ответа.

---

## 11. Ссылки на источники

### Datasheet и спецификации
- [MCP2515 Stand-Alone CAN Controller with SPI — DS20001801J (Microchip)](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP2515-Stand-Alone-CAN-Controller-with-SPI-20001801J.pdf)
- [MCP2515 product page (Microchip)](https://www.microchip.com/en-us/product/mcp2515)
- [MCP2515 SPI bus notes (Linux kernel DT bindings)](https://trac.gateworks.com/wiki/SPI) — проверка timing на стороне host
- [RP2040 Datasheet (Raspberry Pi)](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf)
- [TJA1050 product page (NXP)](https://www.nxp.com/products/interfaces/can-transceivers/can-transceivers/TJA1050)

### Модули и туториалы
- [Last Minute Engineers — MCP2515 CAN Module Tutorial](https://lastminuteengineers.com/mcp2515-can-module-arduino-tutorial/)
- [ComponentIndex — MCP2515 wiring, code, pinout](https://componentindex.net/components/mcp2515/)
- [ShillehTek — MCP2515 CAN Bus Module Manual](https://shillehtek.com/blogs/shillehtek-product-manuals/mcp2515-can-bus-module-tja1050-receiver-spi-manual)
- [yasir-shahzad/MCP2515-CAN-Bus-Module (GitHub)](https://github.com/yasir-shahzad/MCP2515-CAN-Bus-Module)
- [Emre's Bench — Arduino CAN Bus Module Schematic](https://emresbench.com/tips/can.html)

### BLDC протоколы
- [ODrive — CAN Protocol (latest)](https://docs.odriverobotics.com/v/latest/manual/can-protocol.html)
- [ODrive — CAN Bus Guide](https://docs.odriverobotics.com/v/latest/guides/can-guide.html)
- [ODrive — DBC file (firmware repo)](https://github.com/odriverobotics/ODrive/blob/master/docs/can-protocol.md)
- [ODrive — ASCII Protocol (latest)](https://docs.odriverobotics.com/v/latest/manual/ascii-protocol.html)
- [ODrive — UART Interface (latest)](https://docs.odriverobotics.com/v/latest/manual/uart.html)
- [ODrive — Arduino UART guide](https://docs.odriverobotics.com/v/latest/guides/arduino-uart-guide.html)
- [ODriveArduino library](https://github.com/madcowswe/ODrive/tree/master/Arduino/ODriveArduino) — эталонная реализация ASCII-протокола для MCU
- [pico-pio-uart (Camel CASE)](https://github.com/camel-case/pico-pio-uart) — PIO-UART библиотека для RP2040 (опция для второго ODrive по UART)
- [VESC — CAN-bus communication (vedderb/bldc)](https://github.com/vedderb/bldc/blob/master/documentation/comm_can.md)
- [VESC 6 CAN formats (PDF)](https://vesc-project.com/sites/default/files/imce/u15301/VESC6_CAN_CommandsTelemetry.pdf)
- [DroneCAN (UAVCAN v0) protocol spec](https://dronecan.github.io)
- [MKS DroneCAN integration guide](https://www.mks-servo.com/MKS-Community/MKS-DroneCAN-Intro)

### Внутренние документы проекта
- `docs/wiring.md` — текущая распиновка BTS7960/Pi
- `docs/system_architecture.md` — канонический разбор всех композиций
- `docs/stm32_architecture.md` — STM32F103 распиновка и SPI companion link
- `docs/variants.md` — матрица hardware-вариантов (нужно обновить после выбора целевого BLDC)
- `firmware/targets/RPICO_RP2040/target.md` — текущая распиновка RP2040-таргета
- `.planning/PROJECT.md` — текущее состояние Phase 1, тепловой режим BTS7960
- `.planning/STATE.md` — Phase 4-6 завершены, Phase 7 — IS-RPM интеграция

---

## 12. Выбор зафиксирован

| Решение | Значение |
|---------|----------|
| Целевой SPI-модуль | **MCP2515 + TJA1050** (8 МГц кварц, 120 Ω терминатор по джамперу) |
| SPI mode | Mode 0,0 (CPOL=0, CPHA=0) |
| SPI clock | **7.8125 МГц** (делитель 16 от `clk_peri = 125 МГц`, ниже 10 МГц cap модуля, целочисленный делитель — без jitter) |
| Уровни | Предпочтительно модуль с **on-board level-shifter** (3.3 V), либо резистивный делитель 2k/1k на 5V-линиях с последовательным 1k на MISO/INT |
| Шина | CAN 2.0B active, **11-bit ID**, autobaud, начальный битрейт **250 кбит/с** |
| Целевой BLDC | **ODrive Pro / S1 / Micro** (CANSimple) |
| Протокол (production) | CANSimple: `message_id = (node_id << 5) &#124; cmd_id`, little-endian, IEEE-754 float |
| Протокол (альтернатива) | ODrive ASCII через **UART_A** @ 115200 8N1, 3.3 В логика (RX 5V-tolerant), команда `v motor vel torque_ff`. См. §6.8. |
| Command loop | `Set_Input_Vel(0x0D)` каждые 10–20 мс по CAN, watchdog сбрасывается сам; либо `v 0 <vel>\n` каждые 10–20 мс по UART |
| Discovery (CAN) | Broadcast `Address(0x06)` с RTR=1 при инициализации |
| Discovery (UART) | Не требуется — адресация по выделенному UART-порту на каждый ODrive |
| Debug-канал | UART1 (GP4/GP5) — подключение к ODrive UART-A напрямую, ASCII-протокол через терминал (`screen /dev/ttyUSB0 115200`) |
| Failsafe | Прекратить `Set_Input_*` при потере CRSF → ODrive задизармится по своему watchdog (одинаково работает и для CAN, и для UART-варианта) |

Дальнейшие шаги — в задаче `t_3cca56ce` (Architecture нового таргета) и `t_a3ed6b73` / `t_6c05e712` / `t_add4db37` (зависит от декомпозиции). Настоящий документ служит опорой для ADR и `target.md` нового таргета `RPICO_RP2040_BLDC`.