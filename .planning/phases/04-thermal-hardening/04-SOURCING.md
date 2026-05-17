# Phase 4 ESC Sourcing

## Purpose

This note records realistic procurement channels for the candidate drivers so the selection memo can distinguish cost from supply risk.

The prices below are approximate research bands, not live quotes. Verify stock before ordering.

## BTS7960 Baseline Supply

| Channel | Approx cost | Availability | Lead time | Authenticity / risk note |
|---------|-------------|--------------|-----------|--------------------------|
| Existing BiBa spare modules | $0 incremental | Immediate if a spare is already on hand | None | Lowest risk because the module is already in the project inventory |
| Ozon / local marketplace module listings | $2-6 per module | Often available | 1-7 days | High counterfeit and relabel risk; inspect markings and avoid anonymous sellers |
| AliExpress / broad marketplace listings | $1-4 per module | Usually available | 1-6 weeks | Highest authenticity risk; acceptable only for bench experiments |

## BTN8982TA Procurement

| Channel | Approx cost | Availability | Lead time | Authenticity / risk note |
|---------|-------------|--------------|-----------|--------------------------|
| Mouser | $1-2 | Good | 2-7 days to ship, plus transit | Best traceability; preferred for the default path |
| Digi-Key | $1-2 | Good | 2-7 days to ship, plus transit | Best traceability; preferred when Mouser stock is low |
| ChipDip / TME / similar regional distributors | $1.5-3 | Medium to good | 2-14 days | Verify package marking and part number; distributor quality varies by region |

## IFX007T Procurement

| Channel | Approx cost | Availability | Lead time | Authenticity / risk note |
|---------|-------------|--------------|-----------|--------------------------|
| Mouser | $4-7 | Good to medium | 2-7 days to ship, plus transit | Traceable and preferred for the premium path |
| Digi-Key | $4-7 | Good to medium | 2-7 days to ship, plus transit | Traceable and preferred when available |
| TME / element14 / regional industrial distributor | $4-8 | Medium | 3-14 days | Good if stock is traceable; confirm the exact package and suffix |

## Procurement Readout

- The low-friction default path is BTN8982TA.
- The premium path is IFX007T.
- Marketplace BTS7960 modules are acceptable only as baseline or test hardware, not as the preferred long-term procurement route.

## Authenticity Caveat

For all three candidates, marketplace listings can be relabeled, second-hand, or counterfeit. For BiBa, the safest rule is:

1. Buy the default path from a traceable distributor.
2. Use marketplace parts only for exploratory testing.
3. Record the vendor name and part marking before installation.
