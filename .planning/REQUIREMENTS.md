# Requirements: BiBa

**Defined:** 2026-05-14
**Core Value:** Робот должен ехать и слушаться пульта в любых условиях — всё остальное вторично.

## v1 Requirements

Requirements for RP2040 port milestone. Each maps to roadmap phases.

### CRSF / Radio Control

- [ ] **CRSF-01**: RP2040 принимает ELRS/CRSF пакеты по UART и декодирует каналы управления
- [ ] **CRSF-02**: Потеря CRSF-сигнала определяется в течение ≤500 мс и активирует failsafe (стоп моторов)
- [ ] **CRSF-03**: Каналы управления корректно маппируются на команды привода (дифференциальный микс)

### Motor Control

- [ ] **MOTOR-01**: RP2040 управляет двумя каналами BTS7960 (левый/правый) через hardware PWM
- [ ] **MOTOR-02**: При старте все motor-enable пины LOW до получения первой валидной CRSF-команды
- [ ] **MOTOR-03**: Плавный разгон/торможение (ramping) реализован для защиты передачи и BTS7960

### Arming & Failsafe

- [ ] **SAFE-01**: Арминг/разарм через dedicated switch на пульте работает корректно
- [ ] **SAFE-02**: После потери связи или disarm — моторы останавливаются, не зависают в состоянии
- [ ] **SAFE-03**: Deadband по нейтральному положению стиков исключает ложные движения

### IMU Stabilization

- [ ] **IMU-01**: IMU (BMI160 или LSM6DS3) инициализируется на RP2040 по I2C/SPI
- [ ] **IMU-02**: Heading-hold режим (удержание курса по гироскопу) работает на RP2040
- [ ] **IMU-03**: Gyro bias калибруется при старте (стоп > 2 сек = калибровка)
- [ ] **IMU-04**: Оси гироскопа корректно маппированы для BiBa (yaw → дифференциал колёс)

### Current Sensing

- [ ] **CURR-01**: Замеры тока с BTS7960 IS-пинов (или ADS1115) работают на RP2040
- [ ] **CURR-02**: Перегрузка по току вызывает software throttle (не жёсткий стоп)
- [ ] **CURR-03**: Показания тока логируются через UART/USB для отладки

### Trim

- [ ] **TRIM-01**: Триминг каналов (дрейф нейтрали) настраивается и сохраняется в flash
- [ ] **TRIM-02**: Сохранённые трим-значения восстанавливаются при перезагрузке

### Thermal Protection

- [ ] **THERM-01**: Программная защита: при превышении тока/температуры применяется throttle back
- [ ] **THERM-02**: Аппаратная теплоотводящая пластина под BTS7960 установлена (hardware task)

### Hardware Variant Matrix

- [ ] **VARIANT-01**: Документирована таблица вариантов: плата × тип мотора × тип драйвера × опциональные модули
- [ ] **VARIANT-02**: Каждый вариант имеет статус (ready / WIP / planned) и ссылку на target.md или ветку

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### BiBa Extended (Post-RP2040 Phase)

- **VOICE-01**: Голосовые ассеты и звуковая индикация на RP2040
- **BMS-01**: Daly BMS интеграция (BLE/UART) на RP2040
- **LED-01**: LED-матрицы (WS2812 фары/индикаторы) управляются с RP2040
- **TELEM-01**: CRSF обратная телеметрия (VBAT, ток) на пульт
- **COMP-01**: Companion mode — RP2040 как SPI-слейв для Pi Zero 2W

### ROS2 / Autonomous

- **ROS2-01**: BiBa ноды в ROS2 workspace на Pi Zero 2W
- **NAV-01**: Follow-me режим (следование за меткой)

## Out of Scope

Explicitly excluded from RP2040 port milestone.

| Feature | Reason |
|---------|--------|
| Web UI / browser telemetry | Только пульт — no network stack on RP2040 в Phase 1 |
| BMS integration (RP2040) | Python/BLE сложность, откладывается на Pi Zero 2W ветку |
| Voice assets (RP2040) | Нет достаточного RAM на Pico для audio processing |
| ODrive/VESC support (code) | Документируется в матрице, не реализуется в этой фазе |
| Follow-me / autonomous nav | За пределами RC управления |
| ROS2 integration | Отдельный milestone для Pi Zero 2W |
| Docker stack on RP2040 | Нет Linux, не применимо |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CRSF-01 | Phase 1 | Pending |
| CRSF-02 | Phase 1 | Pending |
| CRSF-03 | Phase 1 | Pending |
| MOTOR-01 | Phase 1 | Pending |
| MOTOR-02 | Phase 1 | Pending |
| MOTOR-03 | Phase 1 | Pending |
| SAFE-01 | Phase 1 | Pending |
| SAFE-02 | Phase 1 | Pending |
| SAFE-03 | Phase 1 | Pending |
| IMU-01 | Phase 2 | Pending |
| IMU-02 | Phase 2 | Pending |
| IMU-03 | Phase 2 | Pending |
| IMU-04 | Phase 2 | Pending |
| CURR-01 | Phase 2 | Pending |
| CURR-02 | Phase 2 | Pending |
| CURR-03 | Phase 2 | Pending |
| TRIM-01 | Phase 2 | Pending |
| TRIM-02 | Phase 2 | Pending |
| THERM-01 | Phase 3 | Pending |
| THERM-02 | Phase 3 | Pending |
| VARIANT-01 | Phase 3 | Pending |
| VARIANT-02 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-14*
*Last updated: 2026-05-14 after initialization*
