# Phase 4 EMC and Waterproofing

## Purpose

This note captures the field protection strategy around the thermal stack so the ESC can survive dust, splash, and wiring vibration.

## Moisture Strategy

- Apply conformal coating to the exposed electronics that are not part of the thermal contact surface.
- Keep coating off the heatsink contact area and off any connector pins that need to stay serviceable.
- Seal cable entry points with grommets or strain-relief fittings.
- Route wires so water does not pool and run directly into the connector body.

## Dust Strategy

- Use the heatsink orientation to avoid making the fins a dust shelf if possible.
- Keep the board and connector openings away from direct wheel spray and ground splash.
- Prefer a mounting position that leaves the heat sink in moving air without exposing the electronics to direct debris hits.

## EMC Strategy

- Keep the power loop compact to reduce radiated noise.
- Separate the motor leads from the current-sense wiring as much as practical.
- Maintain a clean ground reference between the controller side and the ESC side.
- If a fan is added later, treat its wiring as a noise source and route it away from the sense lines.

## Connector Protection

- Use locking connectors where possible.
- Add strain relief so the harness does not load the solder joints.
- Mark the current-sense and motor connectors clearly so field servicing does not swap them.
- Inspect connector seals after any high-dust or wet run.

## Field Check

Before a run, confirm:

- the heatsink is mechanically secure,
- the coating is dry,
- the cable entries are sealed,
- and the board can be inspected without removing the thermal interface.
