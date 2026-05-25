# Phase 4 Selection Rationale

## Decision

**Default RP2040 ESC path: BTN8982TA.**

**Deferred premium path: IFX007T.**

This is the locked decision for Phase 4.

## Why BTN8982TA Is The Default

BTN8982TA is the best fit for the RP2040 path because it keeps the project close to the existing BTS7960 wiring model while materially lowering dissipation. It reduces the thermal burden enough to support the phase target without forcing a full board redesign.

The selection is also practical:

- It is cheaper than IFX007T.
- It is easier to source quickly through traceable distributors.
- It is much less disruptive to integrate than a new premium driver path.
- It preserves the current project cadence: improve the existing drive stack first, then harden the thermal package around it.

## Why IFX007T Is Deferred

IFX007T has the best thermal margin in this comparison, but it is not the default because it carries higher integration cost and higher procurement cost. It is the correct premium option if the project later wants a stronger production margin or if the BTN8982TA path proves insufficient in the field.

That deferral is deliberate, not tentative:

- The RP2040 phase does not need the highest-margin part to prove the design intent.
- The phase needs a reliable, low-friction path that can be built and validated quickly.
- IFX007T can remain the upgrade path once the thermal architecture and field validation are stable.

## Why BTS7960 Is Not The Default

BTS7960 remains the baseline reference because it is already in the project, but it is not the default RP2040 solution. The failure analysis shows that its thermal margin is too tight for long continuous runs unless the whole thermal stack is unusually well executed.

BTS7960 is therefore treated as a control case and a fallback for historical context, not as the preferred long-term path.

## Integration Tradeoff

The choice is a tradeoff between margin and effort:

- BTN8982TA gives enough thermal improvement for the phase target with manageable effort.
- IFX007T gives more thermal headroom but asks for more integration work than the phase needs right now.
- BTS7960 has the lowest immediate cost but the highest field-risk profile.

## Final Statement

For Phase 4, the RP2040 default ESC choice is **BTN8982TA**. The deferred premium alternative is **IFX007T**. That split is intentional and final for this phase.
