# Phase 4: Thermal Hardening & ESC Architecture — Specification

**Created:** 2026-05-17  
**Ambiguity score:** 0.20 (gate: ≤ 0.20) ✓  
**Requirements:** 6 locked  

---

## Goal

Select an optimal ESC motor driver (BTN8982TA vs IFX007T) with quantified justification, design a production-ready thermal architecture with active and passive cooling, and validate with ≥60 minutes continuous load testing to eliminate BTS7960 thermal shutdown failures observed in Phase 3 field testing.

---

## Background

**Current state:**
- Phase 3 field testing (2026-05-09) confirmed BTS7960 thermal failures: 20–30 minutes of continuous 25A load → thermal shutdown at ~160°C, causing motor power loss
- Root cause identified: BTS7960 Rds(on) = 16 mΩ generates ~14.4W per H-bridge at 30A; Chinese modules have poor thermal contact via inadequate via-hole design
- Community analysis (dialogue.log) documents identical failure patterns in 5+ real-world projects (wheelchair, gas mower, drone ESC applications)
- Current mitigation (Phase 3): Firmware thermal-reset primitive using EN/INH lines; insufficient alone without hardware cooling

**What triggers Phase 4:**
- Phase 3 thermal protection is operational but insufficient for extended field deployments
- Alternative ESCs (BTN8982TA, IFX007T) with lower Rds(on) are available and have been analyzed in community forums
- Production roadmap requires RP2040 variant to support 30+ minutes of continuous operation without thermal intervention

---

## Requirements

### 1. ESC Failure Analysis – Community Research Synthesized

**Statement:** Analyze ≥5 real-world projects experiencing BTS7960 thermal failures and identify root causes.

- **Current:** dialogue.log contains forum discussions and references; not yet formally organized into a comparative analysis document
- **Target:** ESC-FAILURE-ANALYSIS.md documents ≥5 projects (BiBa, wheelchair, gas mower, etc.) with failure timelines, current profiles, and root cause classification
- **Acceptance:** Document lists projects by source (Arduino Forum, Arduino.ru, RadioKot.ru, SimpleFOC, BiBa team), failure timeline (20–30 min → thermal shutdown), observed current spikes (peaks >100A), and thermal profile (Rds(on) heating + switching losses + contact resistance)

### 2. BTN8982TA and IFX007T Evaluation – Specification vs. Real-World Availability

**Statement:** Evaluate BTN8982TA (drop-in replacement, 10 mΩ Rds(on)) and IFX007T (modern alternative, ~5 mΩ per FET) against project constraints (cost, availability, integration effort).

- **Current:** DIALOGUE-ANALYSIS.md contains preliminary comparison; no formal ESC-EVALUATION.md or sourcing confirmation
- **Target:** ESC-EVALUATION.md with thermal loss calculations at 20A, 30A, 40A continuous load; SOURCING.md confirming availability and cost from ≥3 vendors in RU/SNG regions; SELECTION-RATIONALE.md documenting decision (BTN8982TA for RP2040 default variant, IFX007T as premium option)
- **Acceptance:** Document shows Rds(on) loss differential (14.4W baseline vs. 9W BTN8982TA vs. 4.5W IFX007T), cost comparison ($0.50–1 BTS7960 vs. $1–2 BTN8982TA vs. $4–7 IFX007T), and confirmed availability from JLCPCB/TM Electronics/ChipandDip with lead times ≤14 days

### 3. Thermal Architecture Design – Passive + Active Cooling Specified

**Statement:** Design a production-grade cooling architecture combining passive radiant cooling, optional active fan cooling, and firmware-based current monitoring.

