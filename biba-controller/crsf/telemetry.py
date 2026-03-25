"""CRSF telemetry transmitter helpers."""

from __future__ import annotations

from typing import Optional

import serial

from crsf.protocol import FRAME_TYPE_BATTERY_SENSOR, FRAME_TYPE_GPS, build_frame


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

    def send_system_stats(self, cpu_pct: float, mem_pct: float) -> None:
        """Send CPU and memory usage via CRSF GPS frame.

        CPU percentage is encoded as ground speed (GSpd sensor).
        Memory percentage is encoded as satellite count (Sats sensor).
        """
        if self.serial_port is None:
            raise RuntimeError("CRSFTelemetry serial port is not attached")

        latitude = 1
        longitude = 1
        groundspeed = max(0, min(65535, int(round(cpu_pct * 10))))
        heading = 0
        altitude = 1000  # 0m with CRSF 1000m offset
        satellites = max(0, min(255, int(round(mem_pct))))

        payload = bytearray()
        payload.extend(latitude.to_bytes(4, byteorder="big", signed=True))
        payload.extend(longitude.to_bytes(4, byteorder="big", signed=True))
        payload.extend(groundspeed.to_bytes(2, byteorder="big", signed=False))
        payload.extend(heading.to_bytes(2, byteorder="big", signed=False))
        payload.extend(altitude.to_bytes(2, byteorder="big", signed=False))
        payload.append(satellites)

        self.serial_port.write(build_frame(FRAME_TYPE_GPS, bytes(payload)))
