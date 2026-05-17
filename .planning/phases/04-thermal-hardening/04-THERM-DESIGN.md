# Phase 4 Thermal Architecture

## Purpose

This document turns the selected BTN8982TA path into a concrete thermal stack that can be built, mounted, and checked in the field.

Source trail:

- [04-SELECTION-RATIONALE.md](./04-SELECTION-RATIONALE.md)
- [04-THERM-RESEARCH.md](./04-RESEARCH.md)
- [04-DISCUSSION-LOG.md](./04-DISCUSSION-LOG.md)
- [docs/field-validation.md](../../../docs/field-validation.md)

## Thermal Goal

The design target for the phase is:

- keep the ESC case below 120 C during a 60+ minute run at 30A continuous load;
- keep the thermal path predictable enough that the current limit logic can back off before shutdown;
- leave enough margin that dust, enclosure heating, and ambient rise do not immediately collapse the design.

Practical stack target:

- module base to ambient thermal path should be treated as a sub-6 C/W design goal for the assembled vehicle side mount.

## Thermal Loss Root Cause & Selection Rationale

**Conduction Loss Formula:**
$$P_{loss} = I^2 \times R_{ds(on)}$$

**Comparison (30A continuous load):**
- BTS7960 (16mΩ Rds_on): $P_{loss} = 30^2 \times 0.016 = 14.4\text{ W}$
- **BTN8982TA (10mΩ Rds_on): $P_{loss} = 30^2 \times 0.010 = 9\text{ W}$** ← **~35% reduction**

**Reference:** Cytron Design article confirms that MOSFET Rds_on is the dominant thermal loss path in DC motor H-bridge drivers. Lower on-resistance directly reduces junction temperature rise.

## Synchronous Rectification & Dead Time Management

**Industry Standard (Cytron Design):**
Synchronous rectification replaces the flyback diode (0.5-1V forward drop loss) with a MOSFET-based switch controlled by the gate driver. At 30A continuous, this reduces recirculation losses by replacing conduction through a diode with conduction through Rds_on.

**Dead Time Implication:**
The A3941 gate driver IC (Electronics-Lab reference design) provides adjustable dead time to prevent shoot-through (simultaneous conduction of high-side and low-side FETs). Proper dead time ensures only one MOSFET conducts at any instant, critical for efficiency and thermal performance.

**Cross-Architecture Validation (Arduino Forum):**
MOSFET-based H-bridges are preferred for <200V systems (24V system ✓). IGBTs introduce additional switching loss at low voltages and are unnecessary for battery-powered applications.

## Main Capacitor Sizing

The bootstrap capacitor and main supply capacitor bank serve critical thermal roles:

1. **Voltage Stabilization:** Large capacitors prevent bus voltage sag during high di/dt transients
2. **Thermal Exposure:** The capacitor reaches operating temperature due to switching current flow through ESR
3. **Practical Guidance (Cytron Design):** Oversizing the main capacitor bank is often overlooked but essential—a large capacitor reduces ripple voltage and di/dt stress on the MOSFETs, which indirectly reduces thermal coupling

**A3941 Charge Pump Feature (Electronics-Lab):**
An integrated charge pump provides full (>10V) gate drive even at 7V battery voltage, enabling proper MOSFET switching at low supply levels. This ensures consistent gate-source voltage and prevents slow switching (which increases conduction time and heat).

## Cooling Stack

Recommended stack from driver to chassis:

1. BTN8982TA module or equivalent carrier.
2. Thin thermal interface layer.
3. Aluminum heatsink / radiator mounted to the housing.
4. Mechanical fastener with even pressure across the contact area.
5. Conformal coating on exposed electronics around, but not on, the thermal contact surface.

The thermal stack is intentionally simple. The phase does not rely on hidden airflow assumptions.

## Passive Cooling Baseline

The baseline solution is passive:

- BLA178-1 style aluminum radiator, about 33 x 100 x 100 mm.
- Thermal compound with a real contact path, not a dry clamp.
- Mount the radiator to the robot housing where the heat can spread into the chassis.

This is the default phase assumption. If the passive stack misses the target in the validation run, add a fan rather than redesigning the whole drive path.

## Optional Active Cooling Path

The optional upgrade is a small fan mounted so it pushes air across the heatsink fins.

Use this only if:

- the passive stack reaches the target only marginally, or
- the validation run shows a slow temperature climb late in the session, or
- the enclosure environment is hotter or dustier than the baseline field case.

The fan is a fallback, not the core design assumption.

## Temperature Trigger Logic

The firmware side should treat thermal pressure as a control problem, not just a warning.

Recommended behavior:

- current sensing feeds the limiter that already exists in the control loop;
- if current rises above the configured threshold, PWM should back off before the module enters thermal shutdown;
- telemetry should continue to flag current limiting so the run record shows when the backoff started.

This keeps the field evidence aligned with the control behavior.

## Field Assumptions

The design assumes:

- 24V brushed drive hardware;
- repeated accelerations, turns, and stop-start behavior;
- enclosure dust and splash exposure;
- a chassis-mounted heatsink with real mechanical coupling to the body of the robot.

## Acceptance View

The thermal design is acceptable only if the field run can be described in plain language as:

- the ESC stays within the target temperature band,
- the chassis mount visibly contributes to heat removal,
- and current-based backoff appears before catastrophic shutdown.

## Industry References & Technical Validation

**1. Cytron Design: DC Motor Driver Architecture**
- Confirms synchronous rectification as industry standard for 24V H-bridge systems
- Provides empirical comparison: diode rectification (0.5-1V loss) vs MOSFET Rds_on-based switching
- Documents dead time management criticality for shoot-through prevention
- Emphasizes main capacitor design as often-overlooked thermal factor

**2. Arduino Forum: MOSFET vs IGBT Selection**
- Community consensus: MOSFETs optimal for <200V systems (validates 24V BTN8982TA choice)
- IGBTs introduce unnecessary switching losses at battery voltages
- GaN/SiC noted as future evolution for higher efficiency

**3. Electronics-Lab: A3941 50V/10A Reference Design**
- Gate driver architecture with integrated charge pump (enables full gate drive at 7V-50V battery range)
- Bootstrap capacitor requirement for N-channel MOSFET gate-source voltage
- Dead time protection against shoot-through (tunable via resistor R7)
- Synchronous rectification supported natively in A3941 configuration
- Over-temperature and under-voltage diagnostics provide feedback path for firmware throttle

**Design Closure:**
The BTN8982TA H-bridge + BLA178-1 passive cooling stack + firmware current limiter addresses the root thermal failure mode (I² × Rds_on conduction losses) through both hardware (lower Rds_on, passive dissipation path) and firmware (dynamic backoff before shutdown). Industry references validate MOSFET selection, synchronous rectification benefits, and critical role of dead time and capacitor design for reliable thermal behavior.
