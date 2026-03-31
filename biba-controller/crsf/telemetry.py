"""CRSF telemetry transmitter helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import serial

from crsf.protocol import FRAME_TYPE_BATTERY_SENSOR, FRAME_TYPE_GPS, build_frame


@dataclass(frozen=True)
class BIBASystemMetrics:
    cpu_pct: int
    mem_pct: int
    left_wheel_current_ma: int
    right_wheel_current_ma: int


def build_biba_system_metrics(
    cpu_pct: float,
    mem_pct: float,
    left_motor_current_a: float,
    right_motor_current_a: float,
) -> BIBASystemMetrics:
    return BIBASystemMetrics(
        cpu_pct=max(0, min(6553, int(round(cpu_pct)))),
        mem_pct=max(0, min(255, int(round(mem_pct)))),
        left_wheel_current_ma=max(0, min(6553500, int(round(left_motor_current_a * 1000)))),
        right_wheel_current_ma=max(0, min(6453500, int(round(right_motor_current_a * 1000)))),
    )


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
        cpu_pct: float = 0.0,
        mem_pct: float = 0.0,
        left_motor_current_a: float = 0.0,
        right_motor_current_a: float = 0.0,
        *,
        metrics: Optional[BIBASystemMetrics] = None,
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

        if metrics is None:
            metrics = build_biba_system_metrics(
                cpu_pct=cpu_pct,
                mem_pct=mem_pct,
                left_motor_current_a=left_motor_current_a,
                right_motor_current_a=right_motor_current_a,
            )

        latitude = 1
        longitude = 1
        groundspeed = max(0, min(65535, metrics.cpu_pct * 10))
        heading = max(0, min(65535, int(round(metrics.left_wheel_current_ma / 100.0))))
        altitude = 1000 + max(0, min(64535, int(round(metrics.right_wheel_current_ma / 100.0))))
        satellites = max(0, min(255, metrics.mem_pct))

        payload = bytearray()
        payload.extend(latitude.to_bytes(4, byteorder="big", signed=True))
        payload.extend(longitude.to_bytes(4, byteorder="big", signed=True))
        payload.extend(groundspeed.to_bytes(2, byteorder="big", signed=False))
        payload.extend(heading.to_bytes(2, byteorder="big", signed=False))
        payload.extend(altitude.to_bytes(2, byteorder="big", signed=False))
        payload.append(satellites)

        self.serial_port.write(build_frame(FRAME_TYPE_GPS, bytes(payload)))
