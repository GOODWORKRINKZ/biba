# Roadmap: BiBa

**Milestone:** RP2040 Port
**Created:** 2026-05-14
**Phases:** 4
**Requirements mapped:** 22/22 ✓

---

## Phases

- [x] **Phase 1: Core Drive** — CRSF + BTS7960 PWM + Arming/Failsafe (completed 2026-05-19)
- [ ] **Phase 2: Stabilization & Sensing** — IMU heading-hold + Current sensing + Trim persistence
- [x] **Phase 3: Field Ready** — Thermal protection + Hardware variant matrix + field validation (completed 2026-05-19)
- [x] **Phase 4: Thermal Hardening & ESC Architecture** — BTN8982TA/IFX007T evaluation + cooling design + production validation (completed 2026-05-19)
- [x] **Phase 5: Current Sensing & ADC Architecture** — BTS7960 IS-pins study + ADS1115 I2C ADC allocation + battery/per-wheel current + temp/hum telemetry (completed 2026-05-22)
- [x] **Phase 6: IS-Signal RPM Proof-of-Concept** — RC-filtered IS-pin ADC capture + FFT/ZC/autocorr algorithm comparison + Python analysis scripts (completed 2026-05-23)
- [x] **Phase 7: IS-RPM Integration** — A2 Sub-window ZC detector + FF+PI RPM loop ported to main firmware (both wheels), wheel_rpm_hz in biba_proto, m/s estimation, calibration workflow (completed 2026-05-25)
- [ ] **Phase 8: Session Flight Recorder** — LittleFS black box on RP2040 flash, CH8 trigger + SOS tone, binary .bbd session files, Python download script via USB CDC

---

## Phase Details

### Phase 1: Core Drive
**Goal**: RP2040 принимает ELRS/CRSF и уверенно едет — оба мотора отвечают на команды пульта с надёжным failsafe
**Depends on**: Nothing (first phase)
**Requirements**: CRSF-01, CRSF-02, CRSF-03, MOTOR-01, MOTOR-02, MOTOR-03, SAFE-01, SAFE-02, SAFE-03
**Success Criteria** (what must be TRUE):
  1. Сигнал от ELRS пульта управляет обоими моторами через BTS7960 в дифференциальном режиме — робот физически едет
  2. При выключении пульта или потере сигнала моторы останавливаются в течение ≤500 мс и не зависают в движущемся состоянии
  3. Переключатель арминга (CH5) включает и выключает движение — разарм гарантирует нулевой PWM и EN LOW
  4. При нейтральном положении стиков ложного движения нет (мёртвая зона работает)
  5. При старте моторы не крутятся до получения первой валидной CRSF-команды (безопасная инициализация)
**Plans**: 5 plans

Plans:
- [ ] 01-01-PLAN.md — SpeedRamp C port (ramp.h + ramp.c + biba_config.h constants)
- [ ] 01-02-PLAN.md — SSR HAL extension (target.h + biba_hal.h + biba_hal.c + biba_hal_rp2040.c)
- [ ] 01-03-PLAN.md — SpeedRamp Unity TDD tests (test_ramp/test_main.c, 8 cases)
- [ ] 01-04-PLAN.md — Wire ramp + SSR into mode_standalone.c
- [ ] 01-05-PLAN.md — Build + full native_test verification + human smoke test

---

### Phase 2: Stabilization & Sensing
**Goal**: Робот стабилизируется по гироскопу, измеряет ток, запоминает трим между перезагрузками
**Depends on**: Phase 1
**Requirements**: IMU-01, IMU-02, IMU-03, IMU-04, CURR-01, CURR-02, CURR-03, TRIM-01, TRIM-02
**Success Criteria** (what must be TRUE):
  1. Heading-hold удерживает курс при боковом толчке — RP2040 корректирует дифференциал колёс автоматически
  2. Гироскоп калибруется при старте (стоп ≥2 сек) — дрейф нейтрали не накапливается при прямолинейном движении
  3. Превышение порога тока снижает тягу плавно (throttle back), мотор продолжает работать — жёсткого стопа нет
  4. Трим-значения сохраняются во flash и восстанавливаются после перезагрузки без повторной настройки
  5. Показания тока видны в UART/USB лог-потоке при подключённом кабеле отладки
**Plans**: TBD

---

### Phase 3: Field Ready
**Goal**: Защита от перегрева, задокументированные варианты железа, пройденный полевой тест
**Depends on**: Phase 2
**Requirements**: THERM-01, THERM-02, VARIANT-01, VARIANT-02
**Success Criteria** (what must be TRUE):
  1. После ≥30 мин интенсивной езды BTS7960 не уходит в тепловой отказ — аппаратный теплоотвод подтверждён в поле
  2. При превышении тока (программный порог) тяга снижается автоматически — аппаратных повреждений ESC не происходит
  3. Матрица вариантов охватывает все три платформы (Pi Zero 2W, RP2040, STM32F103) с актуальными статусами (ready / WIP / planned)
  4. Каждый реализованный вариант имеет target.md или ссылку на ветку для воспроизводимой сборки
