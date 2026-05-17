# Phase 4 PCB Layout Guide

## Purpose

This guide captures the physical layout constraints needed to keep the thermal path, current path, and sensor path believable in the field.

## Thermal Interface Path

- Keep the BTN8982TA carrier as close as practical to the metal mount or heatsink.
- Place the thermal pad or isolation pad so the mounting pressure is even across the package.
- Avoid putting tall components between the driver package and the heatsink contact area.
- If an isolation pad is used, verify that it is the thermal bottleneck, not the mounting screw pattern.

## High-Current Layout

- Route the motor current path with the shortest practical loop.
- Keep the power return path wide and obvious.
- Do not run the current-sense traces through the high-current copper path if it can be avoided.
- Keep the sense connector physically separate from the motor power connector so servicing is less error-prone.

## Mounting Guidance

- Use M3-class hardware or equivalent that can survive vibration without loosening.
- Include a flat mounting surface on the chassis side so the heatsink sits squarely.
- Use threadlocking or other vibration-safe retention if the field build normally shakes loose hardware.
- Do not rely on the PCB alone as the mechanical heat spreader.

## Serviceability

- Make the heatsink removable without desoldering the motor power path.
- Keep the connector orientation obvious so the driver can be reinstalled without reversing power or sense lines.
- Leave enough access around the board edge for a screwdriver, inspection light, and cable strain relief.

## Notes For Outsourced Build

If the board is outsourced later, the layout drawing should explicitly call out:

- the heatsink contact zone,
- the isolation pad thickness,
- the fastener locations,
- and the maximum component height in the thermal zone.
