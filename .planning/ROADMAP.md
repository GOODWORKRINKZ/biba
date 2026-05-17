# Roadmap: BiBa

**Milestone:** RP2040 Port
**Created:** 2026-05-14
**Phases:** 4
**Requirements mapped:** 22/22 ✓

---

## Phases

- [ ] **Phase 1: Core Drive** — CRSF + BTS7960 PWM + Arming/Failsafe
- [ ] **Phase 2: Stabilization & Sensing** — IMU heading-hold + Current sensing + Trim persistence
- [ ] **Phase 3: Field Ready** — Thermal protection + Hardware variant matrix + field validation
- [ ] **Phase 4: Thermal Hardening & ESC Architecture** — BTN8982TA/IFX007T evaluation + cooling design + production validation

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
# Phase 4: Thermal Hardening & ESC Architecture
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
- [ ] 04-01-PLAN.md — Synthesize dialogue.log + forum threads (Arduino.ru, Arduino.cc, radiokot.ru) into comparative ESC failure analysis
- [ ] 04-02-PLAN.md — Evaluate BTN8982TA + IFX007T: datasheets, sourcing, thermal simulation (SPICE/FEA if available)
- [ ] 04-03-PLAN.md — Design thermal architecture: cooling strategy selection, PCB layout, EMC/waterproofing spec
- [ ] 04-04-PLAN.md — Prototype validation: 60+ min continuous load test + field validation + HARDWARE-MATRIX publication

---

## Backlog

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

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Drive | 0/? | Not started | - |
| 2. Stabilization & Sensing | 0/? | Not started | - |
| 3. Field Ready | 0/? | Not started | - |
