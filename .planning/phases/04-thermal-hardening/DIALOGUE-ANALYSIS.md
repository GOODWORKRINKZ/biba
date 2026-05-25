# Phase 4 Working Notes: Dialogue Log Analysis

**Date:** 2026-05-17  
**Source:** `/home/ros2/Downloads/biba/artifacts/current-trace/phase-04-community-dialogue.log`  
**Status:** Ready for `/gsd-plan-phase 4`  

---

## Executive Summary

Community analysis reveals **BTS7960 thermal failure is systematic, not random:**
- Root cause: Pulsed startup currents exceed 100A (3–5× nominal), combined with Rds(on) = 16 mΩ → I²R losses dominate
- **Symptom pattern:** 20–30 minutes continuous load → thermal shutdown, motor/wheels lose power
- **Solution ecosystem:** BTN8982TA (drop-in replacement, 35% lower heat) and IFX007T (modern alternative, production-grade) both viable with proper thermal management

**Key insight:** Problem is not design, but **thermal contact and switching losses**. Proper heatsinking + lower Rds(on) chip fixes both BiBa and reported field failures.

---

## Failure Analysis Consolidated Findings

### BTS7960 Design Limitations

| Issue | Evidence | Impact |
|-------|----------|--------|
| **Rds(on) = 16 mΩ** | BTN7970 datasheet | At 30A: P = 900×16m = 14.4W per MOSfet. H-bridge = 28.8W total |
| **Chinese module thermal contact** | Arduino Forum, SimpleFOC Community | Via-hole design ineffective; radiatior "for show" — actual thermal resistance too high |
| **Pulsed current > 100A** | Arduino.cc wheelchair thread (#10) | Paul_KD7HB: "stalling/startup current 5–10× nominal." BTS7960 rated 43A max → fails on high-inertia load |
| **No soft start in field code** | Arduino.cc #24 | Hard reverse (forward → reverse) without deceleration creates current spikes |
| **High frequency switching losses** | SimpleFOC Community | 20 kHz PWM on old NovalithIC generates excess switching losses. Recommend ≤5 kHz for BTN7970. |

### Failure Timeline (BiBa Case Study)

```
Time      Condition              BTS7960 Status              Robot Behavior
------    ---------              -----                       -----
0 min     Cold start, PWM @20kHz Radiator ~30°C              Normal drive, responsive
5 min     Continuous 25A load   ~60°C (passive convection)   No symptoms
10 min    Damp grass (torque ↑) ~90°C                        Still operational
15 min    Throttle fluctuations  ~110°C (approaching Tj(max)) Slight motor lurch
20 min    Steady 25A             ~130°C (thermal mode active) Soft throttle-back engaged
25–30 min Continued 25A          ~150°C (shutdown imminent)   Motor power dropping
30 min    Peak load              Thermal shutdown (Tj ~160°C) Wheel skips, then stop
```

**Note:** Thermal runaway can occur if load remains high and heat dissipation inadequate. With better radiatior, can sustain 40A @ 100°C stable.

---

## Comparative Analysis: ESC Chips

### BTN7970 vs BTN8982TA vs IFX007T

| Parameter | BTN7970 | BTN8982TA | IFX007T | Note |
|-----------|---------|-----------|---------|------|
| **Rds(on)** | 16 mΩ | 10 mΩ | ~5 mΩ | Lower = less heat |
| **Continuous I** | 42 A | 50 A | 30 A (board limit) | Thermal dependent |
| **Pulse I (10ms)** | ~115 A | ~117 A | Design margin needed | Peak capability |
| **Losses @ 30A** | 14.4 W | 9 W | 4.5 W | per H-bridge |
| **Heat reduction** | baseline | -35% | -70% | vs BTN7970 |
| **PWM freq (opt)** | 20 kHz | 25 kHz | 30 kHz | Higher = less audible |
| **Footprint** | PG-TO263-7 | PG-TO263-7 | TO-263-7 | BTN8982 is pin-compat |
| **Cost (SNG)** | $0.50–1 | $1–2 | $4–7 | IFX007T premium |
| **Availability** | EOL/NRND | Active | Active | IFX007T preferred |
| **Current Sense** | Basic | Improved | Excellent | Useful for protection |

**Production recommendation:** BTN8982TA for 24V RP2040 variant (price/performance sweet spot). IFX007T for premium/high-reliability builds.

---

## Root Causes Identified

### 1. Pulsed Current Exceeds Rating
**Evidence:**
- Arduino.cc wheelchair: "Stall current 5–10× rated" (Paul_KD7HB, post #10)
- BiBa field test 2026-05-09: "Motor startup → 40–60A spike, BTS7960 protection engaged"
- Gas mower project: "Two motors starting simultaneously → combined 80A spike"

**Physics:** Locked-rotor or high-inertia load has zero back-EMF initially. I = V / R_winding. For 24V @ 0.5 Ω winding → 48A. With PWM duty cycle effects and acceleration phase → peaks >100A possible.

**Mitigation:** Soft-start (PWM ramp over 100–200 ms), current limiting via firmware or dedicated IC.

### 2. Thermal Contact Poor on Chinese Modules
**Evidence:**
- SimpleFOC Community: "IBT-2 via-hole design doesn't transfer heat effectively"
- BiBa team solution: "Paste radiatior on aluminum plate + conformal coat" (Telegram 2026-05-08)

**Design flaw:** Stock boards rely on via-array to transfer heat from drain pads to back-side radiatoir. But thermal resistance via TO263-7 pads → vias → radiatoir ≈ 0.5–1 K/W additional. Direct solder + thermal epoxy → 0.1–0.2 K/W.

**Mitigation:** Use thermally conductive epoxy or solder assembly house (JLCPCB thermal assembly option). Budget $5–10 per board for upgrade.

### 3. Switching Losses Dominate at High Frequency
**Evidence:**
- SimpleFOC: "Lower PWM to 3–5 kHz → melting stops" (custom board discussion)
- BiBa observation: 20 kHz default PWM on RP2040 causes faster thermal rise than Pi Zero 2W at same load

**Physics:** Switching loss P_sw = ½ × C × V² × f. At 24V, 20 kHz → higher loss than 5 kHz by 4×. Older NovalithIC (BTN7970) has higher switching losses than modern tech.

**Mitigation:** Reduce PWM to 10 kHz (still inaudible to humans >5 kHz, but avoids ultrasonics). Or switch to BTN8982TA/IFX007T with lower Cgs and better gate drive.

### 4. No Current Monitoring or Thermal Protection in Production Code
**Evidence:**
- BiBa Phase 3: "Thermal reset via EN pulse implemented, but no predictive throttling"
- Arduino forum: "We added software current limit in post #24 — no more crashes"

**Mitigation:** Use IS (Current Sense) pin on ESC to feed ADC → firmware throttle-back before thermal shutdown. Typical threshold: 35A for 250W motor on 24V.

---

## Community Solutions Tested

### Passive Cooling (No Fan)
- **Radiatoir size:** Al extrusion ≥50 mm × 50 mm × 3 mm
- **Thermal compound:** 3–5 W/mK (e.g., Thermal Grizzly Kryonaut)
- **Conformal coating:** Clear acrylic spray (protects from moisture)
- **Result:** Extends stable operation from 20 min → 40+ min @ 25A
- **Cost:** $2–5 per unit

### Active Cooling (Fan)
- **Fan:** Axial 40×40×10 mm, 12V, 0.15A (~5 CFM)
- **Placement:** Tangential to heatsink (creates convection)
- **Trigger:** Enable fan via GPIO when ESC temperature >80°C (if thermistor added)
- **Result:** Sustains 40+ A indefinitely @ stable 100–110°C
- **Cost:** $3–8 per unit, adds PWM complexity

### Hybrid Solution (Recommended for Production)
1. Al radiatoir (passive baseline) — $2–3
2. Optional 5V fan header (GPIO controlled) — $1–2 BOM
3. Current sense on firmware for predictive throttle — free (firmware)
4. Conformal coating — $0.50

**Total cost adder:** $3–5 per unit for full thermal hardening.

---

## ESC Selection Decision Matrix

| Factor | Weight | BTN8982TA | IFX007T | Winner |
|--------|--------|-----------|---------|--------|
| Cost | 25% | $1–2 | $4–7 | BTN8982TA |
| Availability (RU/SNG) | 20% | Excellent | Good | BTN8982TA |
| Integration effort | 15% | 0 (drop-in) | Moderate (new board design) | BTN8982TA |
| Heat performance | 20% | -35% vs BTN7970 | -70% vs BTN7970 | IFX007T |
| Reliability track record | 10% | Good (Infineon) | Excellent (modern) | IFX007T |
| Future-proof | 10% | Yes (in production) | Yes (premium) | IFX007T |
| **Weighted Score** | 100% | **4.7 / 5.0** | **4.5 / 5.0** | **BTN8982TA** |

**Decision:** 
- **RP2040 default variant:** BTN8982TA (cost-effective, proven Infineon, immediate deployment)
- **Premium/high-reliability variant:** IFX007T (future roadmap, requires new PCB, but superior performance)
- **Backwards compatibility:** Both can replace BTN7970 on existing boards with thermal management upgrade

---

## Recommended Design Direction

### Thermal Architecture Specification

```
[RP2040 CPU]
   ↓
[GPIO] ────→ [EN pin driver] ──→ [BTN8982TA H-Bridge]
[PWM]  ────→ [IN/INH pins]      ├─ Motor Left
[ADC]  ←──── [IS pin]           └─ Motor Right
   
               ┌─────────────────────────────────────┐
               │  Thermal Management Layer           │
               ├─────────────────────────────────────┤
               │ • Al heatsink (50×50×3 mm)          │
               │ • Thermal epoxy (>3 W/mK)           │
               │ • Conformal acrylic coat (moisture) │
               │ • Optional: 5V fan (40 mm axial)    │
               │ • Firmware: throttle @ IS >35A      │
               └─────────────────────────────────────┘
```

### Validation Test Plan

**Hardware:** Prototype with BTN8982TA + Al radiatior + conformal coat

**Test 1: Thermal Steadiness**
- Load: 30A continuous @ 24V (250W motor)
- Duration: 60+ minutes
- Acceptance: ESC temp ≤120°C, no thermal shutdown
- Measurement: IR thermography (or internal thermistor if added)

**Test 2: Current Spike Handling**
- Load: Simulated stall (locked motor) for 500 ms, then 30A continuous
- Duration: 10 cycles
- Acceptance: No damage, firmware throttle engages predictively
- Measurement: Oscilloscope capture of IS pin vs. firmware throttle response

**Test 3: Field Deployment**
- Scenario: 2+ hours continuous grass-cutting simulation with periodic high-torque events
- Acceptance: No thermal shutdown, wheels responsive throughout
- Measurement: Time-stamped log of motor current and ESC temperature

---

## Deliverables for 04-01 through 04-04

### 04-01-PLAN Deliverables
- [ ] ESC-FAILURE-ANALYSIS.md (this document, formalized)
- [ ] Comparative table: BTN7970, BTN8982TA, IFX007T, IFX007T-based products
- [ ] Forum thread references: 3 Arduino.ru, 2 Arduino.cc, 1 RadioKot (sourced, summarized)
- [ ] Cost analysis: component cost by source (Чип и Дип, Mouser, AliExpress)

### 04-02-PLAN Deliverables
- [ ] Thermal simulation: P_loss @ 20A, 30A, 40A for each chip
- [ ] Sourcing map: Where to buy in RU (Чип и Дип, TM Electronics, Laserzz) with lead times
- [ ] Selection rationale: Why BTN8982TA chosen for RP2040 + IFX007T for future
- [ ] BOM comparison: cost per unit in production volume (10, 100, 1000)

### 04-03-PLAN Deliverables
- [ ] THERM-DESIGN.md: Al extrusion spec, thermal compound, fan (optional) placement
- [ ] PCB layout guidelines: Ground plane, current paths, drain pad area
- [ ] Assembly procedure: How to install radiatoir + conformal coat at JLCPCB
- [ ] EMC/waterproofing: Grommet, cable routing, connector sealing

### 04-04-PLAN Deliverables
- [ ] VALIDATION-TEST-REPORT.md: 60+ min test results with IR images
- [ ] HARDWARE-MATRIX.md: Published to github, RP2040 × [BTN8982TA, IFX007T] × [250W motor, 350W motor]
- [ ] RELIABILITY-DATASHEET.md: MTBF projection, thermal headroom analysis
- [ ] Production readiness checklist: DFA review, cost estimate, supply-chain risk

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| IFX007T sourcing difficult | Maintain dual-source strategy: BTN8982TA as default, IFX007T as premium option |
| Thermal design requires SPICE modeling | Use Infineon + SimpleFOC open SPICE models; skip FEA if computational budget tight |
| Field test schedule slips | Pre-order heatsinks + conformal spray now; can start thermal integration while Phase 3 finalizes |
| Production fab changes add lead time | Lock-in JLCPCB thermal assembly SOP early; test first board from process |

---

## Open Questions for Planning Phase

1. **Should we prototype both BTN8982TA and IFX007T, or go all-in on BTN8982TA?**
   - Answer: BTN8982TA for Phase 4 (cost/schedule). IFX007T spike after Phase 4 completes if budget allows.

2. **Is active fan cooling required, or will passive radiatoir be enough?**
   - Answer: Passive sufficient for 40–60 min nominal missions. Fan enables all-day operation; budget accordingly.

3. **Can we integrate current sense feedback into firmware for predictive throttle-back?**
   - Answer: Yes. IS pin outputs 0–5V proportional to motor current. Firmware reads ADC and reduces PWM duty if exceeded threshold. Cost: firmware + minor hardware (pull-up resistor).

4. **What's the production cost delta (BTN7970 → BTN8982TA + thermal mgmt)?**
   - Answer: ~$4–6 per unit adder (chip $1, heatsink $2–3, conformal $0.50, fan optional $2). Justified by reliability + warranty reduction.

