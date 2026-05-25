# Phase 5 Context: Current Sensing & ADC Architecture

**Created:** 2026-05-19  
**Status:** LOCKED — ready for planning

---

## Decisions Locked

### 1. BTS7960 IS Pin Topology

BTS7960 — это **полумост** (half-bridge). Один мотор = **2 чипа** BTS7960 (один для направления вперёд, один назад). У каждого чипа **один IS-пин**. Итого на роботе:

| IS пин | Описание |
|--------|---------|
| IS_L_fwd | Левый мотор, HIGH-side (движение вперёд) |
| IS_L_rev | Левый мотор, LOW-side (движение назад) |
| IS_R_fwd | Правый мотор, HIGH-side (движение вперёд) |
| IS_R_rev | Правый мотор, LOW-side (движение назад) |

**Текущий баг в прошивке:** `LEFT_R_IS` и `LEFT_L_IS` алиасированы на один канал (CH1). `RIGHT_R_IS` и `RIGHT_L_IS` алиасированы на CH2. Одна из двух IS каждого мотора не читается.

**Физика IS-пина:**
- `kILIS = 8500` (typ) — соотношение тока нагрузки к IS-току
- `RIS = 1kΩ` → `VIS = (IL / 8.5A) × 1V`
- При 30A: `VIS = 3.53V` — превышает RP2040 ADC (3.3V) → клиппинг при ~28A
- При FSR=±4.096V ADS1115: максимум = `4.096 × 8.5 = 34.8A` без клиппинга ✓

**IS-пин активен только когда активен high-side switch** (вперёд или назад). Для получения тока мотора берём `max(IS_fwd, IS_rev)` — только один активен одновременно.

---

### 2. ADC Распределение

#### ADS1115 (I2C, 4 канала, 16-bit)

| Канал | Сигнал | Тип |
|-------|--------|-----|
| ch0 (AIN0 vs GND) | IS_L_fwd | single-ended |
| ch1 (AIN1 vs GND) | IS_L_rev | single-ended |
| ch2 (AIN2 vs GND) | IS_R_fwd | single-ended |
| ch3 (AIN3 vs GND) | IS_R_rev | single-ended |

**ADS1115 конфиг:**
- PGA = `001b` → FSR = **±4.096V** (покрывает IS до 34.8A при RIS=1kΩ)
- Режим: single-shot (по запросу), опрос по каналам последовательно
- Скорость: 128 SPS достаточно (7.8ms/канал, 31ms на полный скан 4 каналов)
- I2C адрес: **0x48** (ADDR → GND)
- I2C шина: I2C0, GP20 (SDA) / GP21 (SCL) — уже существует для IMU

#### RP2040 Native ADC (12-bit, 0–3.3V)

| Пин | Канал | Сигнал | Источник |
|-----|-------|--------|---------|
| GP26 | ADC0 | Vbat | 3DR-style power module, voltage output |
| GP27 | ADC1 | Ibat | 3DR-style power module, current output |
| GP28 | ADC2 | свободен | — |

**3DR Power Module:**
- Voltage output: 0–3.3V linear (соответствует диапазону батареи)
- Current output: 0–3.3V linear (соответствует 0–90A, измеряет до ~60A)
- Выходы идут напрямую в RP2040 ADC (напряжение в пределах 3.3V ✓)

**Примечание:** Старый `BIBA_ADC_CHAN_LEFT_R_IS = 1U` (GP27) и `RIGHT_R_IS = 2U` (GP28) будут переназначены — GP27 теперь Ibat, GP28 свободен. Все 4 IS-пина уходят на ADS1115.

---

### 3. Датчик температуры/влажности

**Модель:** AHT30  
**I2C адрес:** 0x38  
**I2C шина:** I2C0 (GP20/GP21) — тот же bus что ADS1115 и IMU  

