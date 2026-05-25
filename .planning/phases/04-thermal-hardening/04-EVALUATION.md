# Phase 4 ESC Evaluation

## Purpose

This note turns the failure analysis into a numeric comparison that can drive the selection memo and thermal design.

Source trail:

- [04-FAILURE-ANALYSIS.md](./04-FAILURE-ANALYSIS.md)
- [04-RESEARCH.md](./04-RESEARCH.md)
- [04-SPEC.md](./04-SPEC.md)
- [docs/wiring.md](../../../docs/wiring.md)

## Thermal Loss Comparison

Assumptions used for the table below:

- Loss estimate is the simple conduction term `P = I^2 * R`.
- Values are per bridge path, using the practical module-level Rds(on) numbers from the dialogue analysis.
- PWM implications are qualitative because switching loss depends on layout, gate drive, and cooling path.

| Driver | Rds(on) used | 20A loss | 30A loss | 40A loss | PWM frequency implication | Field reliability implication |
|--------|--------------|----------|----------|----------|---------------------------|------------------------------|
| BTS7960 | 16 mOhm | 6.4 W | 14.4 W | 25.6 W | Needs conservative PWM, around 5 kHz is the safe phase target; high PWM increases switching loss faster than the stock thermal path can absorb | Acceptable only as a hardened baseline with real heatsinking and current backoff; risk stays high in continuous field use |
| BTN8982TA | 10 mOhm | 4.0 W | 9.0 W | 16.0 W | Can tolerate a more comfortable PWM envelope than BTS7960, but the design should still avoid gratuitous high-frequency switching | Strong default RP2040 path because dissipation is lower and the package is still integration-friendly |
| IFX007T | 5 mOhm | 2.0 W | 4.5 W | 8.0 W | Best switching margin in this comparison; thermal behavior is the least sensitive to PWM overhead | Highest reliability margin, but the integration cost is higher because it pushes the project toward a board-level redesign |

## Practical Readout For BiBa

- BTS7960 is the cheapest path only if the chassis thermal stack is upgraded and current limiting is actively used.
- BTN8982TA is the first sensible replacement because it reduces heat materially without forcing a full redesign.
- IFX007T is the premium choice when the project wants maximum thermal headroom and can afford the integration work.

## Decision Inputs Reused By Selection

The selection memo should use the following facts directly:

- At 30A continuous, BTS7960 dissipates roughly 14.4 W per bridge path.
- At 30A continuous, BTN8982TA dissipates roughly 9.0 W per bridge path.
- At 30A continuous, IFX007T dissipates roughly 4.5 W per bridge path.
- The BiBa phase target is still a 60+ minute run at the thermal limit, so the default choice must leave margin for the housing, dust, and mounting path.
