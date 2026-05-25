# Phase 4 Reliability Datasheet

## Summary

This datasheet records what Phase 4 proved, what it did not prove, and what the thermal headroom means for the RP2040 path.

## What Was Proven In Repository Form

- The BTS7960 thermal reset path still behaves deterministically.
- The portable current limiter still scales motor output independently.
- The standalone control path now logs current-limited behavior explicitly.
- The BTN8982TA path is selected as the default RP2040 ESC choice.

## What Remains Planned

- 60+ minute continuous-load field validation at the target load.
- Final publication of the field-ready matrix after that run.
- Any decision to promote IFX007T from premium path to default would require new evidence.

## Thermal Headroom Meaning

The numeric loss estimates from [04-EVALUATION.md](./04-EVALUATION.md) mean the following:

- BTS7960 at 30A continuous: about 14.4 W per bridge path.
- BTN8982TA at 30A continuous: about 9.0 W per bridge path.
- IFX007T at 30A continuous: about 4.5 W per bridge path.

Lower dissipation means less reliance on a perfect thermal interface and more margin for ambient heat, dust, and enclosure heat soak. That is why BTN8982TA is a better default than BTS7960 for the RP2040 path.

## Reliability Interpretation

- BTS7960 remains a valid baseline reference, but not a field-first choice for the long mission profile.
- BTN8982TA is the practical default because it improves reliability without forcing a board-level redesign.
- IFX007T offers the best long-run margin, but it is a premium follow-on path rather than the phase default.

## Bottom Line

Phase 4 now has a documented thermal decision path, a deterministic firmware-side backoff path, and a public matrix that separates selected, planned, and reference states. The missing piece is the external 60+ minute field run.
