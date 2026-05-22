# Phase 6: IS-Signal RPM Proof-of-Concept — Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Доказать, что пульсации тока через IS-пины BTS7960 + RC-фильтр + native RP2040 ADC (DMA)
достаточны для оценки RPM мотора MY1016Z (коллекторный редукторный). Снять сырые ADC-данные
при разных duty в обоих направлениях, построить спектры FFT/ZC/autocorr и оценить линейную
зависимость пик-частоты от duty. Это PoC — не production код.

</domain>

<decisions>
## Implementation Decisions

### 1. USB CDC Command Protocol

- **D-01:** Команда захвата: `CAPTURE <FWD|REV> <duty_pct> <n_samples> <sps>`.
  Направление (FWD/REV) — обязательный параметр. Оба направления обязательны для теста.
- **D-02:** Выбор мотора (LEFT/RIGHT) — **константа в Python-скрипте**, не параметр прошивки.
  PoC тестируется на одном моторе за раз; Python знает какой.
- **D-03:** Дополнительные команды: `STOP` (нулевой duty, безопасная остановка), `PING` → `PONG`
  (проверка связи). Оба остаются из исходного плана.
- **D-04:** `CAPTURE_BOTH` (оба мотора interleaved) — **не нужен для PoC**, убрать из scope.

### 2. Motor — MY1016Z Характеристики

- **D-05:** Мотор — **коллекторный редукторный DC**, 24V, 75 RPM на выходном валу.
  IS-рябь порождается **переключением щёток на коллекторных пластинах** (commutator ripple),
  а НЕ от пар полюсов (как у BLDC). Модель: `f_ripple = N_seg × RPM_core / 60`.
- **D-06:** Передаточное число редуктора — **уточнить по даташиту до запуска захватов**.
  Нужно для оценки RPM_core и ожидаемого диапазона f_ripple. Примерный ориентир: при
  передаточном ~33:1 и 75 RPM → RPM_core ≈ 2500 → f_ripple ≈ 250–1000 Hz (зависит от N_seg).
- **D-07:** Даташит мотора: `artifacts/datasheets/` — проверить наличие, уточнить N_seg и ratio.

### 3. Параметры захвата

- **D-08:** Defaults из плана остаются в силе: 10 kSPS, 2048 отсчётов на канал (~205 мс окно).
  Nyquist = 5 kHz, что покрывает ожидаемый диапазон IS-ряби (< 1.5 kHz). RC-фильтр: f_c ≈ 3.2 kHz.
- **D-09:** Python-скрипт запускает захват для **всех duty-точек последовательно в обоих направлениях**:
  `[25, 50, 75, 100]% × {FWD, REV}` = 8 захватов на один запуск.
- **D-10:** Между захватами: задержка 500 мс (spin-up/down) — как в плане.

### 4. Критерий успеха алгоритма

- **D-11:** Цель сравнения FFT / Zero-Crossing / Autocorr: **R² > 0.9** между duty и
  пик-частотой из IS-сигнала. Этого достаточно для PoC. Более глубокий анализ
  (computational cost, robustness to noise, real-time viability) — за пределами этой фазы.
- **D-12:** Тест на синтетическом сигнале: точность ±5% (критерий из success criteria фазы).

### 5. Выход Python-скрипта

- **D-13:** **CSV** — сырые ADC отсчёты для каждого захвата (header: `duty,dir,sample_idx,adc_raw`).
  Хранить в `artifacts/is-capture/`.
- **D-14:** **PNG-графики** — спектр (FFT magnitude) для каждого duty+dir + scatter-plot
  `duty vs f_peak` (три линии: FFT/ZC/autocorr) с R²-аннотацией. Сохранять рядом с CSV.
- **D-15:** Консольный вывод при запуске: duty, направление, пойманная пик-частота, R² в конце.
  Никакого Jupyter — только стандартный Python-скрипт.

### Agent's Discretion

