from __future__ import annotations

import pytest

from imu.bmi160 import BMI160Reader


def _le16(value: int) -> list[int]:
    if value < 0:
        value = (1 << 16) + value
    return [value & 0xFF, (value >> 8) & 0xFF]


class FakeBus:
    def __init__(self, chip_id: int = 0xD1, sample_bytes: list[int] | None = None) -> None:
        self.chip_id = chip_id
        self.sample_bytes = sample_bytes or ([0] * 12)
        self.write_byte_data_calls: list[tuple[int, int, int]] = []
        self.read_byte_data_calls: list[tuple[int, int]] = []
        self.read_i2c_block_data_calls: list[tuple[int, int, int]] = []

    def write_byte_data(self, address: int, register: int, value: int) -> None:
        self.write_byte_data_calls.append((address, register, value))

    def read_byte_data(self, address: int, register: int) -> int:
        self.read_byte_data_calls.append((address, register))
        if register == 0x00:
            return self.chip_id
        raise AssertionError(f"Unexpected register read: {register:#x}")

    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
        self.read_i2c_block_data_calls.append((address, register, length))
        if register == 0x0C and length == 12:
            return self.sample_bytes
        raise AssertionError(f"Unexpected block read: register={register:#x} length={length}")


def test_bmi160_reader_initializes_sensor_and_validates_chip_id() -> None:
    bus = FakeBus()

    reader = BMI160Reader(bus=bus, address=0x68, expected_chip_id=0xD1, sample_rate_hz=100.0)
    reader.initialize()

    assert bus.read_byte_data_calls == [(0x68, 0x00)]
    assert (0x68, 0x7E, 0x11) in bus.write_byte_data_calls
    assert (0x68, 0x7E, 0x15) in bus.write_byte_data_calls
    assert (0x68, 0x41, 0x03) in bus.write_byte_data_calls
    assert (0x68, 0x43, 0x03) in bus.write_byte_data_calls


def test_bmi160_reader_rejects_unexpected_chip_id() -> None:
    bus = FakeBus(chip_id=0x00)
    reader = BMI160Reader(bus=bus, address=0x68, expected_chip_id=0xD1, sample_rate_hz=100.0)

    with pytest.raises(ValueError, match="chip id"):
        reader.initialize()


def test_bmi160_reader_converts_raw_sensor_bytes() -> None:
    sample_bytes = (
        _le16(0)
        + _le16(0)
        + _le16(2624)
        + _le16(0)
        + _le16(0)
        + _le16(16384)
    )
    bus = FakeBus(sample_bytes=sample_bytes)
    reader = BMI160Reader(bus=bus, address=0x68, expected_chip_id=0xD1, sample_rate_hz=100.0)
    reader.initialize()

    sample = reader.read(timestamp_monotonic_s=12.5)

    assert sample.valid is True
    assert sample.timestamp_monotonic_s == pytest.approx(12.5)
    assert sample.gyro_z_dps == pytest.approx(20.0)
    assert sample.accel_z_g == pytest.approx(1.0)