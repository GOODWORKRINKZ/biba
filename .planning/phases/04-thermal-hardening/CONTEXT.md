# Phase 4: Thermal Hardening & ESC Architecture

**Created:** 2026-05-17  
**Updated:** 2026-05-17 (discuss-phase context update)  
**Status:** Context refined — ready for research & planning  

---

## Goal

Optimize BTS7960 thermal performance through hardware (heatsink + conformal coating) and firmware (5 kHz PWM) to sustain 60+ minutes continuous operation at ≤120°C junction temperature. If BTS7960 optimization insufficient, evaluate BTN8982TA/IFX007T alternatives and explore custom high-current driver options (200A+ capable).

---

## Overview

This phase synthesizes field experience and community knowledge (BiBa, Arduino forums, robotics projects) to:
1. Understand root causes of ESC (BTS7960) thermal failures
2. Optimize existing BTS7960 + quantify performance ceiling
3. If needed, evaluate modern alternatives (BTN8982TA, IFX007T)
4. Validate through 60+ min load testing and field deployment
5. Document findings for community knowledge

---

## Key Decisions Captured

### 1. Strategy: Optimize Existing BTS7960 First

**Decision:** Phase 4 focuses on optimizing the existing BTS7960 with:
- **PWM reduction:** 20 kHz → 5 kHz (reduces switching losses per SimpleFOC findings)
- **Hardware cooling:** Mount BLA178-1 radiatior (33×100×100 mm) on ESC housing
- **Thermal compound:** 3–5 W/mK between chip and heatsink
- **Conformal coating:** Acrylic spray for moisture/dust protection

**Rationale:** Community data (dialogue.log + forums) shows BTS7960 failures primarily due to poor thermal contact on Chinese modules, not inherent chip limitation. Proper heatsinking + lower PWM can extend operation from 20 min → 40+ min. **Test this before switching chips.**

**Target:** Achieve <120°C steady-state junction temperature for 60+ min @ 30A continuous load.

### 2. Validation Temperature Target: <120°C (Conservative)

**Decision:** Phase 4 success threshold is <120°C steady-state, not the SPEC's <130°C.

**Rationale:** Provides margin for field variations (ambient >25°C, dust blockage, high-duty cycles). If BTS7960 + heatsink + 5 kHz PWM cannot reach <120°C @ 60 min, hardware upgrade (new ESC chip) is justified.

### 3. Fallback Strategy: BTS7960 Optimization → BTN8982TA

**Decision:** If Phase 4 testing shows BTS7960 cannot sustain <120°C, transition plan is:
1. Source BTN8982TA evaluation boards (10 mΩ Rds(on) vs 16 mΩ, same footprint)
2. Run same 60 min test with BTN8982TA + same heatsink
3. Document performance delta and cost/availability trade-off
4. **If still insufficient:** Explore custom ESC driver research (user interest in 200A+ capable drivers without thermal issues)

**Note:** IFX007T remains a future premium option (separate PCB design required, out of scope for Phase 4 unless BTN8982TA also fails).

### 4. Startup Current Measurement: Pragmatic Approach

**Decision:** For Phase 4, use literature estimate (5× nominal = 5A × 5 = 25A startup peak for 250W motor on 24V).

**Rationale:** Oscilloscope + shunt measurement adds complexity; user prefers field validation under actual load. Phase 4 can collect empirical data via IS pin feedback (firmware logs current spikes during 60 min test).

**Note:** High-frequency capture (oscilloscope) can be deferred to Phase 5 optimization if needed.

### 5. Measurement Approach: IS Pin ADC Feedback + Firmware Logging

**Decision:** Use BTS7960's IS (Current Sense) pin connected to RP2040 ADC:
- Firmware reads IS pin during 60 min test
- Logs current spikes, steady-state current, and temperature correlations
- Provides empirical startup current profile (peaks captured post-facto from logs)

**Benefit:** No external test equipment needed; integrates current monitoring for future throttle-back firmware feature.

---

## Source Materials

- [dialogue.log](../../../artifacts/current-trace/phase-04-community-dialogue.log) — Community discussion of BTS7960 thermal issues, motor driver comparisons, and solutions (user's primary reference)
- DIALOGUE-ANALYSIS.md (existing) — Technical analysis of ESC failures, BTN8982TA vs IFX007T comparison
- Arduino Forum threads: BTS7960 failures in wheelchair projects
- Arduino.ru forum: Gas mower project overheating (~20–30 min)
- RadioKot.ru forum: Driver thermal management solutions
- SimpleFOC documentation: PWM frequency impact on switching losses

---

## Hardware Configuration (BiBa Phase 4)

| Component | Specification | Notes |
|-----------|---------------|-------|
| ESC Chip | BTS7960 (existing) | Testing for optimization potential |
| Heatsink | BLA178-1, 33×100×100 mm | Mounted on ESC housing |
| Thermal Compound | 3–5 W/mK (e.g., Arctic Silver, Thermal Grizzly) | Application area: chip → heatsink |
| Conformal Coating | Clear acrylic spray (IPC-CC-830) | Protection from moisture/dust |
| PWM Frequency | 5 kHz (reduced from 20 kHz) | Reduces switching losses |
| Load Test Motors | 250W, 24V, 2× (differential drive) | Same motors as field deployment |
| Monitoring | IS pin → RP2040 ADC + firmware logging | Current sense feedback for future throttle features |

---

## Success Metrics

| Metric | Target | Evidence |
|--------|--------|----------|
| BTS7960 Optimization | <120°C steady-state @ 60 min, 30A | Temperature log + field test report |
| PWM & Heatsink Effectiveness | Quantified delta (baseline vs optimized) | Thermal profile comparison |
| Startup Current Profile | Empirical data from 60 min test | IS pin firmware logs |
| Fallback Readiness | BTN8982TA evaluation plan + sourcing | If BTS7960 insufficient, contingency clear |
| Community Knowledge | Documented findings useful for others | OPTIMIZATION-REPORT.md (new deliverable) |

---

## Dependencies

- Phase 3 must be complete (baseline ESC thermal behavior established)
- BLA178-1 radiatior and thermal compound sourced
- RP2040 firmware supports IS pin ADC reading (already in place from Phase 2)

---

## Deferred to Future Phases

- **IFX007T evaluation:** Premium alternative, requires new PCB design — deferred to Phase 5+ if needed
- **Custom 200A ESC driver research:** User interest noted; out of scope for Phase 4 baseline. Can spawn separate research thread if BTS7960 + BTN8982TA both insufficient
- **Field-scale production assembly:** Design validation only; manufacturing scaling separate workflow
- **BMS integration on RP2040:** Remains on Pi Zero 2W reference platform

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| BTS7960 cannot reach <120°C with passive cooling | Fallback: source & test BTN8982TA immediately |
| Startup current spikes unaccounted for | Firmware logs IS pin during test; historical analysis post-facto |
| Heatsink inadequate for thermal contact | Test multiple thermal compounds; verify contact area via thermal imaging |
| Field ambient >25°C skews results | Document ambient conditions; test under stress (sunny day, if possible) |

---

## Next Steps (after planning)

1. **04-01-PLAN:** Compile BTS7960 optimization design doc (heatsink specs, conformal coat process, PWM firmware changes)
2. **04-02-PLAN:** Prepare test rig (motor + load, temperature monitoring, IS pin DAQ)
3. **04-03-PLAN:** Conduct 60 min validation test + data analysis
4. **04-04-PLAN:** Decision gate — if <120°C achieved, document optimization report + close phase; else, initiate BTN8982TA evaluation

