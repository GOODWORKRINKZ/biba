# Phase 06: IS-Signal RPM PoC — Findings Log

**Период исследований:** 2026-05-22 — 2026-05-23  
**Статус:** COMPLETE

---

## 1. Характеристика IS-сигнала

**Метод:** DMA-захват IS_LEFT (GP26) через RC-фильтр 1kΩ‖1kΩ + 0.1µF (f_c ≈ 3.2 kHz)  
**Параметры:** 1024 сэмпла @ 10 kSPS = 102.4 мс окно, Nyquist = 5 kHz

Линейная зависимость частоты рябы от duty подтверждена:

| duty % | f_peak Hz | f_peak Hz (REV) |
|--------|-----------|-----------------|
| 25     | ~178      | ~178            |
| 50     | ~432      | ~432            |
| 75     | ~686      | ~686            |
| 100    | ~940      | ~940            |

**Калиброванная модель:**
```
f_hz = K × duty_pct − dead_zone
K        = 10.13 Hz/%
dead_zone = 74.6 Hz
R²        > 0.95  (оба направления)
```

**Вывод:** IS-сигнал пригоден для RPM estimation. Ключевой PoC-критерий (R² > 0.9) выполнен.

---

## 2. Сравнение алгоритмов частотной оценки

| Алгоритм | Точность (синтетика) | Точность (реальный сигнал) | Устойчивость к шуму |
|----------|---------------------|--------------------------|---------------------|
| FFT peak | ±5% (50–1500 Hz) | ±5% | Средняя (утечка при DC) |
| Autocorrelation | ±5% | ±5% | Средняя (ложные пики) |
| Zero-Crossing (простой) | ±5% | Нестабилен при зашумлении | Слабая |
| **A2 Sub-window Schmitt ZC** | **±5%** | **Лучший** | **Высокая** |

**Выбранный алгоритм: A2 Sub-window Schmitt ZC detector**

Параметры:
- `ZC_SUBWIN_K = 8` блоков × 128 сэмплов = 1024 общих сэмплов
- Локальный min/max/гистерезис вычисляется per-блок
- Требует ≥ 2 активных блока (нет сигнала = 0 Hz)
- Скользящий EMA-фильтр: α = 0.7

---

## 3. PI-регулятор скорости

### Архитектура замкнутого контура

```
setpoint_hz → [FF] + [PI] → duty [-1…1] → motor → meas_hz (IS ZC)
```

**Feed-Forward:**
```
ff_duty = direction × (target_mag + 74.6) / (10.13 × 100)
```

**PI:**
```
Kp = 0.002  (duty/Hz ошибки)
Ki = 0.010  (duty/Hz·цикл; цикл ≈ 104 мс)
EMA alpha = 0.7  (фильтрация ZC-измерений)
```

**Дополнительные механизмы:**
- Stiction floor: 20% от FF-duty при работе в deadband
- Integral clamp: ±0.03/Ki симметрично
- Transient blanking: при |Δduty| > 0.08 → пропуск 512 сэмплов; > 0.03 → 256 сэмплов
- На смене направления: integral=0, meas_ema=0, duty=0, мотор выключен

**Валидность ZC-измерений:**
- `ZC_MIN_VALID_HZ = 80` — ниже этого = ноль
- `ZC_MAX_VALID_HZ = target × 2.5 + 300` — выброс = игнорировать

---

## 4. Результаты: Step Response

### RPMRUN (статические ступеньки)

| Target Hz | Rise ms | Settle ms | Overshoot % | SS err Hz |
|-----------|---------|-----------|-------------|-----------|
| 200       | 209     | 7923      | 49          | +5.4      |
| 250       | 209     | 11875     | 22          | +5.0      |
| 400       | 209     | 6775      | 8           | +0.4      |

**Наблюдение:** Большой перерегулирование при малых RPM — FF недокалиброван для нижней части диапазона (линейная модель неточна). Интеграл успевает нарасти до того как система войдёт в диапазон. Для продакшн-версии — gain scheduling или кусочно-линейный FF.

