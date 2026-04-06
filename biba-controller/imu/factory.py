"""Generic IMU factory with lightweight backend autodetection."""

from __future__ import annotations

from smbus2 import SMBus

from imu.bmi160 import BMI160Reader
from imu.lsm6ds3 import LSM6DS3Reader


def detect_imu_kind(*, bus, address: int, expected_bmi_chip_id: int) -> str:
    who_am_i = bus.read_byte_data(address, 0x0F)
    if who_am_i == LSM6DS3Reader._WHO_AM_I:
        return "lsm6ds3"

    bmi_chip_id = bus.read_byte_data(address, 0x00)
    if bmi_chip_id == expected_bmi_chip_id:
        return "bmi160"

    raise ValueError(
        f"Unsupported IMU at {address:#x}: bmi_chip_id={bmi_chip_id:#x} who_am_i={who_am_i:#x}"
    )


def open_imu_reader(
    *,
    bus_index: int,
    address: int,
    expected_bmi_chip_id: int,
    sample_rate_hz: float,
    gyro_z_sign: float = 1.0,
):
    bus = SMBus(bus_index)
    try:
        imu_kind = detect_imu_kind(bus=bus, address=address, expected_bmi_chip_id=expected_bmi_chip_id)
        if imu_kind == "bmi160":
            reader = BMI160Reader(
                bus=bus,
                address=address,
                expected_chip_id=expected_bmi_chip_id,
                sample_rate_hz=sample_rate_hz,
                gyro_z_sign=gyro_z_sign,
            )
        else:
            reader = LSM6DS3Reader(
                bus=bus,
                address=address,
                sample_rate_hz=sample_rate_hz,
                gyro_z_sign=gyro_z_sign,
            )
        reader.initialize()
        return reader
    except Exception:
        close_fn = getattr(bus, "close", None)
        if callable(close_fn):
            close_fn()
        raise