**Plans**: 3 plans

Plans:
- [x] 03-01-PLAN.md — Implement BTS7960 EN/INH thermal reset in firmware with 100 us pulse and regression tests
- [x] 03-02-PLAN.md — Publish canonical hardware variant matrix and field-validation evidence protocol
- [x] 03-03-PLAN.md — Run automated + field validation and produce requirement-traceable UAT report

---

### Phase 4: Thermal Hardening & ESC Architecture
**Goal**: Выбрать оптимальный ESC с обоснованием (BTN8982TA vs IFX007T), спроектировать теплотехническую архитектуру с активным охлаждением и подтвердить в полевых испытаниях
**Depends on**: Phase 3
**Requirements**: THERM-03, THERM-04, ESC-ARCH-01, ESC-ARCH-02
**Success Criteria** (what must be TRUE):
  1. Проведён анализ ≥5 реальных проектов (BiBa, газонокосилка, коляска) с BTS7960 — выявлены общие причины отказов (пусковой ток >100A, перегрев после 20–30 мин езды)
  2. BTN8982TA и IFX007T оценены по спецификациям и доступности — выбран драйвер для RP2040 варианта с обоснованием (Rds(on), cost, availability, thermal limit)
  3. Спроектирована теплотехническая архитектура: радиатор, гидроизоляция, вентилятор, EMC-фильтрация — документирована в THERM-DESIGN.md
  4. Прототип с выбранным ESC пройден ≥60 мин безпрерывной нагрузки (симуляция полевого теста) без теплового отказа
  5. Матрица совместимости ESC × RP2040 × Motor опубликована на github в HARDWARE-MATRIX.md
**Plans**: 4 plans

Plans:
- [x] 04-01-PLAN.md — Synthesize dialogue.log + forum threads (Arduino.ru, Arduino.cc, radiokot.ru) into comparative ESC failure analysis
- [x] 04-02-PLAN.md — Evaluate BTN8982TA + IFX007T: datasheets, sourcing, thermal simulation (SPICE/FEA if available)
- [x] 04-03-PLAN.md — Design thermal architecture: cooling strategy selection, PCB layout, EMC/waterproofing spec
- [x] 04-04-PLAN.md — Prototype validation: 60+ min continuous load test + field validation + HARDWARE-MATRIX publication

---

### Phase 5: Current Sensing & ADC Architecture
**Goal**: Измерять ток колёс и батареи через BTS7960 IS-пины и ADS1115 I2C ADC
**Depends on**: Phase 4
**Requirements**: CURR-01, CURR-02, CURR-03
**Success Criteria** (what must be TRUE):
  1. Ток каждого колеса читается через IS-пины BTS7960 → ADS1115 и виден в телеметрии
  2. Ток батареи (IBAT) и напряжение (VBAT) измеряются через ADS1115 AIN0/AIN1
  3. Температура и влажность (AHT30) читаются и передаются в STM32 proto
  4. Все поля телеметрии покрыты unit-тестами
**Plans**: 1 plan

Plans:
- [x] 05-PLAN.md — ADS1115+AHT30 drivers, ADC remap, telemetry proto, tests

---

### Phase 6: IS-Signal RPM Proof-of-Concept
**Goal**: Доказать что IS-пульсации через RC-фильтр пригодны для оценки RPM мотора MY1016Z
**Depends on**: Phase 5
**Requirements**: RPM-POC-01
**Success Criteria** (what must be TRUE):
  1. DMA-захват IS-сигнала при разных duty дампит данные через USB CDC
  2. FFT, zero-crossing и autocorr алгоритмы оценивают частоту ±5% на синтетическом сигнале
  3. Спектральный пик из IS-сигнала линейно зависит от duty (R² > 0.9 в поле)
  4. Оба firmware env (`rpico_rp2040_standalone`, `rpico_rp2040_is_poc`) собираются без ошибок
**Plans**: 1 plan

Plans:
- [x] 06-PLAN.md — ADC remap, DMA capture driver, USB shell, Python capture+analyse scripts, unit tests

---

### Phase 7: IS-RPM Integration
**Goal**: Перенести A2 Sub-window ZC-детектор и FF+PI контур RPM из PoC в основную прошивку. Оба мотора управляются по замкнутому контуру скорости на RP2040, wheel_rpm_hz уходит в biba_proto телеметрию.
**Depends on**: Phase 6
**Requirements**: RPM-INT-01, RPM-INT-02, RPM-INT-03
**Success Criteria** (what must be TRUE):
  1. A2 Schmitt ZC-детектор работает для IS_LEFT и IS_RIGHT в `rpico_rp2040_standalone` — оба канала валидны при 25–100% duty
  2. FF+PI loop на RP2040 удерживает target RPM ±10% SS error при 200–900 Hz (все 4 duty-точки)
  3. Gain scheduling снижает OS при target < 200 Hz до < 30%
  4. `wheel_rpm_left_hz10` и `wheel_rpm_right_hz10` появляются в biba_proto телеметрии и декодируются в Python
  5. Pi Python пересчитывает rpm_hz → m/s с WHEEL_RADIUS_M + GEAR_RATIO из config
  6. Калибровочный скрипт `scripts/is_rpm_calibrate.py` производит K-коэффициент с R² > 0.95
  7. Unity C unit-тесты покрывают ZC-детектор и PI-модуль
