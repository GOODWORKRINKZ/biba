"""CRSF telemetry transmitter helpers."""

from __future__ import annotations

from typing import Optional

import serial

from crsf.protocol import FRAME_TYPE_BATTERY_SENSOR, build_frame


class CRSFTelemetry:
    """Send CRSF telemetry frames using an already opened serial link."""

    def __init__(self, serial_port: Optional[serial.Serial]) -> None:
        self.serial_port = serial_port

    def attach(self, serial_port: serial.Serial) -> None:
        """Attach a serial port after the receiver has opened it."""
        self.serial_port = serial_port

    def send_battery(
        self,
        voltage_v: float,
        current_a: float,
        capacity_mah: int,
        remaining_pct: int,
    ) -> None:
        """Pack and send a CRSF battery telemetry frame."""
        if self.serial_port is None:
            raise RuntimeError("CRSFTelemetry serial port is not attached")

        voltage = max(0, int(round(voltage_v * 10)))
        current = max(0, int(round(current_a * 10)))
        capacity = max(0, min(capacity_mah, 0xFFFFFF))
        percentage = max(0, min(remaining_pct, 100))

        payload = bytearray()
        payload.extend(voltage.to_bytes(2, byteorder="big", signed=False))
        payload.extend(current.to_bytes(2, byteorder="big", signed=False))
        payload.extend(capacity.to_bytes(3, byteorder="big", signed=False))
        payload.append(percentage)

        self.serial_port.write(build_frame(FRAME_TYPE_BATTERY_SENSOR, bytes(payload)))
