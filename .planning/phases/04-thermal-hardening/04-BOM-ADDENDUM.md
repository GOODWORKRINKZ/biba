# Phase 4 Thermal BOM Addendum

## Purpose

This addendum makes the thermal cost delta visible for the BTN8982TA path and identifies which parts are optional.

## Thermal BOM

| Item | Role | Approx cost | Optional? |
|------|------|-------------|-----------|
| Aluminum heatsink / radiator, BLA178-1 class, about 33 x 100 x 100 mm | Main thermal path | $2-4 | No |
| Thermal compound | Improves contact between driver and heatsink | $0.50-1.50 | No |
| Isolation pad / thermal pad | Keeps the mount electrically safe if needed | $0.50-2.00 | Sometimes, depending on mount geometry |
| Mounting hardware and threadlock | Keeps the stack vibration-safe | $0.50-1.50 | No |
| Conformal coating | Moisture and dust protection | $0.50-2.00 | No for field builds |
| Fan, 40 mm class | Extra cooling margin if passive cooling is not enough | $2-5 | Yes |
| Connector boots / grommets / strain relief | Protects wiring and ingress points | $0.50-2.00 | No for field builds |

## Cost View

- Passive thermal hardening adds roughly $4-8 to the build.
- Adding the optional fan can raise the adder to roughly $6-13 depending on the supplier.
- The cost increase is visible and intentional because the phase is buying thermal margin, not just parts.

## Procurement Note

The passive stack should be ordered together so the thermal path can be assembled and tested as one unit. Do not treat the heatsink, compound, and sealing items as separate later niceties; they are part of the same thermal design.
