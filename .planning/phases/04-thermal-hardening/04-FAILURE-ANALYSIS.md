# Phase 4 Failure Analysis: BTS7960 Thermal Risk

## Purpose

This document normalizes the community evidence chain for Phase 4 so the ESC selection and thermal-design plans can reuse it without re-reading raw dialogue.

Canonical source chain:

- [artifacts/current-trace/phase-04-community-dialogue.log](../../../artifacts/current-trace/phase-04-community-dialogue.log)
- [04-DISCUSSION-LOG.md](./04-DISCUSSION-LOG.md)
- [DIALOGUE-ANALYSIS.md](./DIALOGUE-ANALYSIS.md)
- [04-RESEARCH.md](./04-RESEARCH.md)

## Case Table

| Case | Project / Thread | Observed load | Failure timing | Thermal symptom | Root cause category | Source basis |
|------|------------------|---------------|----------------|-----------------|---------------------|--------------|
| 1 | BiBa field test | Dual brushed drive on 24 V system; repeated acceleration and turns | About 20-30 minutes | One side starts to lag, then driver thermal shutdown behavior appears | Thermal contact weakness + switching loss + high current spikes | Current trace, discussion log, and field notes referenced in the dialogue log |
| 2 | Arduino.ru mower thread | Two 24 V brushed motors, chain-coupled wheels, RC lawn mower | During proposed long mowing runs; concern raised before reliable field proof | BTS7960 identified as the weak link under sustained load | Current spikes from stall/start plus insufficient heat sinking | Forum thread summarized in the dialogue log |
| 3 | Arduino wheelchair thread | 24 V wheelchair motors around 14 A nominal | After repeated testing; driver failure reported after a few days | Both BTS7960 modules stopped working | Start/stall current 5-10x nominal, missing common ground, abrupt reversals | Forum thread analysis in the dialogue log |
| 4 | RadioKot / SimpleFOC discussion | Brushed motor control with NovalithIC-style driver modules | Continuous operation, especially with higher PWM frequency | Heat rise accelerates when PWM stays high | Switching losses dominate when PWM frequency is too aggressive | Community thread summary and SimpleFOC notes from the dialogue log |
| 5 | BTS7960 + MY1016Z2 field example | 24 V MY1016Z2-class motor on BTS7960 module | 20-30 minutes on a loaded drive profile | Drive weakens, module overheats, shutdown or brownout follows | High startup current plus weak thermal path from module to chassis | BTS7960 + MY1016Z2 note captured in the dialogue log |
| 6 | BTS7960 video / field example | Public BTS7960 brushed-drive example linked in the dialogue log | Continuous use case with repeated starts and stops | Thermal rise becomes the limiting factor, not nominal steady-state current | Switching losses and poor module thermal path | Linked video/example captured in the dialogue log |

## Normalized Failure Pattern

Across the cases above, the same pattern repeats:

1. Startup or stall current is much higher than steady-state current.
2. The BTS7960 module dissipates more heat than the stock thermal path can remove.
3. High PWM frequency adds switching loss on top of I2R loss.
4. After roughly 20-30 minutes of loaded drive, the module enters thermal protection or behaves as if it is collapsing thermally.
5. If the system keeps driving without a controlled cooldown or current backoff, the failure repeats.

The important conclusion for Phase 4 is that the failure is systematic. It is not just a single bad board. The combination of pulsed current, poor thermal contact, and switching losses is the recurring root cause.

## Failure Timeline

The BiBa case matches the broader community pattern:

| Time | Expected condition | Observed risk trend |
|------|--------------------|---------------------|
| 0 min | Cold start | High transient current, thermal margin is maximum |
| 5-10 min | Normal motion | Heat begins accumulating in the module and mounting surface |
| 15-20 min | Continuous loaded drive | Module temperature rises quickly if the thermal interface is weak |
| 20-30 min | Prolonged load | Thermal shutdown or visible drive degradation becomes likely |
| 30+ min | No mitigation | Repeated throttle loss, reset behavior, or full stop |

The 20-30 minute window is the practical warning interval that Phase 4 must design around.

## Root Cause Categories

### 1. Current spikes

Brushed motors can draw 3-10x nominal current during start, stall, or abrupt reversal. That is enough to overwhelm a driver that looks adequate on paper but has limited thermal headroom.

### 2. Thermal contact weakness

Many BTS7960 modules rely on a weak thermal path through the module PCB and a small heatsink area. If the driver is only bolted to air or plastic, heat removal is too slow for long runs.

### 3. Switching losses

Higher PWM frequency makes the module quieter, but it also increases switching loss. On an older high-current H-bridge, that can materially accelerate thermal rise.

## Reusable Comparison Matrix

| Driver | Rds(on) | Thermal headroom | Integration effort | Field-safety implication for BiBa |
|--------|---------|------------------|--------------------|-----------------------------------|
| BTS7960 | About 16 mOhm per path | Marginal without real heatsinking; acceptable only with conservative current limits and lower PWM frequency | Lowest effort because the hardware already exists | Safe only as a hardened baseline; needs current backoff and good thermal contact to avoid repeated shutdowns |
| BTN8982TA | About 10 mOhm per path | Better than BTS7960; lower dissipation at the same load | Low to moderate; drop-in friendly compared with a full redesign | Strong default fallback if BTS7960 still runs hot; improves field reliability without a full board rev |
| IFX007T | About 5 mOhm per path | Highest margin in this comparison | Higher; likely needs a new board or tighter mechanical integration | Best long-run safety margin, but it is a premium path because the integration cost is higher |

## Decision Use

This analysis is intentionally conservative:

- Community anecdotes are treated as evidence of failure modes, not as controlled measurements.
- The dialogue log remains the canonical source chain for the user-facing narrative.
- The matrix is written so the selection plan can reuse it directly without reinterpretation.

## Conclusion

Phase 4 should treat the BTS7960 thermal problem as a predictable engineering limit. The usable design path is to preserve the existing drive stack only if it is paired with a proper thermal interface, lower switching loss, and current-based throttle back. If that still misses the target, BTN8982TA is the sensible fallback, and IFX007T is the premium high-margin alternative.