- **Current:** CONTEXT.md and DIALOGUE-ANALYSIS.md document community solutions (Al extrusion radiatoir, thermal compound, conformal coating, optional 40×40 mm fan); not yet formalized into design specification
- **Target:** THERM-DESIGN.md specifies cooling approach: passive baseline (Al heatsink ≥50×50×3 mm, 3–5 W/mK thermal compound, conformal acrylic coating); active option (12V/5V fan header, GPIO-controlled trigger at >80°C), and isolation pad (thermally conductive, electrically insulating). PCB-LAYOUT-GUIDE.md documents thermal pad placement, via array routing, and conformal spray masking. EMC-WATERPROOFING.md specifies grommet sealing, connector protection, and moisture/dust resistance for field deployment. BOM-ADDENDUM.md lists thermal components (Al extrusion cost $2–3, thermal compound $0.50–1, optional fan $3–8)
- **Acceptance:** Design reviewed for thermal resistance path (goal: <0.3 K/W junction-to-case with heatsink), conformal coating applied per IPC-CC-830, and BOM validated for cost adder ≤$5 per unit

### 4. Firmware Current Monitoring – Predictive Throttle-Back

**Statement:** Implement firmware-based current sense reading (via IS pin) with automatic throttle reduction before thermal shutdown occurs.

- **Current:** Phase 3 firmware has thermal-reset primitive (EN/INH pulse); no current-sense ADC integration or throttle-back logic
- **Target:** `firmware/src/drivers/bts7960.c` adds `uint16_t biba_bts7960_get_current_ma(void)` reading IS pin via ADC; `firmware/src/modes/mode_standalone.c` monitors current and reduces PWM duty to 50% if current exceeds threshold (goal: ≤35A for 250W motors on 24V)
- **Acceptance:** ADC converts 0–3.3V (IS pin) to 0–100A range; firmware logs current spike events; 60+ min load test shows throttle-back engaging before thermal latch (i.e., current capped <35A instead of thermal shutdown at 45A+)

### 5. Prototype Validation – 60+ Minute Continuous Load Test

**Statement:** Build a prototype with selected ESC, active/passive cooling, and firmware monitoring; validate with continuous load test ≥60 minutes at 30A without thermal shutdown.

- **Current:** Phase 3 completed 30-min field test protocol; BTS7960 reached thermal shutdown
- **Target:** 04-04-PLAN produces VALIDATION-TEST-REPORT.md documenting 60+ min continuous load @ 30A with junction temperature monitoring (via IR thermography or thermal model); steady-state thermal profile <130°C; no thermal shutdown events; motors remain responsive throughout
- **Acceptance:** Test report includes timestamp log (every 5 min: load, current, temperature estimate, motor response); proof that firmware throttle-back engaged if current approached 35A; photographic evidence of hardware setup (heatsink, thermal paste, cooling solution)

### 6. Hardware Matrix – Public Documentation of ESC × RP2040 × Motor Variants

**Statement:** Publish a compatibility matrix documenting all validated ESC/RP2040/motor combinations on github, with sourcing links and build status.

- **Current:** README.md mentions RP2040 variant; no formal HARDWARE-MATRIX.md
- **Target:** HARDWARE-MATRIX.md published to github main branch, linked from project README. Matrix rows: [ESC variant] × columns: [RP2040 config, motor type, current limit, cost adder, status]. Rows: BTN8982TA (default, active/passive cooling, 30A, $5 adder, ready), IFX007T (premium, custom PCB required, 30A, $10 adder, planned)
- **Acceptance:** Matrix is public, lists bill of materials per variant, thermal management approach per variant, and sourcing links for all components (IC, radiatoir, thermal compound, fan if applicable)

---

## Boundaries

**In scope — Phase 4 produces:**
- ESC-FAILURE-ANALYSIS.md: ≥5 project case studies
- ESC-EVALUATION.md + SOURCING.md + SELECTION-RATIONALE.md: Comparative analysis, cost, availability, decision rationale
- THERM-DESIGN.md + PCB-LAYOUT-GUIDE.md + EMC-WATERPROOFING.md + BOM-ADDENDUM.md: Complete thermal architecture and deployment specs
- Firmware current-sense integration (IS pin ADC + throttle-back logic)
- 60+ min prototype validation test with thermal monitoring
- HARDWARE-MATRIX.md: Public documentation of all validated variants

