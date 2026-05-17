# Phase 4: Thermal Hardening & ESC Architecture - Research

**Gathered:** 2026-05-17
**Status:** Ready for planning
**Source:** Phase 4 discussion log, spec, manifest, and repo inspection

<domain>
## Phase Boundary

Phase 4 is about hardening the brushed-DC drive stack so the RP2040 variant can survive long field runs without BTS7960 thermal shutdown. The phase centers on three decisions: which ESC path to prefer, how to cool and package it, and how to prove the design with a long-duration load test.

The discussion log makes the practical direction explicit: optimize the current BTS7960 setup first, especially with lower PWM frequency and a proper heat sink, then fall back to BTN8982TA if the current hardware cannot hold the temperature target. IFX007T remains a premium or follow-on option, not the first move.
</domain>

<decisions>
## Implementation Decisions

### Community failure analysis is not optional
- The phase must formalize the lessons already captured in dialogue.log and DIALOGUE-ANALYSIS.md into a standalone failure analysis document.
- The analysis should cover at least five real projects and should not stop at a single BiBa anecdote.

### BTS7960-first, BTN8982TA fallback
- The discussion log repeatedly points to a pragmatic sequence: improve BTS7960 cooling and PWM behavior first, then evaluate BTN8982TA if the thermal target is missed.
- IFX007T is a later or premium option, useful for comparison but not the immediate default path.

### Cooling strategy must be concrete
- The user has already chosen a real heat-sink path: a metal-mounted radiator plus thermal compound and waterproofing.
- Any plan that leaves the cooling stack abstract will be too weak to verify in the field.

### Current-sense feedback should drive behavior, not just logging
- Current monitoring is useful only if it can influence throttle-back before thermal shutdown.
- IS pin readings need to become part of the validation story, not just a future idea.

### the agent's Discretion
- Exact PCB layout ownership for the IFX007T path.
- Whether the active fan is mandatory or a contingency after passive cooling is validated.
- Exact current threshold calibration details for the throttle-back logic, provided the chosen threshold remains consistent with the phase goal.
</decisions>

<canonical_refs>
## Canonical References

Downstream agents MUST read these before planning or implementing.

### Source of truth for phase 4 scope
- `.planning/phases/04-thermal-hardening/04-SPEC.md` - locked requirements and acceptance criteria for the phase.
- `.planning/phases/04-thermal-hardening/PHASE-MANIFEST.md` - plan decomposition, deliverables, and estimates.
- `.planning/phases/04-thermal-hardening/04-DISCUSSION-LOG.md` - user decisions and the BTS7960-first cooling strategy.
- `artifacts/current-trace/phase-04-community-dialogue.log` - raw discussion source that the phase analysis is based on.

### Firmware and field-validation references
- `firmware/src/drivers/bts7960.c` - current BTS7960 enable / reset behavior.
- `firmware/src/modes/mode_standalone.c` - where thermal and current handling are currently applied.
- `firmware/src/drivers/current_sense.h` - current-sense interface already in use.
- `docs/field-validation.md` - field-run evidence rules and abort criteria.
- `docs/wiring.md` - current-sense wiring and PWM mode notes.
- `docs/variants.md` - cross-platform compatibility matrix context.

### Comparative research references
- `.planning/phases/04-thermal-hardening/DIALOGUE-ANALYSIS.md` - preliminary ESC and cooling comparison.
- `docs/plans/2026-03-25-bts7960-implementation.md` - older BTS7960 pattern for docs/tests structure.
</canonical_refs>

<specifics>
## Specific Ideas

- The phase should keep the BTS7960 module as a baseline case study because that is what the robot already uses in practice.
- The documented thermal path should include heat sink mounting, thermal compound, conformal coating, and optional fan logic.
- The validation plan should explicitly preserve the 60+ minute load-test requirement and the 30A target from the phase spec.
- The hardware matrix should end in a publishable markdown artifact linked from the repo documentation rather than an internal-only note.
</specifics>

<verification_notes>
## External Verification Notes

The external sources mostly support the direction of the phase, but some statements in the discussion log should be treated as recommendations rather than hard facts:

- **Confirmed by the Arduino wheelchair thread**: the start/stall current is materially higher than the running current, one PWM pin driving both motors is a wiring/design error, the BTS7960 module can fail when the logic ground is wrong or when the module is miswired, and the thread explicitly recommends soft start / deceleration before reverse.
- **Confirmed by the Arduino.ru mower thread**: the project description matches the BiBa-style risk profile, with two 24V brushed motors, chain-coupled wheels, and a user concern about BTS7960-based control being the weak link. This thread is useful context, but it is not itself a controlled thermal benchmark.
- **Confirmed by the IFX007T repo**: the shield supports one or two bidirectional DC motors, documents current sense, over-temperature and overcurrent protection, and shows the ready-made shield / design-data split. The repo supports the comparison, but it does not by itself prove a BiBa field result.
- **Not hard-confirmed from the sources alone**: a universal requirement to use 5 kHz PWM, any specific temperature ceiling, or any claim that every BTS7960 board behaves identically. Those are phase-specific decisions or vendor/module-dependent observations, not source-level guarantees.

Planner implication: use the sources to justify the thermal-risk narrative and the candidate ESC comparison, but keep the final cooling threshold and PWM choice tied to phase requirements and validation evidence.
</verification_notes>

<deferred>
## Deferred Ideas

- Custom 200A+ ESC design.
- Full PCB redesign for a production IFX007T carrier.
- Oscilloscope-based transient current analysis if the field validation can already prove the thermal outcome.

</deferred>

---

*Phase: 04-thermal-hardening*
*Context gathered: 2026-05-17 via discussion log + repo inspection*
