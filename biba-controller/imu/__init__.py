"""IMU interfaces and sample types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IMUSample:
    accel_x_g: float | None
    accel_y_g: float | None
    accel_z_g: float | None
    gyro_x_dps: float | None
    gyro_y_dps: float | None
    gyro_z_dps: float | None
    temperature_c: float | None
    timestamp_monotonic_s: float | None
    valid: bool = True


class IMUReader:
    def read(self, timestamp_monotonic_s: float | None = None) -> IMUSample:
        raise NotImplementedError

    def close(self) -> None:
        pass


class NullIMUReader(IMUReader):
    def read(self, timestamp_monotonic_s: float | None = None) -> IMUSample:
        return IMUSample(
            accel_x_g=None,
            accel_y_g=None,
            accel_z_g=None,
            gyro_x_dps=None,
            gyro_y_dps=None,
            gyro_z_dps=None,
            temperature_c=None,
            timestamp_monotonic_s=timestamp_monotonic_s,
            valid=False,
        )