- Порядок волн (firmware → python) остаётся как в `06-PLAN.md`.
- Unit-тесты алгоритмов (FFT/ZC/autocorr на синтетическом сигнале) — агент пишет по своему
  усмотрению, покрывая критерий ±5%.
- Структура Python-скрипта (один файл с subcommands или два отдельных) — по усмотрению агента,
  лишь бы `--port` и `--motor {left|right}` были аргументами.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Firmware — ADC / целевая топология Phase 6
- `firmware/targets/RPICO_RP2040/target.h` — текущие ADC-defines; Task 1 переписывает их
- `firmware/targets/RPICO_RP2040/target_config.h` — калибровочные константы IS; обновить `BIBA_IS_AMPS_PER_VOLT` → 17.0f (два резистора параллельно)
- `firmware/src/drivers/voltage_sense.c` — зависит от `BIBA_ADC_CHAN_VBAT/IBAT`; потребует правки после переназначения ADC

### Firmware — аппаратные паттерны RP2040
- `firmware/src/poc/` — новая директория для PoC-кода (создать)
- `firmware/platformio.ini` — добавить env `rpico_rp2040_is_poc`; смотреть существующие env как образец

### Phase 5 Context (принятые решения ADC, обязательно прочесть)
- `.planning/phases/05-current-sensing-adc/05-CONTEXT.md` — ADC-распределение Phase 5; Phase 6 делает hardware swap IS_L/R → GP26/27, VBAT/IBAT → ADS1115 AIN0/1

### Datasheet — MY1016Z (проверить перед запуском)
- `artifacts/datasheets/` — искать MY1016Z; нужны N_seg (commutator segments) и gear ratio для оценки f_ripple

### Существующий план (уточнить после обсуждения)
- `.planning/phases/06-is-rpm-poc/06-PLAN.md` — детальный план волн 1–2; **требует правки** в Task 4:
  изменить сигнатуру `cmd_capture()` на `CAPTURE <FWD|REV> <duty> <n> <sps>`, убрать `CAPTURE_BOTH`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `firmware/src/drivers/ads1115.h/.c` — ADS1115 driver (Phase 5); VBAT/IBAT теперь через него
- `firmware/src/hal/biba_hal_rp2040.c` — `biba_hal_pwm_set_duty()` — управление PWM мотором; Task 4 PoC shell использует его напрямую
- `firmware/src/drivers/bts7960.h` — BTS7960 driver; PoC управляет L/R RPWM/LPWM через него или напрямую через HAL

### Established Patterns
- PlatformIO multi-env: смотреть `env:rpico_rp2040_standalone` как образец build_flags и src_filter
- ADC DMA capture: RP2040 `hardware/adc.h` + `hardware/dma.h` — паттерн из плана верен; не менять

### Integration Points
- PoC env (`rpico_rp2040_is_poc`) НЕ должен ломать `rpico_rp2040_standalone` build — Task 1 модифицирует `target.h` совместимо
- Success criteria требует что ОБА env собираются без ошибок после всех изменений

</code_context>

<specifics>
## Specific Ideas

- Мотор вращается В ОБА НАПРАВЛЕНИЯ в рамках одного test run — важно для валидации симметрии IS-сигнала FWD vs REV
- Пользователь указывает мотор (LEFT/RIGHT) через Python-аргумент `--motor`, не прошивку
- MY1016Z — щёточный мотор: IS-рябь от коллектора, частота растёт линейно с RPM_core.
  Если f_ripple не обнаружена при низком duty (< 20%) — это ожидаемо, не баг

</specifics>

<deferred>
## Deferred Ideas

- **CAPTURE_BOTH (оба мотора)** — упрощено до одного мотора за раз для PoC; если оба нужны — следующая фаза
- **Real-time RPM на RP2040** — производственная реализация выбранного алгоритма на embedded C — Phase 7+
- **Абсолютная калибровка RPM** (f_ripple → RPM в физических единицах) — требует N_seg и gear ratio; после Phase 6
- **SNR и computational cost анализ алгоритмов** — за пределами R²-критерия PoC; Phase 7 если нужно

</deferred>