**Out of scope — Phase 4 does NOT:**
- Design new PCB layouts (PCB guidelines provided; actual PCB design deferred to Phase 5 or variant-specific work). **Exception:** IFX007T premium variant may require custom PCB; Phase 4 specifies requirements, Phase 5+ executes
- Implement BMS integration on RP2040 (remains on Pi Zero 2W reference platform)
- Voice/audio enhancements for RP2040 (memory constraints, deferred to future)
- ROS2 or autonomous navigation (radio control only, Phase 1 scope)
- Bulk production assembly (design and validation only; manufacturing escalation to separate workflow)

---

## Acceptance Criteria

Phase 4 is complete when ALL of the following are TRUE:

- [ ] **Analysis:** ESC-FAILURE-ANALYSIS.md documents ≥5 projects with root cause classification, current spike evidence (>100A), and thermal failure timeline (20–30 min)
- [ ] **Selection:** SELECTION-RATIONALE.md specifies chosen ESC (BTN8982TA recommended for RP2040) with cost/availability/integration justification; alternative (IFX007T) documented as premium option
- [ ] **Thermal Design:** THERM-DESIGN.md specifies passive (Al radiatoir, 50×50×3 mm, ≥3 W/mK compound, conformal coat) + active (optional fan, GPIO trigger) cooling; thermal resistance <0.3 K/W calculated; BOM adder ≤$5
- [ ] **Firmware:** `biba_bts7960_get_current_ma()` reads IS pin and returns 0–100A; throttle-back engages at 35A threshold; current spikes logged to UART
- [ ] **Validation:** 60+ min continuous load test @ 30A completes without thermal shutdown; junction temperature <130°C steady-state; throttle-back events (if any) logged and explained
- [ ] **Hardware Matrix:** HARDWARE-MATRIX.md published to github, linked from README.md, lists ESC × RP2040 × motor variants with status (ready/planned) and BOM per variant

---

## Ambiguity Report

**Final ambiguity: 0.20** (gate threshold met)

| Dimension | Score | Status | Note |
|-----------|-------|--------|------|
| Goal Clarity | 0.85 | ✓ | ESC selection criteria clear (cost/perf), thermal architecture approach specified, validation method explicit |
| Boundary Clarity | 0.75 | ✓ | In-scope vs. out-of-scope items explicitly listed; PCB design deferral noted |
| Constraint Clarity | 0.80 | ✓ | Load test: 60+ min @ 30A; temp: <130°C; current limit: 35A; cost: ≤$5 adder; availability: confirmed 14-day lead times |
| Acceptance Criteria | 0.80 | ✓ | All 6 requirements have pass/fail acceptance criteria; thermal shutdown absence is falsifiable |

**Confidence:** High. Phase 3 field data and dialogue.log community analysis provide solid grounding. All 4 ambiguity dimensions meet minimum thresholds.

---

## Traceability to Roadmap

| Roadmap Item | SPEC Requirement | Plan |
|--------------|------------------|------|
| "Анализ ≥5 реальных проектов" | Req 1 | 04-01-PLAN |
| "BTN8982TA и IFX007T оценены" | Req 2 | 04-02-PLAN |
| "Спроектирована теплотехническая архитектура" | Req 3 | 04-03-PLAN |
| "Прототип пройден ≥60 мин нагрузки" | Req 5 | 04-04-PLAN |
| "Матрица совместимости ESC × RP2040 × Motor" | Req 6 | 04-04-PLAN |
| (Firmware current monitoring inferred) | Req 4 | 04-04-PLAN |

---

## Related Artifacts

- [CONTEXT.md](./CONTEXT.md) — Phase overview and source materials
- [DIALOGUE-ANALYSIS.md](./DIALOGUE-ANALYSIS.md) — Technical analysis of ESC failures, BTN8982TA vs IFX007T comparison, community solutions
- [PHASE-MANIFEST.md](./PHASE-MANIFEST.md) — 4-plan breakdown and task estimates
- [field-validation.md](../../docs/field-validation.md) — Phase 3 thermal testing protocol (reference for Phase 4 validation)

---

*Spec created 2026-05-17 via /gsd-spec-phase 4 --auto*  
*All dimensions pass. Ready for /gsd-discuss-phase 4*