**Конфликтов нет:**
| Устройство | Адрес |
|------------|-------|
| IMU (BMI160 / LSM6DS3) | 0x68 / 0x6A |
| ADS1115 | 0x48 |
| AHT30 | 0x38 |

---

### 4. Телеметрия — поля для добавления

Добавить в `biba_telemetry_input_t` (`firmware/src/app/telemetry.h`):

| Поле | Тип | Описание |
|------|-----|---------|
| `vbat_mv` | uint16_t | Напряжение батареи, мВ |
| `ibat_a` | float | Ток батареи, А (с 3DR PM) |
| `temperature_c` | float | Температура, °C (AHT30) |
| `humidity_pct` | float | Влажность, % (AHT30) |

**Соотношение токов:**
- `ibat_a` ≈ `current_left_a + current_right_a` (ток электроники пренебрежимо мал)
- Это можно использовать для кросс-валидации в тестах

---

### 5. Изменения в firmware

#### target.h (RPICO_RP2040)

Старые каналы `IS_*` на native ADC убрать. Переназначить:
- `BIBA_ADC_CHAN_VBAT = 0` (GP26) — остаётся
- `BIBA_ADC_CHAN_IBAT = 1` (GP27) — **новый**
- Старые `BIBA_ADC_CHAN_LEFT_R_IS`, `LEFT_L_IS`, `RIGHT_R_IS`, `RIGHT_L_IS` — удалить или переназначить на ADS1115 каналы

#### Новый драйвер: ADS1115

Создать `firmware/src/drivers/ads1115.c/h`:
- I2C read/write через HAL
- Конфигурация PGA на ±4.096V
- Single-shot conversion per channel
- `ads1115_read_channel(ch)` → voltage_v (float)

#### Новый драйвер: AHT30

Создать `firmware/src/drivers/aht30.c/h`:
- I2C, адрес 0x38
- Запрос измерения + чтение temperature/humidity
- `aht30_read(float *temp_c, float *humidity_pct)`

#### current_sense.c

Обновить чтение IS с native ADC → ADS1115:
- `biba_hal_adc_sample(chan)` → `ads1115_read_channel(ch)`
- `current_left_a = max(IS_L_fwd_v, IS_L_rev_v) × amps_per_volt`
- `current_right_a = max(IS_R_fwd_v, IS_R_rev_v) × amps_per_volt`

#### target_config.h (RPICO_RP2040)

Добавить калибровку IS:
```c
#define BIBA_IS_AMPS_PER_VOLT   8.5f   /* kILIS=8500, RIS=1kΩ → 1V/A×8.5 */
```

Добавить калибровку 3DR PM:
```c
#define BIBA_VBAT_VOLT_MULT     xxx    /* определить из модуля */
#define BIBA_IBAT_AMPS_PER_VOLT xxx    /* определить из модуля */
```

---

### 6. Открытые вопросы (для плана)

- [ ] Конкретная модель 3DR PM — уточнить VOLT_MULT и AMPS_PER_VOLT из документации модуля
- [ ] ADS1115 HAL-слой: использовать `biba_hal_i2c_read/write` или напрямую pico-sdk?
- [ ] Частота опроса ADS1115: встроить в основной loop или отдельный таймер?

---

## Итоговая схема

```
BTS7960 ×4                    ADS1115 (0x48)
─────────────                 ─────────────────────────
IS_L_fwd ──────────────────── AIN0 (ch0)
IS_L_rev ──────────────────── AIN1 (ch1)          I2C0
IS_R_fwd ──────────────────── AIN2 (ch2)   ──────────────── RP2040
IS_R_rev ──────────────────── AIN3 (ch3)            GP20/GP21

AHT30 (0x38) ─────────────────────────────── I2C0

3DR Power Module              RP2040 Native ADC
─────────────────             ─────────────────────────
VOUT_BAT ─────────────────── GP26 (ADC0, Vbat)
VOUT_CURR ────────────────── GP27 (ADC1, Ibat)
```
