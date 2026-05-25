# Phase 5 Manifest: Current Sensing & ADC Architecture

**Phase Number:** 5
**Title:** Current Sensing & ADC Architecture
**Status:** Not planned
**Created:** 2026-05-19

---

## Phase Goal

Изучить схему измерения тока BTS7960 (IS-пины), принять решение по распределению ADC-ресурсов RP2040 + ADS1115 и реализовать считывание: напряжения батареи, тока батареи, тока по каждому колесу, температуры и влажности через I2C — с выводом в телеметрию.

**English:** Study BTS7960 current-sense (IS) pin topology, decide how to allocate the RP2040's 2 ADC channels + ADS1115's 4 I2C channels for battery voltage, battery current, per-wheel current, and add a temperature/humidity I2C sensor for CRSF telemetry.

---

## Hardware Context

| Resource | Count | Notes |
|----------|-------|-------|
| RP2040 ADC channels | 2 (ADC0, ADC1) | GP26, GP27 — shared with GPIO |
| ADS1115 channels | 4 (ch0–ch3) | 16-bit, I2C, addr 0x48 |
| BTS7960 IS pins | 2 (IS_R, IS_L per board) | Current mirror, ratio kILIS ≈ 8500 |
| I2C bus | 1 (shared) | ADS1115 + temp/hum sensor |
| Temp/hum sensor | TBD | SHT31 / BME280 / HDC1080 on I2C |

---

## Trigger

Phase 4 confirmed BTS7960 thermal stability with heatsink. Now we need visibility into:
- How much current each motor is actually drawing in real time
- Battery state (voltage sag, total current draw)
- Ambient temperature and humidity for field telemetry

---

## Key Questions to Answer in Planning

1. **BTS7960 IS pin study**: What is kILIS (IS current ratio)? What resistor value RS connects IS → GND to produce a measurable voltage? What is the ADC input range and filtering needed?
2. **RP2040 ADC allocation**: Which 2 signals go on the native ADC (lower latency, no I2C overhead)? Candidates: Vbat sense, Ibat sense, IS_L, IS_R
3. **ADS1115 allocation**: Which 4 signals go on ADS1115? Gain/PGA settings per channel? Differential vs single-ended?
4. **Temp/hum sensor selection**: SHT31 vs BME280 vs HDC1080 — I2C address conflict check with ADS1115 (0x48)?
5. **Telemetry mapping**: How do battery voltage, current, and temperature map to CRSF telemetry frames (Battery sensor frame, custom)?

---

## Input Artifacts

| Artifact | Source | Purpose |
|----------|--------|---------|
| BTS7960 datasheet | Infineon | IS pin specs, kILIS, RS calculation |
| ADS1115 datasheet | TI | PGA settings, I2C protocol, conversion rate |
| RP2040 datasheet | Raspberry Pi | ADC input range (0–3.3V), impedance |
| Phase 4 artifacts | 04-HARDWARE-MATRIX.md | Confirmed ESC = BTS7960 on current build |
| firmware/src/drivers/ | existing code | Current driver structure for extension |

---

## Plan Structure (to be detailed in /gsd-plan-phase 5)

### 05-01-PLAN: BTS7960 IS Pin Study
**Goal:** Document IS-pin measurement scheme: kILIS, RS value, ADC range, filtering  
**Deliverables:**
- 05-BTS7960-IS-STUDY.md: formula, RS calc, schematic snippet, example readings at 10A/20A/30A

### 05-02-PLAN: ADC Resource Allocation Decision
**Goal:** Assign all measurement channels to RP2040 ADC or ADS1115 with rationale  
**Deliverables:**
- 05-ADC-ALLOCATION.md: channel map table, PGA settings, signal conditioning (dividers, filters)
- 05-SENSOR-SELECTION.md: temp/hum sensor choice, I2C address map

### 05-03-PLAN: Firmware Implementation
**Goal:** Implement ADC reading, ADS1115 driver, temp/hum driver, unit conversion  
**Deliverables:**
- firmware/src/drivers/ads1115.c + ads1115.h
- firmware/src/drivers/temp_hum.c + temp_hum.h (or extend existing i2c layer)
- Updated current-sense path in mode_standalone.c
- Unit tests for conversion math

### 05-04-PLAN: Telemetry Integration & Validation
**Goal:** Wire sensor readings into CRSF telemetry, validate against known loads  
**Deliverables:**
- 05-TELEMETRY-MAP.md: CRSF frame assignments for voltage, current, temp
- Field validation: measured vs expected at known resistive load
- 05-VALIDATION-REPORT.md

---

## Acceptance Criteria (UAT)

- [ ] BTS7960 IS pin behavior documented: kILIS confirmed, RS value justified, ADC range within 0–3.3V
- [ ] ADC channel map finalized: all 5 signals assigned (Vbat, Ibat, Iwheel_L, Iwheel_R, temp/hum)
- [ ] ADS1115 reads correctly on RP2040 I2C — real values in A/V
- [ ] Temp/hum sensor reads on same I2C bus without address conflict
- [ ] Per-wheel current values appear in UART/USB debug stream during motor run
- [ ] Battery voltage + current appear in CRSF telemetry (visible on TX screen)
- [ ] Accuracy ≤ ±5% vs reference load at 5–30A range

---

## Dependencies

**Blocking:** Phase 4 complete ✓ (hardware confirmed)  
**Depends on:** Phase 1 complete ✓ (BTS7960 PWM control exists in firmware)  
**Downstream:** Phase 2 (Stabilization & Sensing) — current sensing feeds throttle-back logic

---

## Estimates

| Task | Est. Effort |
|------|-------------|
| 05-01 (IS pin study) | 2–3 hours |
| 05-02 (ADC allocation) | 3–4 hours |
| 05-03 (Firmware implementation) | 8–12 hours |
| 05-04 (Telemetry + validation) | 4–6 hours |
| **Total** | **17–25 hours** |
