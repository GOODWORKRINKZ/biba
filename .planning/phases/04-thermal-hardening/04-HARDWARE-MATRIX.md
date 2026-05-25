# Phase 4 Hardware Matrix

## Purpose

This matrix publishes the current RP2040 ESC compatibility view for Phase 4.

Legend:

- `ready` = validated enough for the current repository scope
- `selected` = chosen default path for this phase
- `planned` = intended but not yet validated in the phase
- `reference` = historical baseline only
- `not recommended` = the analysis says not to use it for the listed combo

## ESC x RP2040 x Motor Matrix

| ESC | RP2040 | 250W MY1016Z2 | 350W MY1016Z2 | Status | Notes |
|-----|--------|---------------|---------------|--------|-------|
| BTS7960 | yes | reference only | not recommended | reference | Baseline module, but thermal margin is too tight for the long-run target |
| BTN8982TA | yes | selected | planned | selected | Default RP2040 path; lower dissipation and lower integration cost than the premium option |
| IFX007T | yes | planned | planned | planned | Premium path with best thermal headroom, but it needs more integration work |

## Publication Note

This matrix is intentionally conservative. A combo is only marked `ready` once the long-run field proof is available. Until then, the matrix distinguishes the selected path from the validated field state.