**Plans**: 5 plans

Plans:
- [x] 07-01-PLAN.md — ZC Detector C module (zc_detector.h/c) + async ADC capture (adc_capture.h/c moved + extended) + Unity test_zc_detector
- [x] 07-02-PLAN.md — Proto extension (biba_proto.h + telemetry.h/c) + Python decoder (protocol.py + config.py + main.py) + test_stm32_link_protocol
- [x] 07-03-PLAN.md — CALRUN command in PoC firmware + scripts/is_rpm_calibrate.py calibration script
- [x] 07-04-PLAN.md — RPM PI C module (rpm_pi.h/c) + Unity test_rpm_pi (wave 2, depends on 07-01)
- [x] 07-05-PLAN.md — Wire PI into mode_standalone.c (replaces ramp), DMA IRQ state machine, build + smoke test (wave 3)

---

### Phase 8: Session Flight Recorder
**Goal**: Чёрный ящик на RP2040 — запись телеметрии сессии в LittleFS flash + чтение через USB CDC Python-скрипт
**Depends on**: Phase 7
**Requirements**: BB-01, BB-02, BB-03
**Success Criteria** (what must be TRUE):
  1. CH8 HIGH — биба играет SOS-мелодию, режим записи активирован
  2. При арминге с активным BB — открывается session_NNNN.bbd, запись с BIBA_BLACKBOX_RATE_HZ
  3. Файл содержит все поля: timestamp, throttle, rudder, duty L/R, rpm L/R, active_blocks, mean_is, latch_resets, vbat, PI state
  4. При полном flash: звук ошибки при первом CH8; второй CH8 — удаляет старейшую сессию
  5. `python3 scripts/biba_blackbox_download.py` скачивает файлы и конвертирует в CSV без ручных команд
**Plans**: TBD

Features deferred beyond current milestone (v2+):

| Feature | Rationale |
|---------|-----------|
| VOICE-01: Голосовые ассеты на RP2040 | Недостаточно RAM на Pico для audio processing |
| BMS-01: Daly BMS интеграция на RP2040 | Python/BLE сложность, остаётся на Pi Zero 2W |
| LED-01: WS2812 LED-матрицы | Следующая аппаратная фаза |
| TELEM-01: CRSF обратная телеметрия | Следующая функциональная фаза |
| COMP-01: Companion mode (SPI slave) | Только после standalone field-validated |
| ROS2-01: BiBa ноды в ROS2 | Отдельный milestone на Pi Zero 2W |
| NAV-01: Follow-me режим | За пределами RC управления |

### Phase 5: Current Sensing & ADC Architecture
**Goal**: Понять схему измерения тока в BTS7960 (IS-пины), принять решение по распределению АЦП ресурсов RP2040 (2 канала) и ADS1115 (4 канала по I2C) для мониторинга: напряжения батареи, тока батареи, тока по каждому колесу, а также подключить датчик температуры/влажности по I2C для телеметрии
**Depends on**: Phase 4
**Requirements**: ADC-01, ADC-02, ADC-03, ADC-04, TELEM-02
**Success Criteria** (what must be TRUE):
  1. BTS7960 IS-пины изучены: известен масштабный коэффициент (kILIS), допустимый диапазон входного напряжения АЦП, схема включения резистора IS → GND
  2. Принята схема распределения каналов: RP2040 ADC0/ADC1 + ADS1115 ch0–ch3 → назначены сигналы (Vbat, Ibat, Iwheel_L, Iwheel_R, temp/hum)
  3. Код чтения ADS1115 по I2C работает на RP2040, возвращает актуальные значения тока/напряжения в физических единицах (А, В)
  4. Датчик температуры/влажности опрашивается по тому же I2C шине и значения уходят в CRSF телеметрию
  5. Измерения тока колёс сверены с нагрузочным тестом — погрешность не хуже ±5% при токах 5–30 A
**Plans**: TBD

Plans:

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Drive | 5/5 | complete | 2026-05-19 |
| 2. Stabilization & Sensing | 0/TBD | not started | - |
| 3. Field Ready | 3/3 | complete | 2026-05-19 |
| 4. Thermal Hardening | 4/4 | complete (UAT ✓) | 2026-05-19 |
| 5. Current Sensing & ADC | 0/TBD | not started | - |
| 6. IS-Signal RPM PoC | 1/1 | complete | 2026-05-23 |
| 7. IS-RPM Integration | 0/TBD | not started | - |
