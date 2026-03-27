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

    def send_system_stats(
        self,
        cpu_pct: float,
        mem_pct: float,
        left_motor_current_a: float = 0.0,
        right_motor_current_a: float = 0.0,
    ) -> None:
        """Send CPU and memory usage via CRSF GPS frame.

        CPU percentage is encoded as ground speed (GSpd sensor).
        Memory percentage is encoded as satellite count (Sats sensor).
        Left motor current is encoded as heading (Hdg sensor) in deci-amps.
        Right motor current is encoded as altitude (Alt sensor) in deci-amps,
        using the CRSF altitude 1000m offset.
        """
        if self.serial_port is None:
            raise RuntimeError("CRSFTelemetry serial port is not attached")

        latitude = 1
        longitude = 1
        groundspeed = max(0, min(65535, int(round(cpu_pct * 10))))
        heading = max(0, min(65535, int(round(left_motor_current_a * 10))))
        altitude = 1000 + max(0, min(64535, int(round(right_motor_current_a * 10))))
        satellites = max(0, min(255, int(round(mem_pct))))

        payload = bytearray()
        payload.extend(latitude.to_bytes(4, byteorder="big", signed=True))
        payload.extend(longitude.to_bytes(4, byteorder="big", signed=True))
        payload.extend(groundspeed.to_bytes(2, byteorder="big", signed=False))
        payload.extend(heading.to_bytes(2, byteorder="big", signed=False))
        payload.extend(altitude.to_bytes(2, byteorder="big", signed=False))
        payload.append(satellites)

        self.serial_port.write(build_frame(FRAME_TYPE_GPS, bytes(payload)))
