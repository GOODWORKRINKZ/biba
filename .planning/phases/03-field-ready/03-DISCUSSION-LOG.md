# Phase 3 Discussion Log

**Date:** 2026-05-16
**Topic:** BTS7960 thermal latch recovery for brushed motor path

## Summary

- User investigated BTS7960 thermal protection behavior and proposed clearing the fault by pulling `R_EN` / `L_EN` LOW instead of cutting power with an SSR.
- Official Infineon datasheet confirmed that overtemperature shutdown is latched and is reset by `INH LOW` for at least `treset`.
- The module-level wiring used in this repo exposes enable lines as `R_EN` / `L_EN`, so the agreed implementation direction is to use those lines for recovery.

## Decisions captured

1. Thermal reset via `EN LOW` is accepted for the brushed BTS7960 path.
2. SSR is not required solely to clear the thermal latch.
3. The reset pulse will be specified as 100 us for implementation planning.

## References used during discussion

- `artifacts/datasheets/infineon-bts7960-ds-en.pdf`
- `docs/wiring.md`
- `biba-controller/motors/driver.py`
- `.planning/phases/01-core-drive/01-CONTEXT.md`