### RPMTRACK TRAP (динамические переходы, bidirectional)

Извлечено 44 псевдо-ступеньки из 0 → ±300 Hz через `is_trap_step_extractor.py`.

| Направление | Rise ms | Settle ms | Overshoot % | SS err % |
|-------------|---------|-----------|-------------|----------|
| Forward (+) | ~400    | ~1140     | 7.0         | +0.6     |
| Reverse (−) | ~400    | ~1770     | 7.9         | −2.0     |

**Наблюдение:** Несимметрия settle Forward/Reverse — ROC кривой восстановления после реверса чуть медленнее из-за того что integral и EMA сбрасываются на ZC, а накопление с нуля занимает доп. время.

---

## 5. Firmware: структура команд

| Команда | Описание |
|---------|----------|
| `PING` | → `PONG` |
| `STOP` | Мотор в 0, сброс state |
| `CAPTURE <FWD\|REV> <duty%> <n> <sps>` | DMA захват IS-сигнала |
| `STEPRUN <duty_from> <duty_to> <pre_win> <post_win> <kp_m> <ki_m> <stiction> <ff_s> <ff_d>` | PI step response |
| `SWEEP <duty_min> <duty_max> <duty_step> <settle_ms>` | Sweep duty, FFT каждую точку |
| `SWEEPRAW <duty_min> <duty_max> <duty_step> <settle_ms>` | Sweep + сырые ZC данные |
| `RPMTRACK <shape> <base_hz> <amp_hz> <p_start> <p_end> <dur_ms> <kp_m> <ki_m> <stiction> <ff_s_x100> <ff_d_x10>` | Closed-loop tracking (SIN/TRAP) |

**Wire protocol масштабирование:**
- kp/ki умножаются × 1,000,000 для передачи через USB (float → int)
- ff_slope × 100, ff_dead × 10

---

## 6. Python toolchain

| Скрипт | Назначение |
|--------|-----------|
| `scripts/is_poc_capture.py` | Оркестрирует 8 CAPTURE, сохраняет CSV + PNG |
| `scripts/is_poc_analyse.py` | FFT/ZC/autocorr оценщики + scatter R² |
| `scripts/is_poc_step.py` | Запуск STEPRUN, plot step response |
| `scripts/is_poc_rpmtrack.py` | Запуск RPMTRACK (SIN/TRAP), 4-панельный plot |
| `scripts/is_step_response_analysis.py` | Per-subplot step analysis из RPMRUN CSV |
| `scripts/is_trap_step_extractor.py` | Псевдо-ступеньки из TRAP CSV, mean±std |

---

## 7. Архитектурные выводы для Phase 07 (интеграция)

1. **Алгоритм ZC** — переносить A2 Sub-window Schmitt. FFT/autocorr на embedded слишком дороги.
2. **FF модель** — добавить dead-zone коррекцию. Текущий линейный fit даёт ±30% ошибку при duty < 25%.
3. **Gain scheduling** — Ki следует снижать при target < 200 Hz во избежание overshooting.
4. **DMA окно** — 1024 сэмплов @ 10 kSPS = 100 мс цикл. Достаточно для 10 Hz loop bandwidth.
5. **Bidirectional** — native HAL `biba_hal_motor_pwm_left(float duty)` поддерживает [-1, 1] напрямую. Не нужно дополнительного слоя абстракции.
6. **STM32-link** — ZC-результат передавать как RPM поле в существующий proto. Добавить поле `wheel_rpm_hz` × 10 (fixed-point int16).

---

## 8. Что не вошло в PoC (деферировано)

- Абсолютная калибровка RPM (нужен N_seg мотора — неизвестен без даташита)
- Real-time ZC на RP2040 без DMA burst (непрерывный streaming)
- SNR-анализ и computational cost алгоритмов
- Оба мотора одновременно (CAPTURE_BOTH)
- Gain scheduling для малых RPM
