# Phase 4 Manifest: Thermal Hardening & ESC Architecture

**Phase Number:** 4  
**Title:** Thermal Hardening & ESC Architecture  
**Status:** Not planned  
**Created:** 2026-05-17  

---

## Phase Goal

Выбрать оптимальный ESC с обоснованием (BTN8982TA vs IFX007T), спроектировать теплотехническую архитектуру с активным охлаждением и подтвердить в полевых испытаниях.

**English:** Select optimal ESC with justification (BTN8982TA vs IFX007T), design a thermal architecture with active cooling, and validate through field testing.

---

## Trigger

Phase 4 is triggered after Phase 3 (Field Ready) completes and field testing confirms BTS7960 thermal limitations. Synthesis of dialogue.log community discussion identifies root causes and modern alternatives.

---

## Input Artifacts

| Artifact | Source | Purpose |
|----------|--------|---------|
| dialogue.log | `/home/ros2/Downloads/biba/artifacts/current-trace/phase-04-community-dialogue.log` | Community discussion of BTS7960 failures, BTN8982TA/IFX007T comparisons, cooling strategies |
| Arduino forum threads | Links in dialogue.log | Real-world failure modes: 14A wheelchair project, 250W gas mower, aliasing issues |
| SimpleFOC docs | Referenced in dialogue | PWM frequency optimization, thermal management patterns |
| BiBa field logs | Phase 3 outputs | Evidence of 20–30 min thermal failure window |

---

## Plan Structure

### 04-01-PLAN: Failure Analysis
**Goal:** Synthesize ≥5 real-world projects into comparative failure analysis  
**Deliverables:**
- ESC-FAILURE-ANALYSIS.md: Root causes (pulsed current > 100A, poor thermal contact, Rds(on) losses)
- Comparison table: BTS7960, BTN7970, BTN8982TA, IFX007T by specifications and failure modes
- Forum references: Arduino.ru (mower), Arduino.cc (wheelchair), RadioKot.ru (solutions)

**Success Criteria:**
- ≥5 field projects analyzed
- Common failure pattern identified (20–30 min → thermal shutdown)
- Cost vs. performance matrix created

### 04-02-PLAN: ESC Evaluation & Selection
**Goal:** Evaluate BTN8982TA and IFX007T, select for RP2040 variant  
**Deliverables:**
- ESC-EVALUATION.md: Datasheets, thermal models (Rds(on) loss calculation)
- SOURCING.md: Availability, cost in RU/SNG (Чип и Дип, TM Electronics, etc.)
- SELECTION-RATIONALE.md: Why BTN8982TA or IFX007T chosen for RP2040

**Success Criteria:**
- Thermal loss comparison @ 20A, 30A, 40A continuous load
- Cost analysis (component + integration)
- Sourcing confirmed (≥3 vendors listed)

### 04-03-PLAN: Thermal Architecture Design
**Goal:** Specify cooling strategy, PCB layout, EMC/waterproofing  
**Deliverables:**
- THERM-DESIGN.md: Cooling approach (passive radiant + active fan options)
- PCB-LAYOUT-GUIDE.md: Heatsink, isolation pad, conformal coating specs
- EMC-WATERPROOFING.md: Grommet routing, conformal spray, connector sealing
- BOM-ADDENDUM.md: Thermal components (Al heatsink, thermal compound, fan PCB assembly)

**Success Criteria:**
- Design reviewed by Infineon best practices
- EMC/waterproofing validated against field environment (dust, moisture, vibration)

### 04-04-PLAN: Prototype Validation & Hardware Matrix
**Goal:** Build prototype, run 60+ min continuous load test, publish hardware matrix  
**Deliverables:**
- VALIDATION-TEST-REPORT.md: 60+ min @ 30A load, thermal profiles (IR thermography if available)
- FIELD-TEST-NOTES.md: Extended deployment results
- HARDWARE-MATRIX.md: RP2040 × [ESC variants] × [Motor options] published to github
- RELIABILITY-DATASHEET.md: MTBF projection based on thermal/electrical design

**Success Criteria:**
- Prototype survives 60+ min continuous load without thermal shutdown
- Field deployment ≥2 hours without incident
- Hardware matrix published and linked from main README

---

## Dependencies & Ordering

**Blocking:** Phase 3 must complete (baseline thermal behavior known)  
**Parallel:** Can begin literature review while Phase 3 finalizes field data  
**Downstream:** Phase 5 (if any) uses selected ESC architecture  

---

## Estimates

| Task | Est. Effort | Owner |
|------|-------------|-------|
| 04-01 (Failure analysis) | 4–6 hours | TD (community liaison) |
| 04-02 (ESC evaluation) | 6–8 hours | МД (datasheet deep-dive) |
| 04-03 (Thermal design) | 8–10 hours | PCB/thermal specialist (outsource if needed) |
| 04-04 (Validation) | 12–16 hours | Field testing + reporting |
| **Total** | **30–40 hours** | Phase 4 team |

---

## Acceptance Criteria (UAT)

- [ ] ESC selection justified in writing with ≥3 alternatives evaluated
- [ ] Thermal design documented and peer-reviewed
- [ ] Prototype tested ≥60 min @ 30A without thermal failure
- [ ] Field deployment ≥2 hours in typical use case
- [ ] Hardware matrix published with clear BOM and assembly instructions
- [ ] Cost estimate provided (component + assembly + thermal mgmt)

---

## Next Steps

1. Clear dialogue.log context into GSD working notes
2. Run `/gsd-plan-phase 4` to create detailed task breakdown
3. Execute plans sequentially or in parallel waves (04-01 can run during Phase 3 field testing)
4. Track progress via daily commits to `.planning/phases/04-thermal-hardening/`

